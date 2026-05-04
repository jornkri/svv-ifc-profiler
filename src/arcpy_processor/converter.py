# src/arcpy_processor/converter.py
from __future__ import annotations

import os
import logging
from pathlib import Path

import arcpy

from .errors import ArcpyProcessorError, BIM_CONVERSION_FAILED, NO_FEATURES

logger = logging.getLogger(__name__)


def convert_bim(ifc_path: str, dataset_name: str, wkid: int = 25833) -> list[str]:
    """Konverter IFC-fil til feature classes i scratchGDB.

    Returns:
        Liste med fulle stier til feature classes.

    Raises:
        ArcpyProcessorError: BIM_CONVERSION_FAILED hvis konvertering feiler.
    """
    scratch = arcpy.env.scratchFolder
    gdb_name = "bim_temp.gdb"
    gdb_path = os.path.join(scratch, gdb_name)

    try:
        if arcpy.Exists(gdb_path):
            arcpy.management.Delete(gdb_path)
            logger.debug("Slettet eksisterende scratchGDB: %s", gdb_path)
        arcpy.management.CreateFileGDB(scratch, gdb_name)
        sr = arcpy.SpatialReference(wkid)
        arcpy.conversion.BIMFileToGeodatabase(
            str(ifc_path), gdb_path, dataset_name, spatial_reference=sr
        )
    except Exception as exc:
        raise ArcpyProcessorError(
            BIM_CONVERSION_FAILED,
            f"BIMFileToGeodatabase feilet for '{ifc_path}': {exc}",
        ) from exc

    dataset_path = os.path.join(gdb_path, dataset_name)
    old_ws = arcpy.env.workspace
    try:
        arcpy.env.workspace = dataset_path
        fcs = arcpy.ListFeatureClasses() or []
    finally:
        arcpy.env.workspace = old_ws
    logger.info("BIMFileToGeodatabase produserte %d feature classes", len(fcs))
    return [os.path.join(dataset_path, fc) for fc in fcs]


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
