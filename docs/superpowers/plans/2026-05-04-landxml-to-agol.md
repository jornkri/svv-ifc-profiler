# LandXML-til-ArcGIS-Online implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Standalone CLI-script som leser LandXML PlanFeature-polylinjer og publiserer dem som georeferert 3D PolylineZ hostet feature service til ArcGIS Online via ArcPy.

**Architecture:** Ny `landxml_parser.py` (ren Python) leser LandXML → koordinater + EPSG. Ny `landxml_to_agol.py` tar over med ArcPy: oppretter PolylineZ feature class i scratchGDB, reprosjekterer ved behov til EPSG:25833, og publiserer via eksisterende `publisher.py`. Følger identisk mønster som `bim_to_agol.py`.

**Tech Stack:** Python 3.11, ArcPy (ArcGIS Pro 3.x), arcgis Python API, python-dotenv, pytest

---

## Filstruktur

```
src/arcpy_processor/
  errors.py              ← ENDRE: legg til LANDXML_NOT_FOUND, LANDXML_PARSE_ERROR
  __init__.py            ← ENDRE: eksporter nye feilkoder + run_landxml_to_agol
  landxml_parser.py      ← OPPRETT: ren Python LandXML-parser
  landxml_to_agol.py     ← OPPRETT: CLI-orkestrator

tests/
  test_arcpy_auth.py     ← ENDRE: legg til test for nye feilkoder
  test_landxml_parser.py ← OPPRETT
  test_landxml_to_agol.py ← OPPRETT
```

---

## Felles datakontraktar

`parse_landxml()` returnerer:
```python
(
    {"L530": [(86098.6, 1283548.2, 129.4), ...]},  # dict[str, list[tuple[float,float,float]]]
    5111                                              # int: kilde-EPSG
)
```

`main()` i `landxml_to_agol.py` printer ved suksess:
```json
{
  "status": "ok",
  "url": "https://services.arcgis.com/.../FeatureServer",
  "item_id": "abc123",
  "item_url": "https://arcgis.com/home/item.html?id=abc123",
  "layer_count": 1,
  "feature_count": 1,
  "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
  "source_epsg": 5111,
  "published_at": "2026-05-04T10:30:00Z"
}
```

---

## Oppgave 1: Utvid errors.py med nye feilkoder

**Filer:**
- Endre: `src/arcpy_processor/errors.py`
- Endre: `src/arcpy_processor/__init__.py`
- Endre: `tests/test_arcpy_auth.py`

- [ ] **Steg 1.1: Skriv feilviklende tester**

Legg til i `tests/test_arcpy_auth.py`:

```python
from src.arcpy_processor.errors import (
    LANDXML_NOT_FOUND, LANDXML_PARSE_ERROR
)


def test_landxml_error_codes_exist():
    assert LANDXML_NOT_FOUND == "LANDXML_NOT_FOUND"
    assert LANDXML_PARSE_ERROR == "LANDXML_PARSE_ERROR"


def test_landxml_error_to_dict():
    from src.arcpy_processor.errors import ArcpyProcessorError
    err = ArcpyProcessorError(LANDXML_PARSE_ERROR, "EPSG mangler")
    assert err.to_dict() == {
        "status": "error",
        "code": "LANDXML_PARSE_ERROR",
        "message": "EPSG mangler",
    }
```

- [ ] **Steg 1.2: Kjør for å bekrefte feil**

```bash
python -m pytest tests/test_arcpy_auth.py::test_landxml_error_codes_exist -v
```
Forventet: `ImportError` (kodene finnes ikke ennå)

- [ ] **Steg 1.3: Legg til feilkoder i `errors.py`**

```python
# src/arcpy_processor/errors.py
from __future__ import annotations


class ArcpyProcessorError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def to_dict(self) -> dict:
        return {"status": "error", "code": self.code, "message": self.message}


# Feilkoder
IFC_NOT_FOUND         = "IFC_NOT_FOUND"
ARCPY_UNAVAILABLE     = "ARCPY_UNAVAILABLE"
AUTH_FAILED           = "AUTH_FAILED"
NAME_EXISTS           = "NAME_EXISTS"
BIM_CONVERSION_FAILED = "BIM_CONVERSION_FAILED"
NO_FEATURES           = "NO_FEATURES"
PUBLISH_FAILED        = "PUBLISH_FAILED"
LANDXML_NOT_FOUND     = "LANDXML_NOT_FOUND"
LANDXML_PARSE_ERROR   = "LANDXML_PARSE_ERROR"
```

- [ ] **Steg 1.4: Oppdater `__init__.py`**

```python
# src/arcpy_processor/__init__.py
from .errors import (
    ArcpyProcessorError,
    IFC_NOT_FOUND,
    ARCPY_UNAVAILABLE,
    AUTH_FAILED,
    NAME_EXISTS,
    BIM_CONVERSION_FAILED,
    NO_FEATURES,
    PUBLISH_FAILED,
    LANDXML_NOT_FOUND,
    LANDXML_PARSE_ERROR,
)
from .bim_to_agol import main as run_bim_to_agol

__all__ = [
    "ArcpyProcessorError",
    "IFC_NOT_FOUND",
    "ARCPY_UNAVAILABLE",
    "AUTH_FAILED",
    "NAME_EXISTS",
    "BIM_CONVERSION_FAILED",
    "NO_FEATURES",
    "PUBLISH_FAILED",
    "LANDXML_NOT_FOUND",
    "LANDXML_PARSE_ERROR",
    "run_bim_to_agol",
]
```

- [ ] **Steg 1.5: Kjør tester**

```bash
python -m pytest tests/test_arcpy_auth.py -v
```
Forventet: alle tester PASS

- [ ] **Steg 1.6: Commit**

```bash
git add src/arcpy_processor/errors.py src/arcpy_processor/__init__.py tests/test_arcpy_auth.py
git commit -m "feat: add LANDXML_NOT_FOUND and LANDXML_PARSE_ERROR error codes"
```

---

## Oppgave 2: landxml_parser.py

**Filer:**
- Opprett: `src/arcpy_processor/landxml_parser.py`
- Opprett: `tests/test_landxml_parser.py`

Ingen ArcPy i denne filen — ren Python.

- [ ] **Steg 2.1: Skriv feilviklende tester**

```python
# tests/test_landxml_parser.py
from __future__ import annotations
from pathlib import Path
import pytest
from src.arcpy_processor.errors import ArcpyProcessorError, LANDXML_PARSE_ERROR

SAMPLE = Path("samples/FV229_Senterlinje.xml")


def test_parses_epsg_from_file():
    from src.arcpy_processor.landxml_parser import parse_landxml
    _, epsg = parse_landxml(SAMPLE)
    assert epsg == 5111


def test_northing_easting_swap():
    from src.arcpy_processor.landxml_parser import parse_landxml
    points_dict, _ = parse_landxml(SAMPLE)
    name = next(iter(points_dict))
    first_pt = points_dict[name][0]
    # LandXML: Northing=1283548, Easting=86098 → etter swap: X(Easting)≈86098
    assert first_pt[0] < 200_000   # Easting er liten i NTM sone 11
    assert first_pt[1] > 1_000_000  # Northing er stor


def test_features_filter():
    from src.arcpy_processor.landxml_parser import parse_landxml
    points_dict, _ = parse_landxml(SAMPLE, features=["L530"])
    assert list(points_dict.keys()) == ["L530"]
    assert len(points_dict["L530"]) >= 2


def test_raises_for_unknown_feature():
    from src.arcpy_processor.landxml_parser import parse_landxml
    with pytest.raises(ArcpyProcessorError) as exc_info:
        parse_landxml(SAMPLE, features=["FINNESIKKE"])
    assert exc_info.value.code == LANDXML_PARSE_ERROR


def test_raises_when_epsg_missing_and_no_override(tmp_path):
    from src.arcpy_processor.landxml_parser import parse_landxml
    xml = tmp_path / "no_epsg.xml"
    xml.write_text(
        '<?xml version="1.0"?>\n'
        '<LandXML>\n'
        '  <CoordinateSystem/>\n'
        '  <PlanFeatures>\n'
        '    <PlanFeature name="A">\n'
        '      <CoordGeom>\n'
        '        <Line><Start>100.0 200.0 10.0</Start><End>101.0 201.0 11.0</End></Line>\n'
        '      </CoordGeom>\n'
        '    </PlanFeature>\n'
        '  </PlanFeatures>\n'
        '</LandXML>\n'
    )
    with pytest.raises(ArcpyProcessorError) as exc_info:
        parse_landxml(xml)
    assert exc_info.value.code == LANDXML_PARSE_ERROR


def test_source_epsg_override(tmp_path):
    from src.arcpy_processor.landxml_parser import parse_landxml
    xml = tmp_path / "no_epsg.xml"
    xml.write_text(
        '<?xml version="1.0"?>\n'
        '<LandXML>\n'
        '  <CoordinateSystem/>\n'
        '  <PlanFeatures>\n'
        '    <PlanFeature name="A">\n'
        '      <CoordGeom>\n'
        '        <Line><Start>100.0 200.0 10.0</Start><End>101.0 201.0 11.0</End></Line>\n'
        '      </CoordGeom>\n'
        '    </PlanFeature>\n'
        '  </PlanFeatures>\n'
        '</LandXML>\n'
    )
    points_dict, epsg = parse_landxml(xml, source_epsg=25833)
    assert epsg == 25833
    assert "A" in points_dict
    assert len(points_dict["A"]) == 2
```

- [ ] **Steg 2.2: Kjør for å bekrefte feil**

```bash
python -m pytest tests/test_landxml_parser.py -v
```
Forventet: `ImportError` (modulen finnes ikke)

- [ ] **Steg 2.3: Implementer `landxml_parser.py`**

```python
# src/arcpy_processor/landxml_parser.py
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import ArcpyProcessorError, LANDXML_PARSE_ERROR


def parse_landxml(
    path: Path,
    features: list[str] | None = None,
    source_epsg: int | None = None,
) -> tuple[dict[str, list[tuple[float, float, float]]], int]:
    """Les LandXML og returner PlanFeature-polylinjer + kilde-EPSG.

    Args:
        path:        Sti til LandXML-fil.
        features:    Navnliste over PlanFeatures å inkludere. None = alle.
        source_epsg: Overstyr kilde-EPSG (brukes hvis epsgCode mangler i fil).

    Returns:
        Tuple (points_dict, epsg) der points_dict mapper PlanFeature-navn
        til liste med (Easting, Northing, Z)-tupler i kilde-CRS.

    Raises:
        ArcpyProcessorError: LANDXML_PARSE_ERROR ved ugyldig XML, manglende
            EPSG eller ingen matchende features.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR, f"Ugyldig XML i '{path.name}': {exc}"
        ) from exc

    root = tree.getroot()
    ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
    ns = {"lx": ns_uri} if ns_uri else {}

    def find_all(parent: ET.Element, tag: str) -> list[ET.Element]:
        return (parent.findall(f".//lx:{tag}", ns) if ns_uri
                else parent.findall(f".//{tag}"))

    def find_one(parent: ET.Element, tag: str) -> ET.Element | None:
        return (parent.find(f"lx:{tag}", ns) if ns_uri
                else parent.find(tag))

    # Les EPSG
    epsg: int | None = source_epsg
    cs_el = find_one(root, "CoordinateSystem")
    if cs_el is not None and cs_el.get("epsgCode"):
        try:
            epsg = int(cs_el.get("epsgCode"))
        except ValueError:
            pass
    if epsg is None:
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR,
            f"Filen '{path.name}' mangler epsgCode i <CoordinateSystem>. "
            "Oppgi kildesystem med --source-epsg.",
        )

    def parse_coord(text: str) -> tuple[float, float, float]:
        parts = text.strip().split()
        n, e = float(parts[0]), float(parts[1])
        z = float(parts[2]) if len(parts) > 2 else 0.0
        return e, n, z  # Northing/Easting-swap → (X=Easting, Y=Northing, Z)

    result: dict[str, list[tuple[float, float, float]]] = {}
    for pf in find_all(root, "PlanFeature"):
        name = pf.get("name", "")
        if features is not None and name not in features:
            continue
        pts: list[tuple[float, float, float]] = []
        for line in find_all(pf, "Line"):
            start_el = find_one(line, "Start")
            end_el = find_one(line, "End")
            if start_el is None or end_el is None:
                continue
            s = parse_coord(start_el.text)
            e_pt = parse_coord(end_el.text)
            if not pts:
                pts.append(s)
            if e_pt != pts[-1]:
                pts.append(e_pt)
        if len(pts) >= 2:
            result[name] = pts

    if not result:
        available = [pf.get("name", "") for pf in find_all(root, "PlanFeature")]
        hint = f" Tilgjengelige PlanFeatures: {available}." if available else ""
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR,
            f"Ingen matchende PlanFeatures funnet i '{path.name}'.{hint}",
        )

    return result, epsg
```

- [ ] **Steg 2.4: Kjør tester**

```bash
python -m pytest tests/test_landxml_parser.py -v
```
Forventet: alle 6 tester PASS

- [ ] **Steg 2.5: Kjør alle tester**

```bash
python -m pytest tests/ -v
```
Forventet: alle PASS (60+ tester)

- [ ] **Steg 2.6: Commit**

```bash
git add src/arcpy_processor/landxml_parser.py tests/test_landxml_parser.py
git commit -m "feat: add LandXML parser with EPSG detection and feature filtering"
```

---

## Oppgave 3: landxml_to_agol.py — CLI-orkestrator

**Filer:**
- Opprett: `src/arcpy_processor/landxml_to_agol.py`
- Opprett: `tests/test_landxml_to_agol.py`
- Endre: `src/arcpy_processor/__init__.py`

- [ ] **Steg 3.1: Skriv feilviklende tester**

```python
# tests/test_landxml_to_agol.py
from __future__ import annotations
import json
import sys
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(scope="module", autouse=True)
def setup_mocks():
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.management.GetCount.return_value = [1]
    sys.modules.setdefault("arcpy", arcpy_mock)
    sys.modules.setdefault("arcpy.conversion", arcpy_mock.conversion)
    sys.modules.setdefault("arcpy.management", arcpy_mock.management)
    sys.modules.setdefault("arcpy.env", arcpy_mock.env)
    sys.modules.setdefault("arcpy.da", arcpy_mock.da)

    arcgis_mock = MagicMock()
    arcgis_gis_mock = MagicMock()
    arcgis_mock.gis = arcgis_gis_mock
    sys.modules.setdefault("arcgis", arcgis_mock)
    sys.modules.setdefault("arcgis.gis", arcgis_gis_mock)


def test_cli_prints_json_on_success(capsys):
    success_meta = {
        "status": "ok",
        "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc123",
        "item_url": "https://arcgis.com/home/item.html?id=abc123",
        "layer_count": 1,
        "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    # landxml_to_agol bruker lazy imports — patch på kildemodulene
    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               return_value=({"L530": [(86098.0, 1283548.0, 129.4)]}, 5111)), \
         patch("src.arcpy_processor.landxml_to_agol.create_polyline_fc",
               return_value="C:/scratch/landxml_temp.gdb/ds_centerline"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--xml", "test.xml", "--name", "TestLag", "--folder", "SVV",
                  "--features", "L530", "--source-epsg", "5111"])
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert result["source_epsg"] == 5111
    assert result["feature_count"] == 1


def test_cli_exits_1_when_xml_not_found(capsys):
    from src.arcpy_processor.landxml_to_agol import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--xml", "finnes_ikke.xml", "--name", "X", "--folder", "Y"])
    assert exc_info.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "LANDXML_NOT_FOUND"


def test_cli_exits_1_on_parse_error(capsys):
    from src.arcpy_processor.errors import ArcpyProcessorError, LANDXML_PARSE_ERROR

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               side_effect=ArcpyProcessorError(LANDXML_PARSE_ERROR, "EPSG mangler")), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--xml", "test.xml", "--name", "X", "--folder", "Y"])
        assert exc_info.value.code == 1

    error = json.loads(capsys.readouterr().err)
    assert error["code"] == LANDXML_PARSE_ERROR
```

- [ ] **Steg 3.2: Kjør for å bekrefte feil**

```bash
python -m pytest tests/test_landxml_to_agol.py -v
```
Forventet: `ImportError` (modulen finnes ikke)

- [ ] **Steg 3.3: Implementer `landxml_to_agol.py`**

```python
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
            polyline = arcpy.Polyline(array, sr, True)
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

        gis = connect()
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
        except Exception as exc:
            raise ArcpyProcessorError(
                PUBLISH_FAILED, f"Kunne ikke opprette feature class: {exc}"
            ) from exc

        if source_epsg != 25833:
            projected_path = fc_path + "_25833"
            arcpy.management.Project(
                fc_path, projected_path, arcpy.SpatialReference(25833)
            )
            arcpy.management.Delete(fc_path)
            fc_path = projected_path
            logger.info("Reprosjektert fra EPSG:%d til EPSG:25833", source_epsg)

        feature_count = int(arcpy.management.GetCount(fc_path)[0])

        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        result["feature_count"] = feature_count
        result["source_epsg"] = source_epsg
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
```

- [ ] **Steg 3.4: Oppdater `__init__.py`**

```python
# src/arcpy_processor/__init__.py
from .errors import (
    ArcpyProcessorError,
    IFC_NOT_FOUND,
    ARCPY_UNAVAILABLE,
    AUTH_FAILED,
    NAME_EXISTS,
    BIM_CONVERSION_FAILED,
    NO_FEATURES,
    PUBLISH_FAILED,
    LANDXML_NOT_FOUND,
    LANDXML_PARSE_ERROR,
)
from .bim_to_agol import main as run_bim_to_agol
from .landxml_to_agol import main as run_landxml_to_agol

__all__ = [
    "ArcpyProcessorError",
    "IFC_NOT_FOUND",
    "ARCPY_UNAVAILABLE",
    "AUTH_FAILED",
    "NAME_EXISTS",
    "BIM_CONVERSION_FAILED",
    "NO_FEATURES",
    "PUBLISH_FAILED",
    "LANDXML_NOT_FOUND",
    "LANDXML_PARSE_ERROR",
    "run_bim_to_agol",
    "run_landxml_to_agol",
]
```

- [ ] **Steg 3.5: Kjør tester**

```bash
python -m pytest tests/test_landxml_to_agol.py -v
```
Forventet: alle 3 tester PASS

- [ ] **Steg 3.6: Kjør alle tester**

```bash
python -m pytest tests/ -v
```
Forventet: alle PASS (66+ tester)

- [ ] **Steg 3.7: Commit**

```bash
git add src/arcpy_processor/landxml_to_agol.py src/arcpy_processor/__init__.py tests/test_landxml_to_agol.py
git commit -m "feat: add LandXML-to-AGOL CLI with PolylineZ feature class and reprojection"
```

---

## Sjekkliste: spec-dekning

| Spec-krav | Oppgave |
|---|---|
| Ny `landxml_parser.py` uten ArcPy | Oppgave 2 |
| EPSG-lesing fra `<CoordinateSystem epsgCode>` | Oppgave 2 |
| `--source-epsg`-override ved manglende epsgCode | Oppgave 2 |
| Feil ved manglende EPSG uten override | Oppgave 2 |
| `--features`-filtrering (kommaseparert) | Oppgave 2 + 3 |
| Default: alle PlanFeatures | Oppgave 2 + 3 |
| Northing/Easting-swap | Oppgave 2 |
| Konsekutive duplikatpunkter fjernes | Oppgave 2 |
| `create_polyline_fc()` → PolylineZ med `name`-felt | Oppgave 3 |
| Slett stale `landxml_temp.gdb` før opprettelse | Oppgave 3 |
| Reprosjeksjon til EPSG:25833 hvis nødvendig | Oppgave 3 |
| Ingen reprojeksjon hvis kilde allerede er 25833 | Oppgave 3 |
| Gjenbruk `upload_and_publish` fra `publisher.py` | Oppgave 3 |
| JSON stdout med `feature_count` + `source_epsg` | Oppgave 3 |
| JSON stderr + exit 1 ved alle feil | Oppgave 3 |
| CLI: `--xml`, `--name`, `--folder`, `--features`, `--source-epsg` | Oppgave 3 |
| `LANDXML_NOT_FOUND` + `LANDXML_PARSE_ERROR` feilkoder | Oppgave 1 |
| `run_landxml_to_agol` eksportert fra `__init__.py` | Oppgave 3 |
