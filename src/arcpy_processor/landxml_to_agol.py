# src/arcpy_processor/landxml_to_agol.py
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

TARGET_EPSG = 25833


def _check_arcpy() -> None:
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:
        raise ArcpyProcessorError(
            ARCPY_UNAVAILABLE,
            "ArcPy er ikke tilgjengelig. Kjør scriptet fra ArcGIS Pro sitt Python-miljø.",
        ) from exc


def create_polyline_fc(
    points_dict: dict[str, list[tuple[float, float, float]]],
    gdb_path: str,
    dataset_name: str,
    source_epsg: int,
) -> str:
    """Opprett PolylineZ feature class i GDB fra points_dict.

    Args:
        points_dict:  {name: [(Easting, Northing, Z), ...]}
        gdb_path:     Full sti til .gdb-katalog.
        dataset_name: Navn på feature class (uten suffiks).
        source_epsg:  EPSG-kode for kilde-CRS.

    Returns:
        Full sti til opprettet feature class.
    """
    import arcpy

    sr = arcpy.SpatialReference(source_epsg)
    fc_name = f"{dataset_name}_centerline"
    fc_path = os.path.join(gdb_path, fc_name)

    arcpy.management.CreateFeatureclass(
        gdb_path, fc_name, "POLYLINE", has_z="ENABLED", spatial_reference=sr
    )
    arcpy.management.AddField(fc_path, "name", "TEXT", field_length=100)
    arcpy.management.AddField(fc_path, "feat_length", "DOUBLE")

    with arcpy.da.InsertCursor(fc_path, ["name", "feat_length", "SHAPE@"]) as cursor:
        for feat_name, pts in points_dict.items():
            array = arcpy.Array([arcpy.Point(x, y, z) for x, y, z in pts])
            polyline = arcpy.Polyline(array, sr, has_z=True)
            cursor.insertRow([feat_name, polyline.length, polyline])

    logger.info("Opprettet FC '%s' med %d feature(s)", fc_name, len(points_dict))
    return fc_path


def main(argv: list[str] | None = None) -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                        format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Publiser LandXML senterlinje som 3D feature service i ArcGIS Online"
    )
    parser.add_argument("--xml", required=True, help="Sti til .xml LandXML-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    parser.add_argument("--features", default=None,
                        help="Kommaseparerte PlanFeature-navn (default: alle)")
    parser.add_argument("--source-epsg", type=int, default=None,
                        help="Overstyr kilde-EPSG hvis mangler i fil")
    parser.add_argument("--lengdeprofil", default=None,
                        help="Sti til lengdeprofil.svg — festes som vedlegg til senterlinjefeatures")
    parser.add_argument("--token", default=None,
                        help="OAuth2 access_token (overstyrer .env credentials)")
    parser.add_argument("--org-url", default=None,
                        help="AGOL org-URL (overstyrer AGOL_ORG_URL i .env)")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> NoReturn:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    if not Path(args.xml).exists():
        _fail(ArcpyProcessorError(LANDXML_NOT_FOUND,
              f"LandXML-filen ble ikke funnet: {args.xml}"))

    features_list = (
        [f.strip() for f in args.features.split(",")]
        if args.features else None
    )

    try:
        _check_arcpy()
        import arcpy
        from .auth import connect
        from .publisher import check_name_available, upload_and_publish
        from .landxml_parser import parse_landxml

        gis = connect(token=args.token, org_url=args.org_url)
        check_name_available(gis, args.name, args.folder)

        points_dict, source_epsg = parse_landxml(
            Path(args.xml),
            features=features_list,
            source_epsg=args.source_epsg,
        )
        logger.info("Leste %d PlanFeature(s) fra %s (EPSG:%d)",
                    len(points_dict), Path(args.xml).name, source_epsg)

        scratch = arcpy.env.scratchFolder
        gdb_name = "landxml_temp.gdb"
        gdb_path = os.path.join(scratch, gdb_name)
        if arcpy.Exists(gdb_path):
            arcpy.management.Delete(gdb_path)
        arcpy.management.CreateFileGDB(scratch, gdb_name)

        stem = Path(args.xml).stem
        dataset_name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
        if dataset_name and dataset_name[0].isdigit():
            dataset_name = "_" + dataset_name[:49]

        try:
            fc_path = create_polyline_fc(points_dict, gdb_path, dataset_name, source_epsg)
        except ArcpyProcessorError:
            raise
        except Exception as exc:
            raise ArcpyProcessorError(
                PUBLISH_FAILED, f"Kunne ikke opprette feature class: {exc}"
            ) from exc

        try:
            if source_epsg != TARGET_EPSG:
                projected_path = fc_path + f"_{TARGET_EPSG}"
                arcpy.management.Project(
                    fc_path, projected_path, arcpy.SpatialReference(TARGET_EPSG)
                )
                arcpy.management.Delete(fc_path)
                fc_path = projected_path
                logger.info("Reprosjektert fra EPSG:%d til EPSG:%d", source_epsg, TARGET_EPSG)
        except ArcpyProcessorError:
            raise
        except Exception as exc:
            raise ArcpyProcessorError(
                PUBLISH_FAILED, f"Reprojeksjon til EPSG:{TARGET_EPSG} feilet: {exc}"
            ) from exc

        feature_count = int(arcpy.management.GetCount(fc_path)[0])

        if args.lengdeprofil:
            lp_path = Path(args.lengdeprofil)
            if lp_path.exists():
                arcpy.management.EnableAttachments(fc_path)
                match_tbl = os.path.join(gdb_path, f"{dataset_name}_lp_match")
                if arcpy.Exists(match_tbl):
                    arcpy.management.Delete(match_tbl)
                arcpy.management.CreateTable(
                    gdb_path, f"{dataset_name}_lp_match"
                )
                arcpy.management.AddField(match_tbl, "fc_oid", "LONG")
                arcpy.management.AddField(match_tbl, "file_path", "TEXT", field_length=512)
                with arcpy.da.SearchCursor(fc_path, ["OID@"]) as cur:
                    with arcpy.da.InsertCursor(match_tbl, ["fc_oid", "file_path"]) as ins:
                        for (oid,) in cur:
                            ins.insertRow((oid, str(lp_path)))
                arcpy.management.AddAttachments(
                    fc_path, "OBJECTID", match_tbl, "fc_oid", "file_path"
                )
                logger.info("Festet lengdeprofil som vedlegg til %d feature(s)", feature_count)
            else:
                logger.warning("--lengdeprofil-fil ikke funnet: %s", args.lengdeprofil)

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        result["feature_count"] = feature_count
        result["source_epsg"] = source_epsg

        # Query back from AGOL in UTM33 (EPSG:25833) for local map display
        try:
            from arcgis.features import FeatureLayer
            lyr = FeatureLayer(result["url"] + "/0", gis=gis)
            fset = lyr.query(where="1=1", out_fields="name", out_sr=25833, return_geometry=True)
            paths: list[list] = []
            for f in fset.features:
                if f.geometry and "paths" in f.geometry:
                    for path in f.geometry["paths"]:
                        paths.append(path)
            result["utm33_centerline_paths"] = paths
            logger.info("Hentet %d UTM33-senterlinjesegmenter fra AGOL", len(paths))
        except Exception as exc:
            logger.warning("Kunne ikke hente UTM33-senterlinje fra AGOL: %s", exc)

        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
