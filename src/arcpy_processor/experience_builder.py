# src/arcpy_processor/experience_builder.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arcgis.features import FeatureLayer
    from arcgis.gis import GIS

logger = logging.getLogger(__name__)


def _attachment_url(layer_url: str, oid: int, attachment_id: int) -> str:
    """Construct REST URL for an attachment in an AGOL FeatureLayer."""
    return f"{layer_url}/{oid}/attachments/{attachment_id}"


def backfill_svg_urls(layer: "FeatureLayer") -> int:
    """Query AGOL attachment info per feature and write the SVG URL to svg_url field.

    Iterates through all features in the layer, finds the first SVG attachment for each,
    constructs its REST URL, and writes it back to the svg_url attribute field via
    edit_features.

    Args:
        layer: An ArcGIS FeatureLayer object (published to AGOL).

    Returns:
        Number of features updated.
    """
    from arcgis.features import Feature

    fset = layer.query(where="1=1", out_fields="OBJECTID", return_geometry=False)
    updates = []

    for feat in fset.features:
        oid = feat.attributes["OBJECTID"]
        attachments = layer.attachments.search(oid)
        svg_att = next(
            (a for a in attachments if str(a.get("name", "")).lower().endswith(".svg")),
            None,
        )
        if svg_att is None:
            logger.warning("Ingen SVG-attachment funnet for OID %d", oid)
            continue
        url = _attachment_url(layer.url, oid, svg_att["id"])
        updates.append(Feature(attributes={"OBJECTID": oid, "svg_url": url}))

    if updates:
        layer.edit_features(updates=updates)
        logger.info("svg_url oppdatert for %d features", len(updates))

    return len(updates)


def create_or_update_experience(
    gis: "GIS",
    name: str,
    centerline_item_id: str,
    sections_item_id: str,
    sections_service_url: str,
    template_path: Path,
) -> str:
    """Create or update an Experience Builder app on AGOL from a config.json template.

    Placeholders in the template:
        __CENTERLINE_ITEM_ID__  → centerline_item_id
        __SECTIONS_ITEM_ID__    → sections_item_id
        __SERVICE_URL__         → sections_service_url

    Returns the item homepage URL.
    """
    from arcgis.apps.expbuilder import WebExperience

    config_json = (
        template_path.read_text(encoding="utf-8")
        .replace("__CENTERLINE_ITEM_ID__", centerline_item_id)
        .replace("__SECTIONS_ITEM_ID__", sections_item_id)
        .replace("__SERVICE_URL__", sections_service_url)
    )

    existing = gis.content.search(
        query=f'title:"{name}" type:"Web Experience"',
        max_items=5,
    )
    exp_item = next((i for i in existing if i.title == name), None)

    if exp_item is None:
        exp = WebExperience(gis=gis)
        exp.create(title=name, tags=["IFC", "SVV", "tverrprofil", "R700"])
        exp_item = exp.item
        logger.info("Opprettet ny XB-app '%s' (%s)", name, exp_item.id)
    else:
        logger.info("Oppdaterer eksisterende XB-app '%s' (%s)", name, exp_item.id)

    exp_item.update(data=config_json)

    try:
        WebExperience(exp_item).publish()
    except Exception as exc:
        logger.warning("XB publish() feilet (%s) — konfigurasjonen er oppdatert", exc)

    return exp_item.homepage
