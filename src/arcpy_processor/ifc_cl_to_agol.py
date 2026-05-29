# src/arcpy_processor/ifc_cl_to_agol.py
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from .auth import connect
from .errors import ArcpyProcessorError, LANDXML_NOT_FOUND, ARCPY_UNAVAILABLE
from ._polyline_publisher import publish_polyline_to_agol

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
        description="Publiser IFC4X3-senterlinje som 3D feature service i ArcGIS Online"
    )
    parser.add_argument("--ifc-cl", required=True, help="Sti til .ifc IFC4X3-alignment-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    parser.add_argument("--lengdeprofil", default=None,
                        help="Sti til lengdeprofil.svg — festes som vedlegg")
    parser.add_argument("--token", default=None,
                        help="OAuth2 access_token (overstyrer .env credentials)")
    parser.add_argument("--org-url", default=None,
                        help="AGOL org-URL (overstyrer AGOL_ORG_URL i .env)")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> NoReturn:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    cl_path = Path(args.ifc_cl)
    if not cl_path.exists():
        _fail(ArcpyProcessorError(LANDXML_NOT_FOUND,
              f"IFC-CL-filen ble ikke funnet: {args.ifc_cl}"))

    try:
        _check_arcpy()
        from src.ifc_processor.alignment_parser import load_alignment_from_ifc

        data = load_alignment_from_ifc(cl_path)
        points_dict = {
            data.name: [
                (float(p[0]), float(p[1]), float(p[2])) for p in data.points_3d
            ]
        }
        logger.info(
            "IFC-CL '%s': %d 3D-punkter, %d hor.seg, %d vert.seg, %d referenter",
            data.name, len(data.points_3d), len(data.horizontal_segments),
            len(data.vertical_segments), len(data.station_labels),
        )

        extra_field_values = {
            "alignment_name": ("TEXT", {"field_length": 100}, data.name),
            "n_hor_seg": ("LONG", {}, len(data.horizontal_segments)),
            "n_vert_seg": ("LONG", {}, len(data.vertical_segments)),
            "n_referents": ("LONG", {}, len(data.station_labels)),
        }

        gis = connect(token=args.token, org_url=args.org_url)
        result = publish_polyline_to_agol(
            points_dict=points_dict,
            source_epsg=data.source_epsg,
            service_name=args.name,
            folder=args.folder,
            gis=gis,
            source_stem=cl_path.stem,
            lengdeprofil_path=Path(args.lengdeprofil) if args.lengdeprofil else None,
            extra_field_values=extra_field_values,
        )

        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)
    except ValueError as err:
        # alignment_parser-feil → klare meldinger til frontend
        _fail(ArcpyProcessorError("IFC_CL_PARSE_ERROR", str(err)))


if __name__ == "__main__":
    main()
