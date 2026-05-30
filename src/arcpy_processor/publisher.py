# src/arcpy_processor/publisher.py
from __future__ import annotations

import logging
import os
import re
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


def publish_3d_object_layer(
    gis: GIS, feature_service_item, name: str, folder: str
) -> dict | None:
    """Best-effort: publiser et 3D Object Scene Layer fra et hosted *multipatch*
    feature layer (kilden er ``feature_service_item``).

    Dette er REST-operasjonen bak AGOL-knappen «Publish 3D object layer».
    ``arcgis 2.4.x`` har ingen offentlig metode for dette, og den eksakte
    ``publishParameters``-formen for multipatch→sceneService er ikke offentlig
    dokumentert. Funksjonen er derfor **myk**: enhver feil → ``None`` (logges),
    slik at resten av pipelinen fortsetter. Feature-laget kan da publiseres til
    3D Object Layer med ett klikk i AGOL.

    Returns:
        ``{"scene_url": ..., "scene_item_id": ...}`` ved suksess, ellers ``None``.
    """
    scene_name = re.sub(r"[^A-Za-z0-9_]", "_", name)
    try:
        # Speiler Item._publish: kilde-item som featureService, output sceneService.
        services = gis._portal.publish_item(
            itemid=feature_service_item.id,
            fileType="featureService",
            publishParameters={"name": scene_name},
            outputType="sceneService",
            owner=getattr(feature_service_item, "owner", None),
            folder=folder or None,
            buildInitialCache=True,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort, alt skal degraderes mykt
        logger.warning(
            "Automatisk 3D Object Layer-publisering feilet (%s). Feature-laget er "
            "publisert — publiser 3D-laget manuelt i AGOL via «Publish › 3D object "
            "layer».", exc,
        )
        return None

    svc = (services or [{}])[0]
    if not svc or svc.get("success") is False:
        logger.warning(
            "3D Object Layer-publisering returnerte ingen tjeneste (%s). Publiser "
            "3D-laget manuelt i AGOL.", svc.get("error") if svc else "tomt svar",
        )
        return None

    scene_url = svc.get("serviceurl") or svc.get("serviceURL") or svc.get("serviceUrl")
    scene_item_id = svc.get("serviceItemId")
    logger.info("Publisert 3D Object Scene Layer: %s", scene_url)

    # Scene-itemet arver feature-lagets tittel — sett ren tittel ({name}_3D).
    if scene_item_id:
        try:
            sc_item = gis.content.get(scene_item_id)
            if sc_item is not None:
                sc_item.update(item_properties={"title": scene_name})
        except Exception as title_exc:
            logger.warning("Kunne ikke sette tittel '%s' på scene-item: %s",
                           scene_name, title_exc)

    return {"scene_url": scene_url, "scene_item_id": scene_item_id}


def upload_and_publish(
    gis: GIS, gdb_path: str, name: str, folder: str, *, target_sr: int | None = 25833
) -> dict:
    """Zip GDB, last opp til AGOL og publiser som hosted feature service.

    Args:
        target_sr: WKID som AGOL skal reprosjektere til ved publisering, eller
            ``None`` for å publisere uten reprosjektering. **Viktig:** for
            multipatch (3D) MÅ dette være ``None`` — en `targetSR`-reprosjektering
            ved publisering dropper Z-koordinatene og flater multipatch til 2D-
            polygon (verifisert mot AGOL). GDB-en er allerede reprosjektert lokalt
            av `convert_bim`, så data ligger uansett i ønsket CRS.

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
        publish_params = {"name": name}
        if target_sr is not None:
            publish_params["targetSR"] = {"wkid": target_sr, "latestWkid": target_sr}

        publish_delays = [3, 6, 12, 20]
        fs_item = None
        last_exc = None
        for attempt, delay in enumerate([0] + publish_delays, start=1):
            if delay:
                logger.info("Venter %ds før publisering (forsøk %d)…", delay, attempt)
                time.sleep(delay)
            try:
                fs_item = item.publish(publish_parameters=publish_params)
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

        # Den publiserte tjenesten arver GDB-itemets tittel ("{name}_gdb").
        # Sett den tilbake til ønsket navn så item-tittelen blir ren.
        try:
            fs_item.update(item_properties={"title": name})
        except Exception as title_exc:
            logger.warning("Kunne ikke sette tittel '%s' på publisert item: %s", name, title_exc)

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
