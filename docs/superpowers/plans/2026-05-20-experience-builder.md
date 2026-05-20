# Experience Builder Profilutforsker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the tverrprofil publish pipeline to backfill `svg_url` attachment URLs on published AGOL feature layers, then create or update an ArcGIS Experience Builder app configured with Map, List, Feature Info, and Embedded Content widgets.

**Architecture:** A new `experience_builder.py` module in `src/arcpy_processor/` provides two functions: `backfill_svg_urls()` queries each AGOL feature's existing SVG attachment and writes the URL back as an attribute field; `create_or_update_experience()` substitutes item-ID placeholders in a config.json template and creates/updates a Web Experience item. Both are called from the existing pipeline after tverrprofil publish succeeds, and wrap their failures as warnings so the main job never fails due to XB issues.

**Tech Stack:** `arcgis` Python API ≥ 2.2 (`arcgis.features.FeatureLayer`, `arcgis.apps.expbuilder.WebExperience`), pytest with `unittest.mock`.

---

## File map

| File | Change |
|------|--------|
| `src/arcpy_processor/tverrprofil_to_agol.py` | Add `svg_url TEXT` field in `create_point_fc()`; call `backfill_svg_urls()` after publish |
| `src/arcpy_processor/experience_builder.py` | **New** — `_attachment_url`, `backfill_svg_urls`, `create_or_update_experience` |
| `src/api/job_runner.py` | Add `xb_url` to `JobState`; call `create_or_update_experience()` after tverrprofil publish |
| `src/api/server.py` | Return `xb_url` in `/api/jobs/{id}` and `/api/jobs` responses |
| `templates/xb_config_template.json` | **Manual** — created once in XB browser editor |
| `templates/.gitkeep` | **New** — ensures `templates/` is tracked by git |
| `tests/test_experience_builder.py` | **New** — unit tests for the new module |
| `tests/test_api_jobs.py` | Extend: assert `xb_url` in job state and API response |

---

### Task 1: Add `svg_url` field to GDB feature class schema

The tverrprofil feature class needs a `svg_url TEXT(512)` field so AGOL has a place to store the attachment URL after publish. Attachments are already added via ArcPy in the GDB; this task only adds the empty field.

**Files:**
- Modify: `src/arcpy_processor/tverrprofil_to_agol.py:58-82`
- Modify: `tests/test_tverrprofil_to_agol.py`

- [ ] **Step 1: Write the failing test**

Add this test to `tests/test_tverrprofil_to_agol.py`:

```python
def test_create_point_fc_adds_svg_url_field():
    """create_point_fc must add a svg_url field so AGOL can store attachment URLs."""
    import arcpy
    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc

    stations = [{"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0}]

    arcpy.da.InsertCursor.return_value.__enter__ = lambda s: s
    arcpy.da.InsertCursor.return_value.__exit__ = MagicMock(return_value=False)
    arcpy.da.InsertCursor.return_value.__iter__ = MagicMock(return_value=iter([]))
    arcpy.da.SearchCursor.return_value.__enter__ = lambda s: s
    arcpy.da.SearchCursor.return_value.__exit__ = MagicMock(return_value=False)
    arcpy.da.SearchCursor.return_value.__iter__ = MagicMock(return_value=iter([]))

    create_point_fc(stations, "C:/scratch/test.gdb", "vei")

    field_names = [
        call_args[0][1]
        for call_args in arcpy.management.AddField.call_args_list
    ]
    assert "svg_url" in field_names, f"svg_url not in AddField calls: {field_names}"
```

- [ ] **Step 2: Run the test to confirm it fails**

```
pytest tests/test_tverrprofil_to_agol.py::test_create_point_fc_adds_svg_url_field -v
```

Expected: `FAILED` — svg_url not in AddField calls

- [ ] **Step 3: Add the `svg_url` field in `create_point_fc()`**

In `src/arcpy_processor/tverrprofil_to_agol.py`, after the four existing `AddField` calls (around line 65), add one line:

```python
    arcpy.management.AddField(fc_path, "stasjon_m", "DOUBLE")
    arcpy.management.AddField(fc_path, "profil_nr", "TEXT", field_length=20)
    arcpy.management.AddField(fc_path, "z_moh", "DOUBLE")
    arcpy.management.AddField(fc_path, "z_terreng", "DOUBLE")
    arcpy.management.AddField(fc_path, "svg_url", "TEXT", field_length=512)
```

- [ ] **Step 4: Run the test to confirm it passes**

```
pytest tests/test_tverrprofil_to_agol.py::test_create_point_fc_adds_svg_url_field -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full test suite to check for regressions**

```
pytest tests/test_tverrprofil_to_agol.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/arcpy_processor/tverrprofil_to_agol.py tests/test_tverrprofil_to_agol.py
git commit -m "feat: add svg_url field to tverrprofil GDB feature class schema"
```

---

### Task 2: New module — `_attachment_url` and `backfill_svg_urls`

`backfill_svg_urls(layer)` queries all features in a published AGOL FeatureLayer, finds each feature's first SVG attachment, constructs the REST URL, and writes it back via `edit_features`. The private `_attachment_url` helper keeps URL construction testable.

**Files:**
- Create: `src/arcpy_processor/experience_builder.py`
- Create: `tests/test_experience_builder.py`

- [ ] **Step 1: Create the test file with failing tests**

Create `tests/test_experience_builder.py`:

```python
# tests/test_experience_builder.py
from __future__ import annotations
import sys
from unittest.mock import MagicMock
import pytest

# Mock arcgis at module level before any imports
_arcgis_mock = MagicMock()
sys.modules.setdefault("arcgis", _arcgis_mock)
sys.modules.setdefault("arcgis.features", _arcgis_mock.features)
sys.modules.setdefault("arcgis.gis", _arcgis_mock.gis)
sys.modules.setdefault("arcgis.apps", _arcgis_mock.apps)
sys.modules.setdefault("arcgis.apps.expbuilder", _arcgis_mock.apps.expbuilder)


def _make_layer(oids_with_attachments: dict) -> MagicMock:
    layer = MagicMock()
    layer.url = "https://services.arcgis.com/xxx/FeatureServer/0"
    features = []
    for oid in oids_with_attachments:
        feat = MagicMock()
        feat.attributes = {"OBJECTID": oid}
        features.append(feat)
    layer.query.return_value.features = features
    layer.attachments.search.side_effect = list(oids_with_attachments.values())
    return layer


def test_attachment_url_format():
    from src.arcpy_processor.experience_builder import _attachment_url
    result = _attachment_url("https://services.arcgis.com/xxx/FeatureServer/0", 42, 101)
    assert result == "https://services.arcgis.com/xxx/FeatureServer/0/42/attachments/101"


def test_backfill_returns_count():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({
        1: [{"id": 101, "name": "tverrprofil_0000.0.svg"}],
        2: [{"id": 102, "name": "tverrprofil_0050.0.svg"}],
    })
    assert backfill_svg_urls(layer) == 2


def test_backfill_calls_edit_features_once():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({1: [{"id": 101, "name": "station.svg"}]})
    backfill_svg_urls(layer)
    layer.edit_features.assert_called_once()
    call = layer.edit_features.call_args
    updates = call.kwargs.get("updates") or call.args[0]
    assert len(updates) == 1


def test_backfill_skips_non_svg_attachments():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({
        1: [{"id": 201, "name": "photo.png"}],   # not SVG — skip
        2: [{"id": 102, "name": "tverrprofil.svg"}],
    })
    assert backfill_svg_urls(layer) == 1


def test_backfill_no_attachments_does_not_call_edit_features():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({1: [], 2: []})
    assert backfill_svg_urls(layer) == 0
    layer.edit_features.assert_not_called()
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
pytest tests/test_experience_builder.py -v
```

Expected: `ERROR` — cannot import `experience_builder`

- [ ] **Step 3: Create `src/arcpy_processor/experience_builder.py`**

```python
# src/arcpy_processor/experience_builder.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arcgis.features import FeatureLayer
    from arcgis.gis import GIS

logger = logging.getLogger(__name__)


def _attachment_url(layer_url: str, oid: int, attachment_id: int) -> str:
    return f"{layer_url}/{oid}/attachments/{attachment_id}"


def backfill_svg_urls(layer: "FeatureLayer") -> int:
    """Query AGOL attachment info per feature and write the SVG URL to svg_url field.

    Returns number of features updated.
    """
    from arcgis.features import Feature

    fset = layer.query(where="1=1", out_fields="OBJECTID", return_geometry=False)
    updates = []

    for feat in fset.features:
        oid = feat.attributes["OBJECTID"]
        attachments = layer.attachments.search(oid)
        svg_att = next(
            (a for a in attachments if str(a.get("name", "")).lower().endswith(".svg")),
            None,
        )
        if svg_att is None:
            logger.warning("Ingen SVG-attachment funnet for OID %d", oid)
            continue
        url = _attachment_url(layer.url, oid, svg_att["id"])
        updates.append(Feature(attributes={"OBJECTID": oid, "svg_url": url}))

    if updates:
        layer.edit_features(updates=updates)
        logger.info("svg_url oppdatert for %d features", len(updates))

    return len(updates)
```

- [ ] **Step 4: Run the tests to confirm they pass**

```
pytest tests/test_experience_builder.py -v
```

Expected: all 5 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/experience_builder.py tests/test_experience_builder.py
git commit -m "feat: add experience_builder module with backfill_svg_urls"
```

---

### Task 3: Add `create_or_update_experience()` to `experience_builder.py`

Reads a config.json template file, substitutes three placeholders, then creates or updates a Web Experience item on AGOL and publishes it. If the item already exists (matched by exact title), it is updated instead of duplicated.

**Files:**
- Modify: `src/arcpy_processor/experience_builder.py`
- Modify: `tests/test_experience_builder.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_experience_builder.py`:

```python
def test_create_experience_when_none_exists(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text(
        '{"cl": "__CENTERLINE_ITEM_ID__", "sec": "__SECTIONS_ITEM_ID__", "url": "__SERVICE_URL__"}'
    )

    gis = MagicMock()
    gis.content.search.return_value = []

    mock_exp = MagicMock()
    mock_exp.item.homepage = "https://experience.arcgis.com/builder/?id=new123"
    _arcgis_mock.apps.expbuilder.WebExperience.return_value = mock_exp

    url = create_or_update_experience(
        gis=gis,
        name="Profilutforsker",
        centerline_item_id="CL_ID",
        sections_item_id="SEC_ID",
        sections_service_url="https://services/FS",
        template_path=template,
    )

    mock_exp.create.assert_called_once()
    assert url == "https://experience.arcgis.com/builder/?id=new123"


def test_update_experience_when_exists(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text('{"sec": "__SECTIONS_ITEM_ID__"}')

    existing = MagicMock()
    existing.title = "Profilutforsker"
    existing.id = "existing456"
    existing.homepage = "https://experience.arcgis.com/builder/?id=existing456"

    gis = MagicMock()
    gis.content.search.return_value = [existing]

    url = create_or_update_experience(
        gis=gis,
        name="Profilutforsker",
        centerline_item_id="CL",
        sections_item_id="SEC",
        sections_service_url="https://svc/FS",
        template_path=template,
    )

    existing.update.assert_called_once()
    data_arg = (
        existing.update.call_args.kwargs.get("data")
        or existing.update.call_args.args[0]
    )
    assert "SEC" in data_arg
    assert "__SECTIONS_ITEM_ID__" not in data_arg
    assert url == "https://experience.arcgis.com/builder/?id=existing456"


def test_config_placeholders_all_substituted(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text(
        '{"a":"__CENTERLINE_ITEM_ID__","b":"__SECTIONS_ITEM_ID__","c":"__SERVICE_URL__"}'
    )

    gis = MagicMock()
    gis.content.search.return_value = []
    mock_exp = MagicMock()
    mock_exp.item.homepage = "https://arcgis.com/apps/exp"
    _arcgis_mock.apps.expbuilder.WebExperience.return_value = mock_exp

    create_or_update_experience(
        gis=gis,
        name="Test",
        centerline_item_id="AAA",
        sections_item_id="BBB",
        sections_service_url="https://CCC",
        template_path=template,
    )

    data_arg = (
        mock_exp.item.update.call_args.kwargs.get("data")
        or mock_exp.item.update.call_args.args[0]
    )
    assert "AAA" in data_arg
    assert "BBB" in data_arg
    assert "https://CCC" in data_arg
    assert "__CENTERLINE_ITEM_ID__" not in data_arg
    assert "__SECTIONS_ITEM_ID__" not in data_arg
    assert "__SERVICE_URL__" not in data_arg
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
pytest tests/test_experience_builder.py::test_create_experience_when_none_exists tests/test_experience_builder.py::test_update_experience_when_exists tests/test_experience_builder.py::test_config_placeholders_all_substituted -v
```

Expected: `FAILED` — cannot import `create_or_update_experience`

- [ ] **Step 3: Add `create_or_update_experience()` to `experience_builder.py`**

Append to the end of `src/arcpy_processor/experience_builder.py`:

```python


def create_or_update_experience(
    gis: "GIS",
    name: str,
    centerline_item_id: str,
    sections_item_id: str,
    sections_service_url: str,
    template_path: Path,
) -> str:
    """Create or update an Experience Builder app on AGOL from a config.json template.

    Placeholders in the template:
        __CENTERLINE_ITEM_ID__  → centerline_item_id
        __SECTIONS_ITEM_ID__    → sections_item_id
        __SERVICE_URL__         → sections_service_url

    Returns the item homepage URL.
    """
    from arcgis.apps.expbuilder import WebExperience

    config_json = (
        template_path.read_text(encoding="utf-8")
        .replace("__CENTERLINE_ITEM_ID__", centerline_item_id)
        .replace("__SECTIONS_ITEM_ID__", sections_item_id)
        .replace("__SERVICE_URL__", sections_service_url)
    )

    existing = gis.content.search(
        query=f'title:"{name}" type:"Web Experience"',
        max_items=5,
    )
    exp_item = next((i for i in existing if i.title == name), None)

    if exp_item is None:
        exp = WebExperience(gis=gis)
        exp.create(title=name, tags=["IFC", "SVV", "tverrprofil", "R700"])
        exp_item = exp.item
        logger.info("Opprettet ny XB-app '%s' (%s)", name, exp_item.id)
    else:
        logger.info("Oppdaterer eksisterende XB-app '%s' (%s)", name, exp_item.id)

    exp_item.update(data=config_json)

    try:
        WebExperience(exp_item).publish()
    except Exception as exc:
        logger.warning("XB publish() feilet (%s) — konfigurasjonen er oppdatert", exc)

    return exp_item.homepage
```

- [ ] **Step 4: Run all experience_builder tests**

```
pytest tests/test_experience_builder.py -v
```

Expected: all 8 tests `PASSED`

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/experience_builder.py tests/test_experience_builder.py
git commit -m "feat: add create_or_update_experience to experience_builder module"
```

---

### Task 4: Wire `backfill_svg_urls()` into `tverrprofil_to_agol.py` main()

After `upload_and_publish()` returns, call `backfill_svg_urls()` on layer 0 of the published feature service. Failures are caught and logged as warnings — the CLI still exits 0 and returns a valid JSON result.

**Files:**
- Modify: `src/arcpy_processor/tverrprofil_to_agol.py:190-218`
- Modify: `tests/test_tverrprofil_to_agol.py`

- [ ] **Step 1: Add a failing test**

Append to `tests/test_tverrprofil_to_agol.py`:

```python
def test_cli_calls_backfill_svg_urls_after_publish(tmp_path, capsys):
    stations_path = _stations_json(tmp_path)

    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    mock_backfill = MagicMock(return_value=2)

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/test.gdb/test_tverrprofiler"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("src.arcpy_processor.experience_builder.backfill_svg_urls",
               mock_backfill):
        from src.arcpy_processor.tverrprofil_to_agol import main
        main(["--stations-json", str(stations_path),
              "--svgs-dir", str(tmp_path),
              "--name", "Test",
              "--folder", "",
              "--token", "tok123"])

    mock_backfill.assert_called_once()
```

- [ ] **Step 2: Run the test to confirm it fails**

```
pytest tests/test_tverrprofil_to_agol.py::test_cli_calls_backfill_svg_urls_after_publish -v
```

Expected: `FAILED` — `mock_backfill.assert_called_once()` fails

- [ ] **Step 3: Add the backfill call in `main()`**

In `src/arcpy_processor/tverrprofil_to_agol.py`, find the block that queries UTM33 stations (around line 193). After that entire try/except block (around line 215), and before `print(json.dumps(result))`, add:

```python
        # Backfill svg_url attribute from AGOL attachment URLs
        try:
            from arcgis.features import FeatureLayer
            from .experience_builder import backfill_svg_urls
            sections_lyr = FeatureLayer(result["url"] + "/0", gis=gis)
            n_updated = backfill_svg_urls(sections_lyr)
            logger.info("svg_url backfilled for %d features", n_updated)
            result["svg_url_count"] = n_updated
        except Exception as exc:
            logger.warning("svg_url backfill feilet: %s", exc)

        print(json.dumps(result))
```

Make sure to remove or adjust the existing `print(json.dumps(result))` that was already there (it should now only appear once, after the backfill block).

- [ ] **Step 4: Run the failing test to confirm it passes**

```
pytest tests/test_tverrprofil_to_agol.py::test_cli_calls_backfill_svg_urls_after_publish -v
```

Expected: `PASSED`

- [ ] **Step 5: Run the full tverrprofil test suite**

```
pytest tests/test_tverrprofil_to_agol.py -v
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/arcpy_processor/tverrprofil_to_agol.py tests/test_tverrprofil_to_agol.py
git commit -m "feat: call backfill_svg_urls after tverrprofil publish"
```

---

### Task 5: Add `xb_url` to `JobState` and wire XB creation in `job_runner.py`

`xb_url` is added to `JobState` and persisted in `job_state.json` and `agol_urls.json`. After both centerline and tverrprofil publish succeed, `create_or_update_experience()` is called in a try/except — failure downgrades to `done_with_warnings` but never to `failed`.

**Files:**
- Modify: `src/api/job_runner.py`
- Modify: `tests/test_api_jobs.py`

- [ ] **Step 1: Add `xb_url` to `JobState` and `_persist_state`**

In `src/api/job_runner.py`, in the `JobState` dataclass (around line 32), add after `bim_url`:

```python
    xb_url: str | None = None
```

In `_persist_state()` (around line 61), in the `json.dumps({...})` dict, add:

```python
                "xb_url": state.xb_url,
```

In `_persist_agol_urls()` (the inner function inside `run_job`, around line 214), update to include `xb_url`:

```python
        def _persist_agol_urls() -> None:
            """Skriv agol_urls.json med alle tilgjengelige URL-er."""
            _agol = {k: v for k, v in {
                "centerline_url": state.centerline_url,
                "sections_url": state.sections_url,
                "bim_url": state.bim_url,
                "xb_url": state.xb_url,
            }.items() if v}
            if _agol:
                (output_dir / "agol_urls.json").write_text(
                    json.dumps(_agol), encoding="utf-8"
                )
```

- [ ] **Step 2: Write a failing test for `xb_url` in job state**

Open `tests/test_api_jobs.py` and add:

```python
def test_job_state_has_xb_url_field():
    from src.api.job_runner import JobState
    state = JobState(job_id="test-123")
    assert state.xb_url is None


def test_persist_state_includes_xb_url(tmp_path):
    from src.api.job_runner import JobState, _persist_state
    state = JobState(job_id="test-456", output_dir=tmp_path)
    state.xb_url = "https://experience.arcgis.com/builder/?id=abc"
    _persist_state(state)
    data = json.loads((tmp_path / "job_state.json").read_text())
    assert data["xb_url"] == "https://experience.arcgis.com/builder/?id=abc"
```

(Add `import json` at the top of the test file if not already there.)

- [ ] **Step 3: Run the tests to confirm they pass**

```
pytest tests/test_api_jobs.py::test_job_state_has_xb_url_field tests/test_api_jobs.py::test_persist_state_includes_xb_url -v
```

Expected: both `PASSED` (they test structural changes already made in Step 1)

- [ ] **Step 4: Wire `create_or_update_experience()` after tverrprofil publish**

In `run_job()`, after the `if include_tverrprofil:` block (around line 205, after `_persist_agol_urls()` call), add a new block before the `if publish_bim:` check:

```python
        # Create / update Experience Builder app
        _xb_template = Path(__file__).parent.parent.parent / "templates" / "xb_config_template.json"
        if (
            include_tverrprofil
            and state.centerline_url
            and state.sections_url
            and _xb_template.exists()
        ):
            _update(state, 88, "Oppretter Experience Builder-app…")
            try:
                from arcgis.gis import GIS as _GIS
                from src.arcpy_processor.experience_builder import create_or_update_experience
                _gis = _GIS(url=org_url, token=access_token)
                state.xb_url = create_or_update_experience(
                    gis=_gis,
                    name=f"{name}_profilutforsker",
                    centerline_item_id=cl_result.get("item_id", ""),
                    sections_item_id=tp_result.get("item_id", ""),
                    sections_service_url=tp_result.get("url", ""),
                    template_path=_xb_template,
                )
                logger.info("[%s] XB-app URL: %s", job_id, state.xb_url)
            except Exception as _xb_exc:
                logger.warning("[%s] XB-app oppretting feilet: %s", job_id, _xb_exc)
            _persist_agol_urls()
```

Note: `cl_result` and `tp_result` are local variables already set earlier in `run_job()`.

- [ ] **Step 5: Write a test that verifies XB creation is skipped when template is absent**

Append to `tests/test_api_jobs.py`:

```python
def test_run_job_skips_xb_when_template_missing(tmp_path):
    """XB creation is silently skipped if the template file does not exist."""
    import json
    from unittest.mock import patch, MagicMock

    # Minimal mock setup matching run_job's subprocess calls
    mock_cl_result = {
        "url": "https://services/CL/FeatureServer",
        "item_id": "cl_id",
        "utm33_centerline_paths": [],
    }
    mock_tp_result = {
        "url": "https://services/TP/FeatureServer",
        "item_id": "tp_id",
        "utm33_stations": [],
    }

    mock_pipeline_result = {
        "metadata": str(tmp_path / "meta.json"),
        "stations_json": str(tmp_path / "stations.json"),
    }
    (tmp_path / "meta.json").write_text(json.dumps({"stations": [{"station": 0.0}]}))
    (tmp_path / "stations.json").write_text(json.dumps([]))

    with patch("src.api.job_runner.run_pipeline", return_value=mock_pipeline_result), \
         patch("src.api.job_runner.parse_landxml", return_value=(MagicMock(), 25833)), \
         patch("src.api.job_runner.subprocess.run") as mock_sub:

        mock_sub.side_effect = [
            MagicMock(stdout=json.dumps(mock_cl_result), stderr=""),
            MagicMock(stdout=json.dumps(mock_tp_result), stderr=""),
        ]

        from src.api import job_runner
        job_runner.create_job.__module__  # ensure module loaded
        job_id = job_runner.create_job()
        job_runner._jobs[job_id].output_dir = tmp_path / "output"

        job_runner.run_job(
            job_id=job_id,
            ifc_path=tmp_path / "model.ifc",
            xml_path=tmp_path / "cl.xml",
            name="TestProject",
            interval=10.0,
            access_token="tok",
            org_url="https://www.arcgis.com",
            output_dir=tmp_path / "output",
        )

    state = job_runner.get_job(job_id)
    assert state.xb_url is None   # template missing → skipped
    assert state.status in ("done", "done_with_warnings")
```

- [ ] **Step 6: Run the new test**

```
pytest tests/test_api_jobs.py::test_run_job_skips_xb_when_template_missing -v
```

Expected: `PASSED`

- [ ] **Step 7: Run the full test suite**

```
pytest tests/ -v --tb=short
```

Expected: all tests pass (or existing failures unchanged).

- [ ] **Step 8: Commit**

```bash
git add src/api/job_runner.py tests/test_api_jobs.py
git commit -m "feat: add xb_url to JobState and wire XB experience creation in pipeline"
```

---

### Task 6: Expose `xb_url` in `server.py` API responses

Two endpoints return job data: `GET /api/jobs/{id}` and `GET /api/jobs`. Both must include `xb_url`.

**Files:**
- Modify: `src/api/server.py:142-155` (`get_job`) and `src/api/server.py:158-190` (`list_jobs`)
- Modify: `tests/test_api_jobs.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_api_jobs.py`:

```python
def test_get_job_response_includes_xb_url():
    from fastapi.testclient import TestClient
    from src.api.server import app
    from src.api import job_runner

    job_id = job_runner.create_job()
    state = job_runner._jobs[job_id]
    state.status = "done"
    state.xb_url = "https://experience.arcgis.com/builder/?id=xyz"

    client = TestClient(app)
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["xb_url"] == "https://experience.arcgis.com/builder/?id=xyz"


def test_list_jobs_response_includes_xb_url(tmp_path):
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    import json as _json

    job_id = "test-list-xb"
    output_dir = tmp_path / job_id / "output"
    output_dir.mkdir(parents=True)

    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(_json.dumps(meta))

    agol_urls = {
        "centerline_url": "https://cl",
        "sections_url": "https://sec",
        "xb_url": "https://experience.arcgis.com/builder/?id=abc",
    }
    (output_dir / "agol_urls.json").write_text(_json.dumps(agol_urls))

    from src.api.server import app
    client = TestClient(app)

    with patch("src.api.server.UPLOAD_DIR", tmp_path):
        resp = client.get("/api/jobs")

    assert resp.status_code == 200
    jobs = resp.json()
    match = next((j for j in jobs if j["job_id"] == job_id), None)
    assert match is not None
    assert match["xb_url"] == "https://experience.arcgis.com/builder/?id=abc"
```

- [ ] **Step 2: Run the tests to confirm they fail**

```
pytest tests/test_api_jobs.py::test_get_job_response_includes_xb_url tests/test_api_jobs.py::test_list_jobs_response_includes_xb_url -v
```

Expected: `FAILED` — `xb_url` not in response

- [ ] **Step 3: Update `get_job()` in `server.py`**

In `src/api/server.py`, in the `get_job()` function (around line 142), add `xb_url` to the returned dict:

```python
    return {
        "status": state.status,
        "progress_pct": state.progress_pct,
        "message": state.message,
        "centerline_url": state.centerline_url,
        "sections_url": state.sections_url,
        "bim_url": state.bim_url,
        "xb_url": state.xb_url,
        "error": state.error,
    }
```

- [ ] **Step 4: Update `list_jobs()` in `server.py`**

In `src/api/server.py`, in the `list_jobs()` function (around line 175), add `xb_url` to the appended dict:

```python
                result.append({
                    "job_id": d.name,
                    "n_stations": len(meta.get("stations", [])),
                    "modified": meta_file.stat().st_mtime,
                    "centerline_url": agol_urls.get("centerline_url"),
                    "sections_url": agol_urls.get("sections_url"),
                    "bim_url": agol_urls.get("bim_url"),
                    "xb_url": agol_urls.get("xb_url"),
                })
```

- [ ] **Step 5: Run the new tests**

```
pytest tests/test_api_jobs.py::test_get_job_response_includes_xb_url tests/test_api_jobs.py::test_list_jobs_response_includes_xb_url -v
```

Expected: both `PASSED`

- [ ] **Step 6: Run the full test suite**

```
pytest tests/ -v --tb=short
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/api/server.py tests/test_api_jobs.py
git commit -m "feat: expose xb_url in /api/jobs and /api/jobs/{id} responses"
```

---

### Task 7: Create templates directory and XB config template

This task is **manual** — it requires opening the ArcGIS Experience Builder browser editor and building the app layout. The Python code from Tasks 2–6 is already wired to read `templates/xb_config_template.json`; if the file is absent the XB creation step is silently skipped (see Task 5 Step 4).

**Files:**
- Create: `templates/.gitkeep` (tracked by git)
- Create: `templates/xb_config_template.json` (created manually, then committed)

- [ ] **Step 1: Create `templates/` directory**

```bash
mkdir templates
echo "" > templates/.gitkeep
git add templates/.gitkeep
git commit -m "chore: add templates/ directory for XB config template"
```

- [ ] **Step 2: Build the XB app layout in the browser**

1. Log into your AGOL organization
2. Open Experience Builder → Create new Experience
3. Choose **Blank** template
4. Configure layout with these widgets:
   - **Map widget** (full centre area) — add centerline layer + stations layer; enable popup with Arcade label:
     ```arcade
     "Profil " + Text($feature.profil_nr) + "  ·  " +
     Text(Round($feature.station_m, 0)) + " m  ·  " +
     Text(Round($feature.elevation, 1)) + " m.o.h."
     ```
   - **List widget** (left sidebar, 280 px) — datasource: stations layer, sort `stasjon_m` ASC; display template: `{profil_nr}` (large) + `km {stasjon_m / 1000}` (small)
   - **Feature Info widget** (right panel top) — datasource: stations layer; fields: `profil_nr`, `stasjon_m`, `z_moh`, `segment_classes`
   - **Embedded Content widget** (right panel bottom) — URL expression: `{svg_url}` (attribute field)
5. Connect List and Map selection triggers to Feature Info and Embedded Content via **Link widgets** or **Message actions** in the widget settings

- [ ] **Step 3: Export config.json from the XB editor**

In the XB editor:
- Open developer mode (add `?dev=true` to URL)
- OR use **Share → Download** to get a `.zip` with `config.json` inside

Extract `config.json` from the zip.

- [ ] **Step 4: Parameterize the config**

Open `config.json` in a text editor. Find all occurrences of:
- The centerline feature layer item ID → replace each with `__CENTERLINE_ITEM_ID__`
- The sections feature layer item ID → replace each with `__SECTIONS_ITEM_ID__`
- The sections feature service base URL → replace each with `__SERVICE_URL__`

Save as `templates/xb_config_template.json`.

- [ ] **Step 5: Verify substitution**

```
python -c "
import json
t = open('templates/xb_config_template.json').read()
assert '__CENTERLINE_ITEM_ID__' in t, 'centerline placeholder missing'
assert '__SECTIONS_ITEM_ID__' in t, 'sections placeholder missing'
assert '__SERVICE_URL__' in t, 'service URL placeholder missing'
print('OK — all 3 placeholders present')
"
```

Expected output: `OK — all 3 placeholders present`

- [ ] **Step 6: Commit the template**

```bash
git add templates/xb_config_template.json
git commit -m "feat: add Experience Builder config.json template with item-ID placeholders"
```

---

## Arcade expressions reference

These expressions are configured in the XB editor (Step 7 Step 2), not in Python:

**Popup title on station points:**
```arcade
"Profil " + Text($feature.profil_nr) + "  ·  " +
Text(Round($feature.station_m, 0)) + " m  ·  " +
Text(Round($feature.elevation, 1)) + " m.o.h."
```

**km-formatted label in Feature Info:**
```arcade
"km " + Text(Round($feature.station_m / 1000, 3), "0.000")
```

**SVG URL for Embedded Content widget:**
```arcade
$feature.svg_url
```
