# Tverrprofil-pipeline Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backend API for OAuth2 auth, file upload, IFC processing, and AGOL publishing — the full server-side pipeline from IFC+LandXML upload to published feature services.

**Architecture:** FastAPI + starlette SessionMiddleware for OAuth2; BackgroundTasks for IFC/ArcPy processing; subprocesses for ArcPy AGOL publishing. Job state stored in-memory dict for MVP.

**Tech Stack:** FastAPI 0.110+, starlette sessions, httpx, arcpy (subprocess), arcgis Python API, pytest.

---

## File Structure

**Create:**
- `src/api/auth_routes.py` — OAuth2 router: GET /auth/login, /callback, /me; POST /auth/logout
- `src/api/job_runner.py` — job state machine + `run_job()` background function
- `src/arcpy_processor/tverrprofil_to_agol.py` — CLI: publish cross-section stations to AGOL
- `tests/test_pipeline_stations_json.py` — verify `run_pipeline` writes stations.json
- `tests/test_tverrprofil_to_agol.py` — mock arcpy + arcgis for tverrprofil CLI
- `tests/test_api_auth.py` — OAuth2 flow with mocked AGOL
- `tests/test_api_jobs.py` — POST /api/jobs + GET /api/jobs/{id}

**Modify:**
- `src/ifc_processor/pipeline.py:119-150` — add `stations.json` + `stations_json` key to output
- `src/arcpy_processor/auth.py:13-33` — add `token` / `org_url` params to `connect()`
- `src/arcpy_processor/landxml_to_agol.py:76-108` — add `--token` / `--org-url` CLI args
- `src/api/server.py` — add SessionMiddleware + auth router + POST /api/jobs + clean up old /api/upload
- `requirements.txt` — add `httpx>=0.27`, `itsdangerous>=2.1`

---

### Task 1: pipeline.py — stations.json output

**Files:**
- Modify: `src/ifc_processor/pipeline.py:119-150`
- Create: `tests/test_pipeline_stations_json.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pipeline_stations_json.py
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from src.ifc_processor.pipeline import run_pipeline
from src.ifc_processor.cross_section import CrossSection

SAMPLE_IFC = Path(__file__).parent.parent / "samples" / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"


def _cl_geojson(tmp: Path) -> Path:
    cl = tmp / "cl.geojson"
    cl.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature",
                      "geometry": {"type": "LineString",
                                   "coordinates": [[10.0, 20.0, 100.0],
                                                   [60.0, 20.0, 101.0]]},
                      "properties": {}}],
    }))
    return cl


def test_stations_json_keys_with_mocks(tmp_path):
    """stations.json keys and format — no real IFC needed."""
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    assert "stations_json" in result
    stations = json.loads(Path(result["stations_json"]).read_text())
    assert isinstance(stations, list)
    assert len(stations) >= 1
    row = stations[0]
    for key in ("station_m", "profil_nr", "x", "y", "z"):
        assert key in row
    assert row["station_m"] == pytest.approx(0.0)
    assert row["profil_nr"] == "0000.00"    # f"{0.0:07.2f}"
    assert row["x"] == pytest.approx(10.0)  # first point of centerline
    assert row["y"] == pytest.approx(20.0)
    assert row["z"] == pytest.approx(100.0)


def test_stations_json_profil_nr_format(tmp_path):
    """profil_nr matches f'{station_m:07.2f}'."""
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    stations = json.loads(Path(result["stations_json"]).read_text())
    for row in stations:
        assert row["profil_nr"] == f"{row['station_m']:07.2f}"


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_stations_json_with_real_ifc():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=_cl_geojson(tmp_path),
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )
        assert "stations_json" in result
        stations = json.loads(Path(result["stations_json"]).read_text())
        assert len(stations) >= 1
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_pipeline_stations_json.py -v
```
Expected: FAIL — `KeyError: 'stations_json'`

- [ ] **Step 3: Implement in pipeline.py**

In `run_pipeline()`, before the stations loop (line 119), add:
```python
station_rows: list[dict] = []
```

Inside the loop success branch, **after** the `svg_paths.append(str(svg_path))` line, add:
```python
station_rows.append({
    "station_m": round(s.distance, 3),
    "profil_nr": f"{s.distance:07.2f}",
    "x": round(float(s.position[0]), 3),
    "y": round(float(s.position[1]), 3),
    "z": round(float(s.position[2]), 3),
})
```

After the `_save_centerline_geojson` call (before `meta_path`), add:
```python
stations_json_path = output_dir / "stations.json"
stations_json_path.write_text(json.dumps(station_rows, indent=2))
```

Update the return dict:
```python
return {
    "svgs": svg_paths,
    "centerline": str(cl_path),
    "metadata": str(meta_path),
    "stations_json": str(stations_json_path),
}
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_pipeline_stations_json.py -v
```
Expected: PASS (2–3 tests; real-IFC test skipped if sample absent)

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline_stations_json.py
git commit -m "feat: add stations.json output to run_pipeline"
```

---

### Task 2: auth.py — token/org_url support

**Files:**
- Modify: `src/arcpy_processor/auth.py`
- Modify: `tests/test_arcpy_auth.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_arcpy_auth.py`:

```python
def test_connect_with_token_calls_gis_with_token():
    from unittest.mock import patch, MagicMock
    import sys

    # Ensure arcgis.gis is mocked
    gis_mock = MagicMock()
    gis_class = MagicMock(return_value=gis_mock)
    with patch.dict("sys.modules", {"arcgis": MagicMock(gis=MagicMock(GIS=gis_class)),
                                    "arcgis.gis": MagicMock(GIS=gis_class)}):
        with patch("src.arcpy_processor.auth.GIS", gis_class):
            from importlib import reload
            import src.arcpy_processor.auth as auth_mod
            reload(auth_mod)
            result = auth_mod.connect(token="mytoken", org_url="https://test.arcgis.com")

    gis_class.assert_called_once_with("https://test.arcgis.com", token="mytoken")
```

Actually `auth.py` uses lazy import of GIS inside the function. Patch at module level won't work.
Use this simpler approach instead — add at the bottom of `tests/test_arcpy_auth.py`:

```python
def test_connect_with_token_uses_token_not_password():
    """connect(token=...) calls GIS(url, token=...) not GIS(url, user, pass)."""
    from unittest.mock import patch, MagicMock, call

    gis_instance = MagicMock()
    gis_class = MagicMock(return_value=gis_instance)

    with patch("builtins.__import__", side_effect=lambda name, *a, **k: (
        type("M", (), {"GIS": gis_class})() if name == "arcgis.gis"
        else __import__(name, *a, **k)
    )):
        pass  # complex — use direct import patch instead

    # Simpler: mock the lazy import path
    arcgis_gis_mock = MagicMock()
    arcgis_gis_mock.GIS = MagicMock(return_value=MagicMock())
    with patch.dict("sys.modules", {"arcgis.gis": arcgis_gis_mock}):
        from src.arcpy_processor.auth import connect
        connect(token="tok123", org_url="https://myorg.maps.arcgis.com")

    call_kwargs = arcgis_gis_mock.GIS.call_args
    assert call_kwargs.kwargs.get("token") == "tok123" or \
           (len(call_kwargs.args) > 1 and call_kwargs.args[1] == {"token": "tok123"})
```

This test is awkward due to the lazy import pattern. Write a cleaner test:

```python
def test_connect_with_token():
    """connect(token=...) passes token= keyword to GIS(), not username/password."""
    import sys
    from unittest.mock import MagicMock, patch

    gis_mock = MagicMock()
    GIS_mock = MagicMock(return_value=gis_mock)

    with patch.dict(sys.modules, {"arcgis.gis": MagicMock(GIS=GIS_mock)}):
        # Force re-import of the function so it picks up the mock
        import importlib
        import src.arcpy_processor.auth as auth_module
        importlib.reload(auth_module)
        auth_module.connect(token="mytoken", org_url="https://test.maps.arcgis.com")

    GIS_mock.assert_called_once_with("https://test.maps.arcgis.com", token="mytoken")
```

- [ ] **Step 2: Run the test to verify it fails**

```
pytest tests/test_arcpy_auth.py::test_connect_with_token -v
```
Expected: FAIL — `TypeError: connect() got an unexpected keyword argument 'token'`

- [ ] **Step 3: Implement in auth.py**

Replace the entire `connect()` function:

```python
def connect(token: str | None = None, org_url: str | None = None) -> GIS:
    """Returner autentisert GIS-instans.

    Args:
        token:   OAuth2 access_token fra brukerens innlogging. Overstyrer .env-credentials.
        org_url: AGOL org-URL. Overstyrer AGOL_ORG_URL i .env.
    """
    from arcgis.gis import GIS

    url = org_url or os.getenv("AGOL_ORG_URL", "https://www.arcgis.com")

    if token:
        try:
            return GIS(url, token=token)
        except Exception as exc:
            raise ArcpyProcessorError(
                AUTH_FAILED,
                f"Kunne ikke koble til ArcGIS Online med token ({url}): {exc}",
            ) from exc

    username = os.getenv("AGOL_USERNAME")
    password = os.getenv("AGOL_PASSWORD")

    if not (username and username.strip()) or not (password and password.strip()):
        raise ArcpyProcessorError(
            AUTH_FAILED,
            "AGOL_USERNAME og AGOL_PASSWORD må settes i .env-filen.",
        )

    try:
        return GIS(url, username, password)
    except Exception as exc:
        raise ArcpyProcessorError(
            AUTH_FAILED,
            f"Kunne ikke logge inn på ArcGIS Online ({url}): {exc}",
        ) from exc
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_arcpy_auth.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/auth.py tests/test_arcpy_auth.py
git commit -m "feat: add optional token/org_url params to auth.connect()"
```

---

### Task 3: landxml_to_agol.py — --token / --org-url args

**Files:**
- Modify: `src/arcpy_processor/landxml_to_agol.py:76-108`
- Modify: `tests/test_landxml_to_agol.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_landxml_to_agol.py`:

```python
def test_cli_passes_token_to_connect(capsys):
    """--token arg is forwarded to auth.connect()."""
    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect") as mock_connect, \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               return_value=({"L530": [(86098.0, 1283548.0, 129.4)]}, 25833)), \
         patch("src.arcpy_processor.landxml_to_agol.create_polyline_fc",
               return_value="C:/scratch/landxml_temp.gdb/ds_centerline"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("arcpy.management.GetCount", return_value=[1]):

        mock_connect.return_value = MagicMock()
        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit):
            main(["--xml", "test.xml", "--name", "TestLag", "--folder", "",
                  "--token", "mytoken123", "--org-url", "https://myorg.maps.arcgis.com"])

    mock_connect.assert_called_once_with(token="mytoken123", org_url="https://myorg.maps.arcgis.com")
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_landxml_to_agol.py::test_cli_passes_token_to_connect -v
```
Expected: FAIL — `AssertionError` (connect called without token kwarg)

- [ ] **Step 3: Implement in landxml_to_agol.py**

In `main()`, add two arguments to the argparse block (after the `--source-epsg` line):

```python
parser.add_argument("--token", default=None,
                    help="OAuth2 access_token (overstyrer .env credentials)")
parser.add_argument("--org-url", default=None,
                    help="AGOL org-URL (overstyrer AGOL_ORG_URL i .env)")
```

Update the `connect()` call:

```python
gis = connect(token=args.token, org_url=args.org_url)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_landxml_to_agol.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/landxml_to_agol.py tests/test_landxml_to_agol.py
git commit -m "feat: add --token and --org-url args to landxml_to_agol CLI"
```

---

### Task 4: tverrprofil_to_agol.py — new publish CLI

**Files:**
- Create: `src/arcpy_processor/tverrprofil_to_agol.py`
- Create: `tests/test_tverrprofil_to_agol.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_tverrprofil_to_agol.py
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(scope="module", autouse=True)
def setup_arcpy_mock():
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.management.GetCount.return_value = [3]
    arcpy_mock.management.CreateFeatureclass.return_value = ["C:/scratch/test.gdb/test_tverrprofiler"]
    sys.modules.setdefault("arcpy", arcpy_mock)
    sys.modules.setdefault("arcpy.management", arcpy_mock.management)
    sys.modules.setdefault("arcpy.da", arcpy_mock.da)

    arcgis_mock = MagicMock()
    sys.modules.setdefault("arcgis", arcgis_mock)
    sys.modules.setdefault("arcgis.gis", MagicMock())


def _stations_json(tmp: Path) -> Path:
    p = tmp / "stations.json"
    p.write_text(json.dumps([
        {"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0},
        {"station_m": 50.0, "profil_nr": "0050.00", "x": 60.0, "y": 20.0, "z": 101.0},
    ]))
    return p


def test_cli_exits_1_when_stations_json_not_found(capsys):
    from src.arcpy_processor.tverrprofil_to_agol import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--stations-json", "nonexistent.json",
              "--svgs-dir", ".",
              "--name", "Test",
              "--folder", ""])
    assert exc_info.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == "LANDXML_NOT_FOUND"


def test_cli_prints_json_on_success(tmp_path, capsys):
    stations_path = _stations_json(tmp_path)

    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/test.gdb/test_tverrprofiler"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[2]):

        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "TestTverrprofil",
                  "--folder", "",
                  "--token", "mytoken"])
        assert exc_info.value.code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["feature_count"] == 2


def test_create_point_fc_calls_insert_cursor(tmp_path):
    """create_point_fc inserts one row per station."""
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.CreateFeatureclass.reset_mock()

    stations = [
        {"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0},
        {"station_m": 10.0, "profil_nr": "0010.00", "x": 15.0, "y": 20.0, "z": 100.5},
    ]

    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
    create_point_fc(stations, "C:/scratch/test.gdb", "myservice")

    arcpy_mock.management.CreateFeatureclass.assert_called_once()
    insert_cursor_ctx = arcpy_mock.da.InsertCursor.return_value.__enter__.return_value
    assert insert_cursor_ctx.insertRow.call_count == 2


def test_cli_passes_token_to_connect(tmp_path):
    stations_path = _stations_json(tmp_path)
    success_meta = {"status": "ok", "url": "https://x/FeatureServer",
                    "item_id": "i", "item_url": "https://x",
                    "layer_count": 1, "spatial_reference": "x",
                    "published_at": "2026-05-04T10:00:00+00:00"}

    with patch("src.arcpy_processor.auth.connect") as mock_connect, \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/t.gdb/t"), \
         patch("src.arcpy_processor.publisher.upload_and_publish", return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[1]):

        mock_connect.return_value = MagicMock()
        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit):
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "X", "--folder", "",
                  "--token", "tok999", "--org-url", "https://myorg.arcgis.com"])

    mock_connect.assert_called_once_with(token="tok999", org_url="https://myorg.arcgis.com")
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_tverrprofil_to_agol.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.arcpy_processor.tverrprofil_to_agol'`

- [ ] **Step 3: Implement tverrprofil_to_agol.py**

Create `src/arcpy_processor/tverrprofil_to_agol.py`:

```python
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

        with arcpy.da.SearchCursor(fc_path, ["OID@", "stasjon_m"]) as cur:
            for oid, station_m in cur:
                svg = svgs_dir / f"station_{station_m:07.1f}.svg"
                if svg.exists():
                    arcpy.management.AddAttachment(fc_path, oid, str(svg))
                else:
                    logger.warning("SVG ikke funnet for stasjon %.1f m: %s", station_m, svg)

        feature_count = int(arcpy.management.GetCount(fc_path)[0])
        result = upload_and_publish(gis, gdb_path, args.name, args.folder)
        result["feature_count"] = feature_count
        print(json.dumps(result))
        sys.exit(0)

    except ArcpyProcessorError as err:
        _fail(err)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_tverrprofil_to_agol.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/tverrprofil_to_agol.py tests/test_tverrprofil_to_agol.py
git commit -m "feat: add tverrprofil_to_agol CLI for publishing cross-section points to AGOL"
```

---

### Task 5: requirements.txt + auth_routes.py — OAuth2 router

**Files:**
- Modify: `requirements.txt`
- Create: `src/api/auth_routes.py`
- Create: `tests/test_api_auth.py`

- [ ] **Step 1: Add new dependencies to requirements.txt**

Add after the `python-multipart` line:

```
httpx>=0.27             # OAuth2 token exchange + AGOL self endpoint
itsdangerous>=2.1       # required by starlette SessionMiddleware
```

Install them:
```
pip install httpx>=0.27 itsdangerous>=2.1
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/test_api_auth.py
from __future__ import annotations
import os
import pytest
from unittest.mock import patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware


@pytest.fixture(autouse=True)
def set_env(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("AGOL_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("AGOL_CLIENT_SECRET", "test_secret")
    monkeypatch.setenv("AGOL_REDIRECT_URI", "http://localhost:8000/auth/callback")
    monkeypatch.setenv("AGOL_ORG_URL", "https://testkommune.maps.arcgis.com")


@pytest.fixture
def client():
    from src.api.auth_routes import router
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="test-secret-key")
    app.include_router(router, prefix="/auth")
    return TestClient(app)


def test_login_redirects_to_agol(client):
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "testkommune.maps.arcgis.com" in resp.headers["location"]
    assert "client_id=test_client_id" in resp.headers["location"]
    assert "state=" in resp.headers["location"]


def test_me_returns_401_when_not_logged_in(client):
    resp = client.get("/auth/me")
    assert resp.status_code == 401


def test_callback_rejects_invalid_state(client):
    resp = client.get("/auth/callback?code=abc&state=bad-state-no-session")
    assert resp.status_code == 400


def test_callback_sets_session(client):
    """Full flow: login → set state → callback with valid state → /me returns user."""
    # Login to establish state in session
    login_resp = client.get("/auth/login", follow_redirects=False)
    location = login_resp.headers["location"]
    params = dict(p.split("=", 1) for p in location.split("?")[1].split("&"))
    state = params["state"]

    token_mock = MagicMock()
    token_mock.raise_for_status = MagicMock()
    token_mock.json.return_value = {"access_token": "tok123", "refresh_token": "ref456"}

    user_mock = MagicMock()
    user_mock.raise_for_status = MagicMock()
    user_mock.json.return_value = {"username": "testuser", "fullName": "Test Bruker"}

    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        cb_resp = client.get(f"/auth/callback?code=xyz&state={state}",
                             follow_redirects=False)
    assert cb_resp.status_code in (302, 307)

    me_resp = client.get("/auth/me")
    assert me_resp.status_code == 200
    data = me_resp.json()
    assert data["username"] == "testuser"
    assert data["full_name"] == "Test Bruker"


def test_logout_clears_session(client):
    """After logout, /auth/me returns 401."""
    # Login
    login_resp = client.get("/auth/login", follow_redirects=False)
    state = dict(p.split("=", 1) for p in
                 login_resp.headers["location"].split("?")[1].split("&"))["state"]
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"access_token": "t", "refresh_token": "r"}))
    user_mock = MagicMock(raise_for_status=MagicMock(),
                          json=MagicMock(return_value={"username": "u", "fullName": "N"}))
    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)

    assert client.get("/auth/me").status_code == 200
    client.post("/auth/logout")
    assert client.get("/auth/me").status_code == 401
```

- [ ] **Step 3: Run tests to verify they fail**

```
pytest tests/test_api_auth.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.auth_routes'`

- [ ] **Step 4: Implement auth_routes.py**

Create `src/api/auth_routes.py`:

```python
# src/api/auth_routes.py
"""OAuth2 Authorization Code flow mot ArcGIS Online."""
from __future__ import annotations

import os
import uuid

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from starlette.requests import Request

router = APIRouter()


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


@router.get("/login")
def auth_login(request: Request) -> RedirectResponse:
    state = str(uuid.uuid4())
    request.session["oauth_state"] = state
    org_url = _env("AGOL_ORG_URL", "https://www.arcgis.com")
    url = (
        f"{org_url}/sharing/rest/oauth2/authorize"
        f"?client_id={_env('AGOL_CLIENT_ID')}"
        f"&response_type=code"
        f"&redirect_uri={_env('AGOL_REDIRECT_URI', 'http://localhost:8000/auth/callback')}"
        f"&state={state}"
    )
    return RedirectResponse(url)


@router.get("/callback")
def auth_callback(request: Request, code: str, state: str) -> RedirectResponse:
    if state != request.session.get("oauth_state"):
        raise HTTPException(400, "Ugyldig state-parameter — mulig CSRF-angrep")

    org_url = _env("AGOL_ORG_URL", "https://www.arcgis.com")

    token_resp = httpx.post(
        f"{org_url}/sharing/rest/oauth2/token",
        data={
            "client_id": _env("AGOL_CLIENT_ID"),
            "client_secret": _env("AGOL_CLIENT_SECRET"),
            "code": code,
            "redirect_uri": _env("AGOL_REDIRECT_URI", "http://localhost:8000/auth/callback"),
            "grant_type": "authorization_code",
        },
    )
    token_resp.raise_for_status()
    token_data = token_resp.json()
    access_token = token_data["access_token"]

    self_resp = httpx.get(
        f"{org_url}/sharing/rest/community/self",
        params={"f": "json", "token": access_token},
    )
    self_resp.raise_for_status()
    user = self_resp.json()

    request.session.update({
        "access_token": access_token,
        "refresh_token": token_data.get("refresh_token"),
        "username": user.get("username", ""),
        "full_name": user.get("fullName", ""),
        "org_url": org_url,
    })
    return RedirectResponse("/")


@router.get("/me")
def auth_me(request: Request) -> dict:
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget")
    return {
        "username": request.session.get("username"),
        "full_name": request.session.get("full_name"),
        "org_url": request.session.get("org_url"),
    }


@router.post("/logout")
def auth_logout(request: Request) -> dict:
    request.session.clear()
    return {"status": "ok"}
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_api_auth.py -v
```
Expected: all 5 tests PASS

- [ ] **Step 6: Commit**

```bash
git add requirements.txt src/api/auth_routes.py tests/test_api_auth.py
git commit -m "feat: add OAuth2 auth_routes with AGOL Authorization Code flow"
```

---

### Task 6: job_runner.py — background job module

**Files:**
- Create: `src/api/job_runner.py`
- Create: `tests/test_api_jobs.py` (initial, will be extended in Task 7)

- [ ] **Step 1: Write failing tests for job_runner**

```python
# tests/test_api_jobs.py
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_create_job_returns_id():
    from src.api.job_runner import create_job, get_job
    job_id = create_job()
    assert job_id is not None
    state = get_job(job_id)
    assert state is not None
    assert state.status == "queued"


def test_get_job_unknown_returns_none():
    from src.api.job_runner import get_job
    assert get_job("does-not-exist-xyz") is None


def test_run_job_success(tmp_path):
    """run_job sets status=done after successful pipeline + subprocesses."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"
    fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"
    fake_xml.write_text("")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    meta = {"stations": [{"station": 0.0}, {"station": 10.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [str(output_dir / "station_0000000.0.svg")],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl/FeatureServer"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp/FeatureServer"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp]):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestJob",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
        )

    state = get_job(job_id)
    assert state.status == "done"
    assert state.progress_pct == 100
    assert state.centerline_url == "https://agol/cl/FeatureServer"
    assert state.sections_url == "https://agol/tp/FeatureServer"


def test_run_job_sets_failed_on_subprocess_error(tmp_path):
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"
    fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"
    fake_xml.write_text("")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, "cmd", stderr="AGOL feilet")):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestFail",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
        )

    state = get_job(job_id)
    assert state.status == "failed"
    assert "AGOL feilet" in state.error
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_jobs.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'src.api.job_runner'`

- [ ] **Step 3: Implement job_runner.py**

Create `src/api/job_runner.py`:

```python
# src/api/job_runner.py
"""Bakgrunnsjobb-orkestrator for IFC → AGOL pipeline."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "done", "failed"]


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress_pct: int = 0
    message: str = "Venter…"
    centerline_url: str | None = None
    sections_url: str | None = None
    error: str | None = None


_jobs: dict[str, JobState] = {}


def create_job() -> str:
    """Opprett ny jobb og returner job_id."""
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobState(job_id=job_id, message="Starter pipeline…")
    return job_id


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def _update(state: JobState, pct: int, msg: str) -> None:
    state.progress_pct = pct
    state.message = msg
    logger.info("[%s] %d%% %s", state.job_id, pct, msg)


def run_job(
    job_id: str,
    ifc_path: Path,
    xml_path: Path,
    name: str,
    interval: float,
    access_token: str,
    org_url: str,
    output_dir: Path,
) -> None:
    """Kjør full pipeline i bakgrunnen. Oppdaterer jobbstatus underveis."""
    from src.ifc_processor.pipeline import run_pipeline

    state = _jobs[job_id]
    state.status = "running"

    try:
        _update(state, 0, "Starter pipeline…")
        _update(state, 5, "Kjører IFC-prosessering…")

        pipeline_result = run_pipeline(
            ifc_path=ifc_path,
            centerline_path=xml_path,
            output_dir=output_dir,
            interval_m=interval,
        )

        meta = json.loads(Path(pipeline_result["metadata"]).read_text())
        n_sections = len(meta["stations"])
        _update(state, 50, f"Genererte {n_sections} tverrprofiler")

        _update(state, 55, "Publiserer senterlinje til AGOL…")
        cl_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
                "--xml", str(xml_path),
                "--name", f"{name}_senterlinje",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        cl_result = json.loads(cl_proc.stdout)
        state.centerline_url = cl_result.get("url")
        _update(state, 70, "Senterlinje publisert til AGOL")

        _update(state, 75, "Publiserer tverrprofiler til AGOL…")
        tp_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.tverrprofil_to_agol",
                "--stations-json", pipeline_result["stations_json"],
                "--svgs-dir", str(output_dir),
                "--name", f"{name}_tverrprofiler",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        tp_result = json.loads(tp_proc.stdout)
        state.sections_url = tp_result.get("url")
        _update(state, 100, f"Ferdig — {n_sections} profiler publisert")
        state.status = "done"

    except subprocess.CalledProcessError as exc:
        state.status = "failed"
        state.error = exc.stderr or f"Subprocess feilet med kode {exc.returncode}"
        logger.error("[%s] Subprocess feilet: %s", job_id, state.error)
    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        logger.error("[%s] Jobb feilet: %s", job_id, exc, exc_info=True)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_api_jobs.py -v
```
Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/job_runner.py tests/test_api_jobs.py
git commit -m "feat: add job_runner background job orchestrator"
```

---

### Task 7: server.py — add auth, jobs, session middleware

**Files:**
- Modify: `src/api/server.py`
- Modify: `tests/test_api_jobs.py` (add HTTP-level tests)

**Note:** The old `POST /api/upload` endpoint and `JOBS` dict are removed. If `tests/test_smoke.py` tests `/api/upload`, those tests will need to be removed or updated.

- [ ] **Step 1: Write failing HTTP-level tests**

Add to `tests/test_api_jobs.py`:

```python
import io
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def set_env_for_server(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("AGOL_CLIENT_ID", "test_client")
    monkeypatch.setenv("AGOL_ORG_URL", "https://test.maps.arcgis.com")


@pytest.fixture
def client():
    from src.api.server import app
    return TestClient(app)


def _login(client):
    """Simulate OAuth2 login via mocked AGOL callbacks."""
    login_resp = client.get("/auth/login", follow_redirects=False)
    params = dict(p.split("=", 1) for p in
                  login_resp.headers["location"].split("?")[1].split("&"))
    state = params["state"]
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"access_token": "tok", "refresh_token": "r"}))
    user_mock = MagicMock(raise_for_status=MagicMock(),
                          json=MagicMock(return_value={"username": "u", "fullName": "N"}))
    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_post_jobs_requires_auth(client):
    resp = client.post(
        "/api/jobs",
        data={"name": "Test", "interval": "10"},
        files={"ifc_file": ("m.ifc", io.BytesIO(b"fake")),
               "xml_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 401


def test_post_jobs_validates_file_type(client):
    _login(client)
    resp = client.post(
        "/api/jobs",
        data={"name": "Test", "interval": "10"},
        files={"ifc_file": ("model.txt", io.BytesIO(b"bad")),
               "xml_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 400


def test_post_jobs_creates_job_and_returns_id(client):
    _login(client)
    with patch("src.api.job_runner.run_job"):  # prevent actual execution
        resp = client.post(
            "/api/jobs",
            data={"name": "TestService", "interval": "10"},
            files={"ifc_file": ("model.ifc", io.BytesIO(b"fake")),
                   "xml_file": ("cl.xml", io.BytesIO(b"<xml/>"))},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_get_job_status_queued(client):
    _login(client)
    with patch("src.api.job_runner.run_job"):
        create_resp = client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "xml_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "status" in data
    assert "progress_pct" in data
    assert "message" in data
    assert "centerline_url" in data
    assert "sections_url" in data
    assert "error" in data


def test_get_job_404_for_unknown(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_api_jobs.py::test_health tests/test_api_jobs.py::test_post_jobs_requires_auth -v
```
Expected: FAIL — import errors or missing routes

- [ ] **Step 3: Rewrite server.py**

Replace `src/api/server.py` with:

```python
"""FastAPI-server for SVV IFC Profiler.

Endepunkter:
    GET  /api/health          → helsesjekk
    GET  /auth/login          → OAuth2 innlogging (redirect til AGOL)
    GET  /auth/callback       → OAuth2 callback (bytt code mot token)
    GET  /auth/me             → innlogget brukerinfo (fra session)
    POST /auth/logout         → logg ut (slett session)
    POST /api/jobs            → start ny pipeline-jobb
    GET  /api/jobs/{id}       → jobbstatus
"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

load_dotenv()

from .auth_routes import router as auth_router
from . import job_runner

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="SVV IFC Profiler API",
    description="Generer tverr- og lengdeprofiler fra IFC-modeller iht. R700.",
    version="0.2.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router, prefix="/auth")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    ifc_file: UploadFile = File(...),
    xml_file: UploadFile = File(...),
    name: str = Form(...),
    interval: float = Form(10.0),
) -> dict:
    """Motta IFC + LandXML, start pipeline-jobb i bakgrunnen."""
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget — bruk /auth/login")
    if not ifc_file.filename or not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "ifc_file må være en .ifc-fil")
    if not xml_file.filename or not xml_file.filename.lower().endswith(".xml"):
        raise HTTPException(400, "xml_file må være en .xml LandXML-fil")
    if not (1 <= interval <= 100):
        raise HTTPException(400, "interval må være mellom 1 og 100 meter")

    job_id = job_runner.create_job()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    ifc_path = job_dir / "model.ifc"
    xml_path = job_dir / "centerline.xml"

    with ifc_path.open("wb") as f:
        while chunk := await ifc_file.read(1024 * 1024):
            f.write(chunk)
    with xml_path.open("wb") as f:
        while chunk := await xml_file.read(1024 * 1024):
            f.write(chunk)

    background_tasks.add_task(
        job_runner.run_job,
        job_id=job_id,
        ifc_path=ifc_path,
        xml_path=xml_path,
        name=name,
        interval=interval,
        access_token=request.session["access_token"],
        org_url=request.session.get("org_url", "https://www.arcgis.com"),
        output_dir=job_dir / "output",
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    state = job_runner.get_job(job_id)
    if state is None:
        raise HTTPException(404, "Jobb ikke funnet")
    return {
        "status": state.status,
        "progress_pct": state.progress_pct,
        "message": state.message,
        "centerline_url": state.centerline_url,
        "sections_url": state.sections_url,
        "error": state.error,
    }
```

- [ ] **Step 4: Check if test_smoke.py references /api/upload and update it**

```
pytest tests/test_smoke.py -v
```

If tests fail due to removed `/api/upload`, either delete those tests or replace with a `/api/health` check. The upload workflow now goes through `/api/jobs`.

- [ ] **Step 5: Run all tests**

```
pytest tests/test_api_jobs.py tests/test_api_auth.py -v
```
Expected: all HTTP-level tests PASS

- [ ] **Step 6: Run full test suite**

```
pytest -v
```
Expected: all tests PASS (skip tests needing real IFC/AGOL)

- [ ] **Step 7: Commit**

```bash
git add src/api/server.py tests/test_api_jobs.py
git commit -m "feat: extend server with SessionMiddleware, auth router, POST /api/jobs"
```
