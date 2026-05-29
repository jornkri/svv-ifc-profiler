# src/arcpy_processor/landxml_to_agol.py
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from .errors import ArcpyProcessorError, LANDXML_NOT_FOUND, ARCPY_UNAVAILABLE

logger = logging.getLogger(__name__)


def _check_arcpy() -> None:
    try:
        import arcpy  # noqa: F401
    except ImportError as exc:
        raise ArcpyProcessorError(
            ARCPY_UNAVAILABLE,
            "ArcPy er ikke tilgjengelig. Kjør scriptet fra ArcGIS Pro sitt Python-miljø.",
        ) from exc


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
        from .auth import connect
        from .landxml_parser import parse_landxml
        from ._polyline_publisher import publish_polyline_to_agol

        gis = connect(token=args.token, org_url=args.org_url)

        points_dict, source_epsg = parse_landxml(
            Path(args.xml),
            features=features_list,
            source_epsg=args.source_epsg,
        )
        logger.info("Leste %d PlanFeature(s) fra %s (EPSG:%d)",
                    len(points_dict), Path(args.xml).name, source_epsg)

        result = publish_polyline_to_agol(
            points_dict=points_dict,
            source_epsg=source_epsg,
            service_name=args.name,
            folder=args.folder,
            gis=gis,
            source_stem=Path(args.xml).stem,
            lengdeprofil_path=Path(args.lengdeprofil) if args.lengdeprofil else None,
        )

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
