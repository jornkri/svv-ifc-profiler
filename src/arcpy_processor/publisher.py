# src/arcpy_processor/publisher.py
from __future__ import annotations

import logging
import os
import shutil
from datetime import datetime, timezone

from arcgis.gis import GIS

from .errors import ArcpyProcessorError, NAME_EXISTS, PUBLISH_FAILED

logger = logging.getLogger(__name__)


def check_name_available(gis: GIS, name: str, folder: str) -> None:
    """Feiler med NAME_EXISTS hvis et item med samme tittel finnes."""
    # Sjekker navn på tvers av hele org (ikke kun angitt folder) for å unngå navnekonflikter.
    existing = gis.content.search(
        query=f'title:"{name}" AND type:"Feature Service"',
        max_items=10,
    )
    if any(item.title == name for item in existing):
        raise ArcpyProcessorError(
            NAME_EXISTS,
            f"En tjeneste med navn '{name}' finnes allerede i folder '{folder}'. "
            "Velg et annet navn eller slett den eksisterende tjenesten.",
        )


def upload_and_publish(gis: GIS, gdb_path: str, name: str, folder: str) -> dict:
    """Zip GDB, last opp til AGOL og publiser som hosted feature service.

    Returns:
        Dict med status, url, item_id, item_url, feature_count,
        spatial_reference og published_at.

    Raises:
        ArcpyProcessorError: PUBLISH_FAILED hvis noe feiler.
    """
    scratch_dir = os.path.dirname(gdb_path)
    zip_base = os.path.join(scratch_dir, f"{name}_upload")
    zip_path = zip_base + ".zip"

    try:
        shutil.make_archive(zip_base, "zip", scratch_dir, os.path.basename(gdb_path))
        logger.info("Zippet GDB til %s (%.1f MB)", zip_path, os.path.getsize(zip_path) / 1e6)

        item_props = {
            "type": "File Geodatabase",
            "title": name,
            "tags": "IFC,BIM,SVV,tverrprofil",
            "snippet": f"BIM-data konvertert fra IFC: {name}",
        }
        item = gis.content.add(item_props, data=zip_path, folder=folder)
        logger.info("Lastet opp GDB som item %s", item.id)

        fs_item = item.publish()
        logger.info("Publisert feature service: %s", fs_item.url)

        layer_count = len(getattr(fs_item, "layers", []))

        return {
            "status": "ok",
            "url": fs_item.url,
            "item_id": item.id,
            "item_url": item.homepage,
            "layer_count": layer_count,
            "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
            "published_at": datetime.now(timezone.utc).isoformat(),
        }

    except ArcpyProcessorError:
        raise
    except Exception as exc:
        raise ArcpyProcessorError(
            PUBLISH_FAILED,
            f"Publisering til ArcGIS Online feilet: {exc}",
        ) from exc
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            logger.debug("Slettet midlertidig zip: %s", zip_path)
