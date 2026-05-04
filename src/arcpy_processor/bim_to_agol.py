# src/arcpy_processor/bim_to_agol.py
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from .errors import ArcpyProcessorError, IFC_NOT_FOUND, ARCPY_UNAVAILABLE

logging.basicConfig(level=logging.INFO, stream=sys.stderr,
                    format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _gdb_path_from_fcs(fc_paths: list[str]) -> str:
    """Utled GDB-sti fra første FC-sti (format: /scratch/bim_temp.gdb/dataset/FC)."""
    parts = Path(fc_paths[0]).parts
    gdb_idx = next(i for i, p in enumerate(parts) if p.endswith(".gdb"))
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
    parser = argparse.ArgumentParser(
        description="Konverter IFC-fil til 3D Object Layer i ArcGIS Online"
    )
    parser.add_argument("--ifc", required=True, help="Sti til .ifc-fil")
    parser.add_argument("--name", required=True, help="Tjenestenavn i ArcGIS Online")
    parser.add_argument("--folder", required=True, help="Folder i ArcGIS Online")
    args = parser.parse_args(argv)

    def _fail(err: ArcpyProcessorError) -> None:
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

        dataset_name = Path(args.ifc).stem.replace(" ", "_")[:50]
        fc_paths = convert_bim(args.ifc, dataset_name, wkid=25833)
        fc_paths = delete_empty_fcs(fc_paths, os.path.dirname(fc_paths[0]))
        gdb_path = _gdb_path_from_fcs(fc_paths)

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
