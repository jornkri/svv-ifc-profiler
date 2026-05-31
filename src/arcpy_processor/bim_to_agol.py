from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from .errors import ArcpyProcessorError, IFC_NOT_FOUND, ARCPY_UNAVAILABLE, NO_FEATURES

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
        description="Konverter IFC-fil til 3D Object Layer i ArcGIS Online"
    )
    parser.add_argument("--ifc", required=True, help="Sti til .ifc-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    parser.add_argument("--token", default=None, help="AGOL OAuth2-token")
    parser.add_argument("--org-url", default=None, dest="org_url",
                        help="ArcGIS Online organisasjons-URL")
    parser.add_argument("--input-wkid", type=int, default=None, dest="input_wkid",
                        help="EPSG-kode for IFC-filens koordinatsystem (brukes når IFC mangler georef)")
    parser.add_argument("--output-wkid", type=int, default=25833, dest="output_wkid",
                        help="EPSG-kode for ønsket utdata-CRS (default: 25833 = UTM33N)")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> NoReturn:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    if not Path(args.ifc).exists():
        _fail(ArcpyProcessorError(IFC_NOT_FOUND, f"IFC-filen ble ikke funnet: {args.ifc}"))

    try:
        _check_arcpy()
        from .auth import connect
        from .converter import convert_bim, merge_and_categorize
        from .publisher import (
            check_name_available,
            publish_3d_object_scene_layer,
            upload_and_publish,
        )
        from src.ifc_processor.bim_classifier import classify_ifc

        plan_name = f"{args.name}_plan"

        gis = connect(token=args.token, org_url=args.org_url)
        # 3D-laget og 2D-plan-laget publiseres som separate tjenester.
        check_name_available(gis, args.name, args.folder)
        check_name_available(gis, plan_name, args.folder)

        stem = Path(args.ifc).stem
        dataset_name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
        if dataset_name and dataset_name[0].isdigit():
            dataset_name = "_" + dataset_name[:49]

        fc_paths = convert_bim(args.ifc, dataset_name,
                               input_wkid=args.input_wkid,
                               output_wkid=args.output_wkid)
        if not fc_paths:
            raise ArcpyProcessorError(
                NO_FEATURES,
                "BIMFileToGeodatabase produserte ingen feature classes. "
                "Sjekk at IFC-filen inneholder geometri.",
            )

        classification = classify_ifc(args.ifc)
        # convert_bim har allerede reprosjektert til output_wkid — ikke reprosjekter på nytt.
        gdb_3d, gdb_plan = merge_and_categorize(fc_paths, classification)

        # 1) Publiser det rene multipatch-laget som eget feature layer.
        #    Dette er den «associated feature layer» et 3D Object Layer bygges på.
        #    target_sr=None: IKKE reprosjekter ved publisering — det dropper Z og
        #    flater multipatch til polygon. GDB-en er allerede i riktig CRS lokalt.
        result_3d = upload_and_publish(gis, gdb_3d, args.name, args.folder, target_sr=None)

        # 2) Best-effort: bygg et PROSJISERT (25833) 3D Object Scene Layer fra
        #    multipatch-laget via SLPK (Output Coordinate System = output_wkid).
        #    Et scene-lag publisert direkte fra feature-tjenesten havner i global
        #    WGS84 og gir «coordinate system mismatch» i en lokal 25833-scene.
        #    Feiler det, beholder vi multipatch-feature-laget (bim_3d_url) som
        #    3D-fallback (samme geometri, 25833, kan tegnes i en lokal SceneView).
        multipatch_fc = str(Path(gdb_3d) / "bim_3d")
        scene = publish_3d_object_scene_layer(
            gis, multipatch_fc, f"{args.name}_3D", args.folder, wkid=args.output_wkid
        )

        # 3) Publiser 2D-plan-laget som eget feature layer.
        result_plan = upload_and_publish(gis, gdb_plan, plan_name, args.folder)

        scene_url = scene.get("scene_url") if scene else None
        result = {
            "status": "ok",
            # url peker på det mest nyttige laget: scene hvis publisert, ellers 3D-FL.
            "url": scene_url or result_3d.get("url"),
            "bim_3d_url": result_3d.get("url"),
            "bim_3d_item_id": result_3d.get("item_id"),
            "bim_scene_url": scene_url,
            "bim_scene_item_id": scene.get("scene_item_id") if scene else None,
            "bim_plan_url": result_plan.get("url"),
            "bim_plan_item_id": result_plan.get("item_id"),
            "spatial_reference": result_3d.get("spatial_reference"),
            "published_at": result_3d.get("published_at"),
        }
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
