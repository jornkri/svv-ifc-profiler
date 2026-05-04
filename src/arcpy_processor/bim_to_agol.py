from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

from .errors import ArcpyProcessorError, IFC_NOT_FOUND, ARCPY_UNAVAILABLE, NO_FEATURES, PUBLISH_FAILED

logger = logging.getLogger(__name__)


def _gdb_path_from_fcs(fc_paths: list[str]) -> str:
    """Utled GDB-sti fra første FC-sti (format: /scratch/bim_temp.gdb/dataset/FC)."""
    if not fc_paths:
        raise ArcpyProcessorError(PUBLISH_FAILED, "Intern feil: fc_paths er tom")
    parts = Path(fc_paths[0]).parts
    try:
        gdb_idx = next(i for i, p in enumerate(parts) if p.endswith(".gdb"))
    except StopIteration:
        raise ArcpyProcessorError(
            PUBLISH_FAILED,
            f"Intern feil: ingen .gdb-komponent i sti: {fc_paths[0]}",
        ) from None
    return str(Path(*parts[:gdb_idx + 1]))


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
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> NoReturn:
        print(json.dumps(err.to_dict()), file=sys.stderr)
        sys.exit(1)

    if not Path(args.ifc).exists():
        _fail(ArcpyProcessorError(IFC_NOT_FOUND, f"IFC-filen ble ikke funnet: {args.ifc}"))

    try:
        _check_arcpy()
        from .auth import connect
        from .converter import convert_bim, delete_empty_fcs
        from .publisher import check_name_available, upload_and_publish

        gis = connect()
        check_name_available(gis, args.name, args.folder)

        stem = Path(args.ifc).stem
        dataset_name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
        if dataset_name and dataset_name[0].isdigit():
            dataset_name = "_" + dataset_name[:49]

        fc_paths = convert_bim(args.ifc, dataset_name, wkid=25833)
        if not fc_paths:
            raise ArcpyProcessorError(
                NO_FEATURES,
                "BIMFileToGeodatabase produserte ingen feature classes. "
                "Sjekk at IFC-filen inneholder geometri.",
            )
        fc_paths = delete_empty_fcs(fc_paths, "")
        gdb_path = _gdb_path_from_fcs(fc_paths)

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
