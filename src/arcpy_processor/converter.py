# src/arcpy_processor/converter.py
from __future__ import annotations

import os
import logging
from pathlib import Path

import arcpy

from .errors import ArcpyProcessorError, BIM_CONVERSION_FAILED, NO_FEATURES
from src.ifc_processor.bim_classifier import ClassifiedElement

logger = logging.getLogger(__name__)


def _resolve_kategori(global_id: str,
                      classification: dict[str, ClassifiedElement]) -> tuple[str, str, str, str]:
    """Returner (kategori, fag_gruppe, ifc_klasse, navn) for en GlobalId.
    Ukjent GlobalId → Uklassifisert (mister ingenting stille)."""
    ce = classification.get(global_id)
    if ce is None:
        return ("Uklassifisert", "Annet", "", "")
    return (ce.kategori, ce.fag_gruppe, ce.ifc_klasse, ce.navn)


def _find_guid_field(fc_path: str) -> str | None:
    """Finn feltet som holder IFC-GlobalId i en feature class (case-insensitivt).
    Returner None hvis ingen kandidat finnes (→ trigger fallback i kaller)."""
    for f in arcpy.ListFields(fc_path):
        if "globalid" in f.name.lower() or "ifcguid" in f.name.lower():
            return f.name
    return None


def convert_bim(
    ifc_path: str,
    dataset_name: str,
    input_wkid: int | None = None,
    output_wkid: int = 25833,
) -> list[str]:
    """Konverter IFC-fil til feature classes i scratchGDB.

    Args:
        ifc_path:     Sti til .ifc-fil.
        dataset_name: Navn på feature dataset i GDB.
        input_wkid:   EPSG-kode for IFC-filens koordinatsystem. Hvis oppgitt og
                      ulik output_wkid, reprosjekteres datasettetet etterpå.
                      Bruk når IFC mangler IfcProjectedCRS eller har feil CRS.
        output_wkid:  EPSG-kode for ønsket utdata-CRS (default: 25833 = UTM33N).

    Returns:
        Liste med fulle stier til feature classes.

    Raises:
        ArcpyProcessorError: BIM_CONVERSION_FAILED hvis konvertering feiler.
    """
    scratch = arcpy.env.scratchFolder
    gdb_name = "bim_temp.gdb"
    gdb_path = os.path.join(scratch, gdb_name)

    bim_sr_wkid = input_wkid if input_wkid else output_wkid

    try:
        if arcpy.Exists(gdb_path):
            arcpy.management.Delete(gdb_path)
            logger.debug("Slettet eksisterende scratchGDB: %s", gdb_path)
        arcpy.management.CreateFileGDB(scratch, gdb_name)
        sr = arcpy.SpatialReference(bim_sr_wkid)
        arcpy.conversion.BIMFileToGeodatabase(
            str(ifc_path), gdb_path, dataset_name, spatial_reference=sr
        )
    except Exception as exc:
        raise ArcpyProcessorError(
            BIM_CONVERSION_FAILED,
            f"BIMFileToGeodatabase feilet for '{ifc_path}': {exc}",
        ) from exc

    dataset_path = os.path.join(gdb_path, dataset_name)

    # Slett tomme feature classes før eventuell reprosjektering
    old_ws = arcpy.env.workspace
    try:
        arcpy.env.workspace = dataset_path
        all_fcs = arcpy.ListFeatureClasses() or []
    finally:
        arcpy.env.workspace = old_ws

    for fc in all_fcs:
        fc_path = os.path.join(dataset_path, fc)
        count = int(arcpy.management.GetCount(fc_path)[0])
        if count == 0:
            arcpy.management.Delete(fc_path)
            logger.debug("Slettet tom FC: %s", fc)
        else:
            logger.debug("Beholder FC med %d features: %s", count, fc)

    old_ws = arcpy.env.workspace
    try:
        arcpy.env.workspace = dataset_path
        remaining_fcs = arcpy.ListFeatureClasses() or []
    finally:
        arcpy.env.workspace = old_ws

    if not remaining_fcs:
        raise ArcpyProcessorError(
            NO_FEATURES,
            "Alle feature classes var tomme etter BIMFileToGeodatabase. "
            "Sjekk at IFC-filen inneholder geometri.",
        )
    logger.info("BIMFileToGeodatabase: %d av %d feature classes har data",
                len(remaining_fcs), len(all_fcs))

    if input_wkid and input_wkid != output_wkid:
        projected_path = dataset_path + "_out"
        try:
            arcpy.management.Project(
                dataset_path, projected_path, arcpy.SpatialReference(output_wkid)
            )
            logger.debug("Reprosjekterte datasett fra EPSG:%d til EPSG:%d", input_wkid, output_wkid)
        except Exception as exc:
            raise ArcpyProcessorError(
                BIM_CONVERSION_FAILED,
                f"Reprosjektering fra EPSG:{input_wkid} til EPSG:{output_wkid} feilet: {exc}",
            ) from exc
        dataset_path = projected_path

        old_ws = arcpy.env.workspace
        try:
            arcpy.env.workspace = dataset_path
            remaining_fcs = arcpy.ListFeatureClasses() or []
        finally:
            arcpy.env.workspace = old_ws

    return [os.path.join(dataset_path, fc) for fc in remaining_fcs]


def delete_empty_fcs(fc_paths: list[str], dataset_path: str) -> list[str]:  # noqa: ARG001
    """Slett feature classes uten features. Returner gjenstående.

    Args:
        fc_paths: Liste med stier til feature classes å sjekke.
        dataset_path: Stien til datasett (reservert for fremtidiges implementasjoner).

    Raises:
        ArcpyProcessorError: NO_FEATURES hvis alle er tomme.
    """
    remaining = []
    for fc_path in fc_paths:
        count = int(arcpy.management.GetCount(fc_path)[0])
        if count == 0:
            arcpy.management.Delete(fc_path)
            logger.debug("Slettet tom FC: %s", fc_path)
        else:
            remaining.append(fc_path)
            logger.debug("Beholder FC med %d features: %s", count, fc_path)

    if not remaining:
        raise ArcpyProcessorError(
            NO_FEATURES,
            "Alle feature classes var tomme etter konvertering. "
            "Sjekk at IFC-filen inneholder geometri.",
        )
    return remaining
