# src/arcpy_processor/_polyline_publisher.py
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from .auth import connect  # noqa: F401 — re-eksport for testbarhet
from .errors import ArcpyProcessorError, PUBLISH_FAILED
from .publisher import check_name_available, upload_and_publish

logger = logging.getLogger(__name__)

TARGET_EPSG = 25833


def _create_polyline_fc(
    points_dict: dict[str, list[tuple[float, float, float]]],
    gdb_path: str,
    dataset_name: str,
    source_epsg: int,
    extra_fields: list[tuple[str, str, dict[str, Any]]] | None = None,
) -> str:
    """Opprett PolylineZ FC. extra_fields: liste av (field_name, field_type, kwargs)."""
    import arcpy
    sr = arcpy.SpatialReference(source_epsg)
    fc_name = f"{dataset_name}_centerline"
    fc_path = os.path.join(gdb_path, fc_name)
    arcpy.management.CreateFeatureclass(
        gdb_path, fc_name, "POLYLINE", has_z="ENABLED", spatial_reference=sr
    )
    arcpy.management.AddField(fc_path, "name", "TEXT", field_length=100)
    arcpy.management.AddField(fc_path, "feat_length", "DOUBLE")
    extra_fields = extra_fields or []
    for fname, ftype, fkwargs in extra_fields:
        arcpy.management.AddField(fc_path, fname, ftype, **fkwargs)

    insert_fields = ["name", "feat_length", "SHAPE@"] + [f[0] for f in extra_fields]
    with arcpy.da.InsertCursor(fc_path, insert_fields) as cursor:
        for feat_name, pts in points_dict.items():
            array = arcpy.Array([arcpy.Point(x, y, z) for x, y, z in pts])
            polyline = arcpy.Polyline(array, sr, has_z=True)
            row = [feat_name, polyline.length, polyline] + \
                  [None] * len(extra_fields)   # extra-verdier settes av kaller via UpdateCursor
            cursor.insertRow(row)
    logger.info("Opprettet FC '%s' med %d feature(s)", fc_name, len(points_dict))
    return fc_path


def _sanitize_name(stem: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
    if name and name[0].isdigit():
        name = "_" + name[:49]
    return name


def publish_polyline_to_agol(
    points_dict: dict[str, list[tuple[float, float, float]]],
    *,
    source_epsg: int,
    service_name: str,
    folder: str,
    gis,
    source_stem: str | None = None,
    lengdeprofil_path: Path | None = None,
    extra_field_values: dict[str, tuple[str, dict[str, Any], Any]] | None = None,
) -> dict:
    """Publiser polylinje-data som hostet FeatureService i AGOL.

    Args:
        points_dict: navn → liste av (E, N, Z)-punkter
        source_epsg: kilde-CRS
        service_name: tjenestenavn i AGOL
        folder: AGOL-mappe ("" = rot)
        gis: arcgis.gis.GIS-instans
        source_stem: filnavn-stem brukt til datasett-naming (default: service_name)
        lengdeprofil_path: valgfri SVG som vedlegges hver feature
        extra_field_values: {field_name: (field_type, addfield_kwargs, value)} for
                            ekstra attributter (samme verdi på alle features)
    """
    import arcpy
    check_name_available(gis, service_name, folder)

    scratch = arcpy.env.scratchFolder
    gdb_name = "publish_temp.gdb"
    gdb_path = os.path.join(scratch, gdb_name)
    if arcpy.Exists(gdb_path):
        arcpy.management.Delete(gdb_path)
    arcpy.management.CreateFileGDB(scratch, gdb_name)

    dataset_name = _sanitize_name(source_stem or service_name)

    extra_field_values = extra_field_values or {}
    extra_fields = [(n, t, k) for n, (t, k, _) in extra_field_values.items()]

    try:
        fc_path = _create_polyline_fc(
            points_dict, gdb_path, dataset_name, source_epsg, extra_fields=extra_fields,
        )
    except Exception as exc:
        raise ArcpyProcessorError(
            PUBLISH_FAILED, f"Kunne ikke opprette feature class: {exc}"
        ) from exc

    # Fyll inn extra_field_values
    if extra_field_values:
        with arcpy.da.UpdateCursor(fc_path, list(extra_field_values.keys())) as cur:
            for row in cur:
                cur.updateRow([v for _, (_, _, v) in extra_field_values.items()])

    if source_epsg != TARGET_EPSG:
        projected_path = fc_path + f"_{TARGET_EPSG}"
        arcpy.management.Project(fc_path, projected_path, arcpy.SpatialReference(TARGET_EPSG))
        arcpy.management.Delete(fc_path)
        fc_path = projected_path
        logger.info("Reprosjektert fra EPSG:%d til EPSG:%d", source_epsg, TARGET_EPSG)

    feature_count = int(arcpy.management.GetCount(fc_path)[0])

    if lengdeprofil_path and lengdeprofil_path.exists():
        arcpy.management.EnableAttachments(fc_path)
        match_tbl = os.path.join(gdb_path, f"{dataset_name}_lp_match")
        if arcpy.Exists(match_tbl):
            arcpy.management.Delete(match_tbl)
        arcpy.management.CreateTable(gdb_path, f"{dataset_name}_lp_match")
        arcpy.management.AddField(match_tbl, "fc_oid", "LONG")
        arcpy.management.AddField(match_tbl, "file_path", "TEXT", field_length=512)
        with arcpy.da.SearchCursor(fc_path, ["OID@"]) as cur:
            with arcpy.da.InsertCursor(match_tbl, ["fc_oid", "file_path"]) as ins:
                for (oid,) in cur:
                    ins.insertRow((oid, str(lengdeprofil_path)))
        arcpy.management.AddAttachments(
            fc_path, "OBJECTID", match_tbl, "fc_oid", "file_path"
        )
        logger.info("Festet lengdeprofil som vedlegg til %d feature(s)", feature_count)

    result = upload_and_publish(gis, gdb_path, service_name, folder)
    result["feature_count"] = feature_count
    result["source_epsg"] = source_epsg
    return result
