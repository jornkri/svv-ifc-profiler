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
