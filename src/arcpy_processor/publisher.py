# src/arcpy_processor/publisher.py
from __future__ import annotations

import logging
import os
import time
import zipfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arcgis.gis import GIS

from .errors import ArcpyProcessorError, NAME_EXISTS, PUBLISH_FAILED

logger = logging.getLogger(__name__)


def _zip_gdb(gdb_path: str, zip_path: str) -> None:
    """Zip en File GDB og hopp over ArcPy-låsefiler (.lock)."""
    gdb_dir = os.path.dirname(gdb_path)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(gdb_path):
            for fname in files:
                if fname.endswith(".lock"):
                    continue
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, gdb_dir)
                zf.write(full, arcname)


def check_name_available(gis: GIS, name: str, folder: str) -> None:  # noqa: ARG001
    """Feiler med NAME_EXISTS hvis en Feature Service med samme tittel finnes."""
    existing = gis.content.search(
        query=f'title:"{name}" AND type:"Feature Service"',
        max_items=10,
    )
    if any(item.title == name for item in existing):
        raise ArcpyProcessorError(
            NAME_EXISTS,
            f"En Feature Service med navn '{name}' finnes allerede i organisasjonen. "
            "Velg et annet navn eller slett det eksisterende itemet.",
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
        _zip_gdb(gdb_path, zip_path)
        logger.info("Zippet GDB til %s (%.1f MB)", zip_path, os.path.getsize(zip_path) / 1e6)

        # Last opp GDB med et midlertidig navn for å unngå konflikt med Feature Service-navnet.
        # AGOL ville ellers appende "_1" på den publiserte Feature Service.
        gdb_upload_name = f"{name}_gdb"
        item_props = {
            "title": gdb_upload_name,
            "type": "File Geodatabase",
            "tags": "IFC,BIM,SVV,tverrprofil",
            "snippet": f"BIM-data konvertert fra IFC: {name}",
        }
        # gis.content.add() is synchronous and returns a validated Item — more reliable
        # than the async folder_obj.add() job pattern for subsequent publish calls.
        item = gis.content.add(item_properties=item_props, data=zip_path, folder=folder or None)
        if item is None:
            raise ArcpyProcessorError(PUBLISH_FAILED, "Opplasting til AGOL returnerte None")
        logger.info("Lastet opp GDB som item %s (tittel: %s)", item.id, gdb_upload_name)

        # AGOL can lag after upload before the item is queriable for publish.
        # Retry with backoff to handle the propagation delay.
        publish_delays = [3, 6, 12, 20]
        fs_item = None
        last_exc = None
        for attempt, delay in enumerate([0] + publish_delays, start=1):
            if delay:
                logger.info("Venter %ds før publisering (forsøk %d)…", delay, attempt)
                time.sleep(delay)
            try:
                fs_item = item.publish(publish_parameters={"name": name, "targetSR": {"wkid": 25833, "latestWkid": 25833}})
                break
            except Exception as exc:
                last_exc = exc
                if "Could not locate the Item" in str(exc) and attempt <= len(publish_delays):
                    logger.warning("Item ikke tilgjengelig ennå (%s), prøver igjen…", exc)
                    continue
                raise
        if fs_item is None:
            raise last_exc
        logger.info("Publisert feature service: %s", fs_item.url)

        # Slett kilde-GDB-item — bare Feature Service trengs i AGOL.
        try:
            item.delete()
            logger.info("Slettet kilde-GDB item %s", item.id)
        except Exception as del_exc:
            logger.warning("Kunne ikke slette kilde-GDB item %s: %s", item.id, del_exc)

        # Diagnostic: query first feature to verify published coordinates
        try:
            from arcgis.features import FeatureLayer
            _lyr = FeatureLayer(fs_item.url + "/0", gis=gis)
            _q = _lyr.query(where="1=1", out_fields="*", result_record_count=1, out_sr=25833)
            for _feat in _q.features:
                logger.info("AGOL publiserte koordinater (EPSG:25833): %s", _feat.geometry)
                break
        except Exception as _exc:
            logger.warning("Kunne ikke verifisere AGOL-koordinater: %s", _exc)

        layer_count = len(getattr(fs_item, "layers", []))

        return {
            "status": "ok",
            "url": fs_item.url,
            "item_id": fs_item.id,
            "item_url": fs_item.homepage,
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
        # Opprydning er best-effort: på Windows kan zip-fila fortsatt være låst
        # (OneDrive/antivirus/SDK) rett etter opplasting. En feil her skal IKKE
        # maskere et vellykket publiserings-resultat.
        if os.path.exists(zip_path):
            try:
                os.remove(zip_path)
                logger.debug("Slettet midlertidig zip: %s", zip_path)
            except OSError as exc:
                logger.warning("Kunne ikke slette midlertidig zip %s: %s", zip_path, exc)
