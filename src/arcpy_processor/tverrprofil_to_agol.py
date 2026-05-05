# src/arcpy_processor/tverrprofil_to_agol.py
"""CLI: publiser tverrprofil-stasjoner med SVG-vedlegg til ArcGIS Online."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from .errors import ArcpyProcessorError, LANDXML_NOT_FOUND, ARCPY_UNAVAILABLE, PUBLISH_FAILED

logger = logging.getLogger(__name__)


def _check_arcpy() -> None:
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:
        raise ArcpyProcessorError(
            ARCPY_UNAVAILABLE,
            "ArcPy er ikke tilgjengelig. Kjør scriptet fra ArcGIS Pro sitt Python-miljø.",
        ) from exc


def create_point_fc(
    stations: list[dict],
    gdb_path: str,
    dataset_name: str,
) -> str:
    """Opprett PointZ feature class og populer med stasjonsdata.

    Args:
        stations:     Liste med dicts {station_m, profil_nr, x, y, z}.
        gdb_path:     Full sti til .gdb-katalog.
        dataset_name: Navn på datasett (brukes som prefix for feature class).

    Returns:
        Full sti til opprettet feature class.
    """
    import arcpy

    sr = arcpy.SpatialReference(25833)
    fc_name = f"{dataset_name}_tverrprofiler"
    fc_path = os.path.join(gdb_path, fc_name)

    arcpy.management.CreateFeatureclass(
        gdb_path, fc_name, "POINT", spatial_reference=sr, has_z="ENABLED"
    )
    arcpy.management.AddField(fc_path, "stasjon_m", "DOUBLE")
    arcpy.management.AddField(fc_path, "profil_nr", "TEXT", field_length=20)

    with arcpy.da.InsertCursor(fc_path, ["stasjon_m", "profil_nr", "SHAPE@"]) as cur:
        for row in stations:
            pt = arcpy.Point(row["x"], row["y"], row["z"])
            geom = arcpy.PointGeometry(pt, sr)
            cur.insertRow((row["station_m"], row["profil_nr"], geom))

    logger.info("Opprettet FC '%s' med %d punkt(er)", fc_name, len(stations))
    return fc_path


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Publiser tverrprofil-stasjoner med SVG-vedlegg til ArcGIS Online"
    )
    parser.add_argument("--stations-json", required=True,
                        help="Sti til stations.json fra run_pipeline")
    parser.add_argument("--svgs-dir", required=True,
                        help="Katalog med SVG-filer navngitt station_{m:07.1f}.svg")
    parser.add_argument("--name", required=True,
                        help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", default="",
                        help="Mappe i ArcGIS Online (default: rotmappen)")
    parser.add_argument("--token", default=None,
                        help="OAuth2 access_token (overstyrer .env credentials)")
    parser.add_argument("--org-url", default=None,
                        help="AGOL org-URL (overstyrer AGOL_ORG_URL i .env)")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> NoReturn:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    stations_path = Path(args.stations_json)
    if not stations_path.exists():
        _fail(ArcpyProcessorError(
            LANDXML_NOT_FOUND,
            f"stations.json ble ikke funnet: {args.stations_json}",
        ))

    try:
        _check_arcpy()
        import arcpy
        from .auth import connect
        from .publisher import check_name_available, upload_and_publish

        gis = connect(token=args.token, org_url=args.org_url)
        check_name_available(gis, args.name, args.folder)

        stations = json.loads(stations_path.read_text())
        svgs_dir = Path(args.svgs_dir)

        scratch = arcpy.env.scratchFolder
        stem = re.sub(r"[^A-Za-z0-9_]", "_", args.name)[:50]
        if stem and stem[0].isdigit():
            stem = "_" + stem[:49]
        gdb_name = f"{stem}_tverrprofil.gdb"
        gdb_path = os.path.join(scratch, gdb_name)

        if arcpy.Exists(gdb_path):
            arcpy.management.Delete(gdb_path)
        arcpy.management.CreateFileGDB(scratch, gdb_name)

        try:
            fc_path = create_point_fc(stations, gdb_path, stem)
        except ArcpyProcessorError:
            raise
        except Exception as exc:
            raise ArcpyProcessorError(
                PUBLISH_FAILED, f"Kunne ikke opprette feature class: {exc}"
            ) from exc

        arcpy.management.EnableAttachments(fc_path)

        # AddAttachments krever en match-tabell: (join_oid, file_path)
        match_tbl = os.path.join(arcpy.env.scratchGDB, f"{stem}_attach_match")
        if arcpy.Exists(match_tbl):
            arcpy.management.Delete(match_tbl)
        arcpy.management.CreateTable(arcpy.env.scratchGDB, f"{stem}_attach_match")
        arcpy.management.AddField(match_tbl, "fc_oid", "LONG")
        arcpy.management.AddField(match_tbl, "svg_path", "TEXT", field_length=512)

        rows_added = 0
        with arcpy.da.SearchCursor(fc_path, ["OID@", "stasjon_m"]) as cur:
            with arcpy.da.InsertCursor(match_tbl, ["fc_oid", "svg_path"]) as ins:
                for oid, station_m in cur:
                    svg = svgs_dir / f"station_{station_m:07.1f}.svg"
                    if svg.exists():
                        ins.insertRow((oid, str(svg)))
                        rows_added += 1
                    else:
                        logger.warning("SVG ikke funnet for stasjon %.1f m: %s", station_m, svg)

        if rows_added > 0:
            arcpy.management.AddAttachments(fc_path, "OBJECTID", match_tbl, "fc_oid", "svg_path")

        feature_count = int(arcpy.management.GetCount(fc_path)[0])
        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        result["feature_count"] = feature_count
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
