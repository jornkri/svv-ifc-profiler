# Ferdig-grunn-elevasjon (cut & fill) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lag en ferdig-grunn-elevasjonsflate fra BIM-vegmodellen og legg den som et ekstra elevasjonslag oppå `GeocacheTerreng` i Profilutforsker-3D, så vegmodellen hviler riktig (ingen skjæring som stikker opp / fylling som svever).

**Architecture:** Ren-Python mesh-z-buffer rasteriserer IFC-veg-TIN-ene (topp-z per celle, ekskl. eksisterende-terreng-TIN) til en kompakt binær høydegrid (`terrain_dem.bin` + `terrain_dem.json`) i jobbens output. Et nytt backend-endpoint serverer filene. Klienten laster dem i en custom `BaseElevationLayer` (`CorridorElevationLayer`) med `tileInfo` matchet eksakt mot terreng-cachens skjema (EPSG:25833), lagt oppå `GeocacheTerreng` med NoData-gjennomfall.

**Tech Stack:** Python (numpy, ifcopenshell via eksisterende `read_ifc_tins`), FastAPI, ArcGIS Maps SDK for JavaScript 5.0 (ESM, `BaseElevationLayer`/`TileInfo`).

---

## Avvik fra spec (bevisst, flagget til bruker)

Spec-en (`docs/superpowers/specs/2026-06-03-ferdig-grunn-elevasjon-design.md`) beskrev en Python-mosaikk mot Kartverket-terreng + feather. Under planlegging ble det klart at:

- `GeocacheTerreng` leverer allerede naturlig terreng overalt, og korridorlaget komposit­terer oppå med **NoData-gjennomfall** → naturlig terreng utenfor footprint er «gratis» fra baselaget. Python-mosaikken er derfor redundant.
- En rutenett-spørring mot Kartverkets punkt-API (≤50 punkter/kall) over hele korridoren ville krevd titusenvis av kall — ikke gjennomførbart.

**Beslutning:** Kjernen lager en footprint-DEM (modellens topp-z) + NoData utenfor. En eventuell feather-overgang gjøres senere klient-side mot ekte `GeocacheTerreng`-verdier (vi har en ren hook for det), **kun hvis** manuell QA viser vertikale kant-sprang. Antakelsen er at SVV-vegmodellens `fylling`/`skjaering`-flater nnår dagline (der modell-z ≈ terreng), så overgangen blir sømløs uten feather.

---

## File Structure

- **Create:** `src/ifc_processor/finished_ground.py` — ren-Python rasterisering + DEM-skriving. Én ansvar: TIN → høydegrid-filer.
- **Modify:** `src/ifc_processor/pipeline.py` — best-effort kall til `build_finished_ground_dem(...)` + ny nøkkel i retur-dict.
- **Modify:** `src/api/server.py` — to nye read-only endepunkter som serverer DEM-filene.
- **Modify:** `web/profilutforsker.html` — `CorridorElevationLayer` + tileInfo-konstant + wiring i scene-init og jobblasting.
- **Create:** `tests/test_finished_ground.py` — enhetstester for rasterisering/skriving.
- **Modify:** `tests/test_api_jobs.py` (hvis finnes; ellers create) — endpoint-test.

---

## Task 1: Mesh-z-buffer-kjerne (`rasterize_tins`)

**Files:**
- Create: `src/ifc_processor/finished_ground.py`
- Test: `tests/test_finished_ground.py`

Grid-konvensjon (lås denne nå, brukes i alle senere tasks og i frontend):
- `xmin, ymin` = sørvestre hjørne. `cell_m` = cellestørrelse (m).
- `ncols, nrows` = antall celler i x/y.
- `ymax = ymin + nrows * cell_m`.
- Celleverdi `grid[r][c]` samples i **cellesenter**: `cx = xmin + (c+0.5)*cell_m`, `cy = ymax - (r+0.5)*cell_m` (rad 0 = nordligst).
- NoData = `-9999.0`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_finished_ground.py
import numpy as np
from src.ifc_processor.finished_ground import rasterize_tins, NODATA


def _flat_triangle(z, x0, y0, size):
    """Én stor flat trekant i z-planet som dekker [x0,x0+size]x[y0,y0+size]-ish."""
    # To trekanter dekker et kvadrat; her bruker vi én rettvinklet trekant.
    return np.array([[[x0, y0, z], [x0 + size, y0, z], [x0, y0 + size, z]]])


def test_rasterize_single_triangle_fills_covered_cells():
    tris = _flat_triangle(z=5.0, x0=0.0, y0=0.0, size=4.0)
    grid, header = rasterize_tins([tris], xmin=0.0, ymin=0.0, xmax=4.0, ymax=4.0, cell_m=1.0)
    assert header["ncols"] == 4 and header["nrows"] == 4
    # Cellesenter (0.5,3.5) ligger inne i trekanten (y<=x-grensa? sjekk hjørnet nær origo)
    # Nedre-venstre celle (rad 3, kol 0) senter (0.5,0.5): innenfor → 5.0
    assert grid[3, 0] == 5.0
    # Øvre-høyre celle (rad 0, kol 3) senter (3.5,3.5): utenfor rettvinklet trekant → NoData
    assert grid[0, 3] == NODATA


def test_rasterize_keeps_topmost_z_on_overlap():
    low = _flat_triangle(z=2.0, x0=0.0, y0=0.0, size=4.0)
    high = _flat_triangle(z=9.0, x0=0.0, y0=0.0, size=4.0)
    grid, _ = rasterize_tins([low, high], xmin=0.0, ymin=0.0, xmax=4.0, ymax=4.0, cell_m=1.0)
    assert grid[3, 0] == 9.0  # høyeste vinner uansett rekkefølge
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_finished_ground.py -v`
Expected: FAIL med `ModuleNotFoundError`/`ImportError` (finished_ground finnes ikke).

- [ ] **Step 3: Write minimal implementation**

```python
# src/ifc_processor/finished_ground.py
"""Ferdig-grunn-DEM fra BIM-veg-TIN-er (ren Python, ingen ArcPy).

Rasteriserer veg-TIN-trekanter til et regulært høydegrid via en mesh-z-buffer
(topp-z per celle). Brukes som ekstra elevasjonslag oppå GeocacheTerreng i
Profilutforsker-3D, så vegmodellen hviler riktig (cut/fill).
"""
from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)

NODATA = -9999.0


def rasterize_tins(
    triangle_arrays: list[np.ndarray],
    *,
    xmin: float,
    ymin: float,
    xmax: float,
    ymax: float,
    cell_m: float,
) -> tuple[np.ndarray, dict]:
    """Rasteriser trekanter til et høydegrid (topp-z per cellesenter).

    Args:
        triangle_arrays: Liste av (N,3,3)-arrays (trekant → 3 hjørner → x,y,z),
                         alle i SAMME projiserte CRS (typisk EPSG:25833).
        xmin..ymax:      Grid-utstrekning i samme CRS.
        cell_m:          Cellestørrelse i meter.

    Returns:
        (grid, header). grid: float32 (nrows, ncols), rad 0 = nordligst,
        NoData = NODATA. header: dict med xmin/ymin/cell_m/ncols/nrows/nodata.
    """
    ncols = max(1, int(round((xmax - xmin) / cell_m)))
    nrows = max(1, int(round((ymax - ymin) / cell_m)))
    ymax_eff = ymin + nrows * cell_m
    grid = np.full((nrows, ncols), NODATA, dtype=np.float32)

    for tris in triangle_arrays:
        if tris is None or len(tris) == 0:
            continue
        for tri in tris:
            _splat_triangle(grid, tri, xmin, ymax_eff, cell_m, ncols, nrows)

    header = {
        "xmin": float(xmin),
        "ymin": float(ymin),
        "cell_m": float(cell_m),
        "ncols": int(ncols),
        "nrows": int(nrows),
        "nodata": float(NODATA),
    }
    return grid, header


def _splat_triangle(
    grid: np.ndarray,
    tri: np.ndarray,
    xmin: float,
    ymax: float,
    cell_m: float,
    ncols: int,
    nrows: int,
) -> None:
    """Skriv én trekants topp-z inn i griddet (z-buffer, max vinner)."""
    xs = tri[:, 0]
    ys = tri[:, 1]
    zs = tri[:, 2]

    # Celle-indeksområde som trekantens bbox dekker (rad 0 = nordligst).
    c_lo = int(np.floor((xs.min() - xmin) / cell_m))
    c_hi = int(np.ceil((xs.max() - xmin) / cell_m))
    r_lo = int(np.floor((ymax - ys.max()) / cell_m))
    r_hi = int(np.ceil((ymax - ys.min()) / cell_m))
    c_lo, c_hi = max(0, c_lo), min(ncols, c_hi)
    r_lo, r_hi = max(0, r_lo), min(nrows, r_hi)
    if c_lo >= c_hi or r_lo >= r_hi:
        return

    # Barysentriske nevnere (2D-projeksjon i xy).
    x1, y1 = xs[0], ys[0]
    x2, y2 = xs[1], ys[1]
    x3, y3 = xs[2], ys[2]
    denom = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    if abs(denom) < 1e-12:
        return  # degenerert/vertikal trekant — ingen xy-flate

    cols = np.arange(c_lo, c_hi)
    rows = np.arange(r_lo, r_hi)
    cx = xmin + (cols + 0.5) * cell_m            # (ncol,)
    cy = ymax - (rows + 0.5) * cell_m            # (nrow,)
    CX, CY = np.meshgrid(cx, cy)                 # (nrow, ncol)

    a = ((y2 - y3) * (CX - x3) + (x3 - x2) * (CY - y3)) / denom
    b = ((y3 - y1) * (CX - x3) + (x1 - x3) * (CY - y3)) / denom
    c = 1.0 - a - b
    inside = (a >= -1e-9) & (b >= -1e-9) & (c >= -1e-9)
    z = a * zs[0] + b * zs[1] + c * zs[2]

    sub = grid[r_lo:r_hi, c_lo:c_hi]
    np.maximum(sub, np.where(inside, z, NODATA), out=sub)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_finished_ground.py -v`
Expected: PASS (begge testene).

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/finished_ground.py tests/test_finished_ground.py
git commit -m "feat(elevasjon): mesh-z-buffer rasterizer for ferdig-grunn-DEM"
```

---

## Task 2: Skriv DEM til disk (`write_dem`)

**Files:**
- Modify: `src/ifc_processor/finished_ground.py`
- Test: `tests/test_finished_ground.py`

- [ ] **Step 1: Write the failing test**

```python
# legg til i tests/test_finished_ground.py
import json
from src.ifc_processor.finished_ground import write_dem


def test_write_dem_roundtrips_binary_and_header(tmp_path):
    grid = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    header = {"xmin": 10.0, "ymin": 20.0, "cell_m": 0.5,
              "ncols": 2, "nrows": 2, "nodata": NODATA}
    bin_path, json_path = write_dem(grid, header, tmp_path)

    assert bin_path.name == "terrain_dem.bin"
    assert json_path.name == "terrain_dem.json"

    raw = np.fromfile(bin_path, dtype="<f4")
    assert np.array_equal(raw, grid.ravel(order="C"))

    meta = json.loads(json_path.read_text(encoding="utf-8"))
    assert meta["wkid"] == 25833
    assert meta["ncols"] == 2 and meta["nrows"] == 2
    assert meta["cell_m"] == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_finished_ground.py::test_write_dem_roundtrips_binary_and_header -v`
Expected: FAIL med `ImportError: cannot import name 'write_dem'`.

- [ ] **Step 3: Write minimal implementation**

```python
# legg til i src/ifc_processor/finished_ground.py
import json
from pathlib import Path


def write_dem(grid: np.ndarray, header: dict, output_dir) -> tuple[Path, Path]:
    """Skriv grid til terrain_dem.bin (little-endian float32, row-major C-order,
    rad 0 = nordligst) og header til terrain_dem.json (med wkid=25833)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    bin_path = output_dir / "terrain_dem.bin"
    json_path = output_dir / "terrain_dem.json"

    grid.astype("<f4").tofile(bin_path)
    meta = {"wkid": 25833, **header}
    json_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return bin_path, json_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_finished_ground.py -v`
Expected: PASS (alle tre testene).

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/finished_ground.py tests/test_finished_ground.py
git commit -m "feat(elevasjon): skriv DEM som binær heightfield + JSON-header"
```

---

## Task 3: Orchestrator (`build_finished_ground_dem`)

**Files:**
- Modify: `src/ifc_processor/finished_ground.py`
- Test: `tests/test_finished_ground.py`

Ansvar: filtrer bort eksisterende-terreng-TIN, transformer til 25833 ved behov, beregn grid-bbox fra senterlinjen + margin, kall `rasterize_tins` + `write_dem`. Returner `Path` til `.bin` eller `None`.

`TINLayer` har `.triangles` (N,3,3) og `.road_class` (str). `Centerline` har `.points` (M,3) og `.source_epsg` (int).

- [ ] **Step 1: Write the failing test**

```python
# legg til i tests/test_finished_ground.py
from dataclasses import dataclass
from src.ifc_processor.finished_ground import build_finished_ground_dem


@dataclass
class _FakeTIN:
    road_class: str
    triangles: np.ndarray


@dataclass
class _FakeCL:
    points: np.ndarray
    source_epsg: int = 25833


def test_build_excludes_terrain_class_and_writes_dem(tmp_path):
    # Veg-trekant rundt (100,200) i 25833, z=50.
    road = _FakeTIN("kjørefelt", np.array([[[98, 198, 50.0], [104, 198, 50.0], [98, 204, 50.0]]]))
    # Terreng-trekant skal IKKE påvirke griddet (høyere z, men ekskluderes).
    terr = _FakeTIN("terreng", np.array([[[98, 198, 999.0], [104, 198, 999.0], [98, 204, 999.0]]]))
    cl = _FakeCL(points=np.array([[100.0, 200.0, 50.0], [101.0, 201.0, 50.0]]))

    bin_path = build_finished_ground_dem([road, terr], cl, tmp_path, cell_m=1.0, margin_m=5.0)
    assert bin_path is not None and bin_path.exists()

    raw = np.fromfile(bin_path, dtype="<f4")
    present = raw[raw != NODATA]
    assert present.size > 0
    assert np.all(present == 50.0)  # kun veg-z, aldri terreng-z=999


def test_build_returns_none_when_no_road_tins(tmp_path):
    terr = _FakeTIN("terreng", np.array([[[0, 0, 1.0], [1, 0, 1.0], [0, 1, 1.0]]]))
    cl = _FakeCL(points=np.array([[0.0, 0.0, 0.0], [1.0, 1.0, 0.0]]))
    assert build_finished_ground_dem([terr], cl, tmp_path, cell_m=1.0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_finished_ground.py -k build -v`
Expected: FAIL med `ImportError: cannot import name 'build_finished_ground_dem'`.

- [ ] **Step 3: Write minimal implementation**

```python
# legg til i src/ifc_processor/finished_ground.py

# road_class-verdier som IKKE er del av ferdig grunn (eksisterende terreng).
_EXCLUDE_CLASSES = {"terreng"}

DEFAULT_CELL_M = 0.5
DEFAULT_MARGIN_M = 30.0  # romslig nok til å dekke skråninger ut til dagline


def _to_25833_xy(tris: np.ndarray, source_epsg: int) -> np.ndarray:
    """Transformer (N,3,3)-trekanters x,y fra source_epsg til 25833 (z uendret)."""
    if source_epsg == 25833:
        return tris
    from pyproj import Transformer
    tf = Transformer.from_crs(source_epsg, 25833, always_xy=True)
    out = tris.copy().astype(float)
    flat = out.reshape(-1, 3)
    x, y = tf.transform(flat[:, 0], flat[:, 1])
    flat[:, 0] = x
    flat[:, 1] = y
    return out.reshape(tris.shape)


def build_finished_ground_dem(
    tins,
    centerline,
    output_dir,
    *,
    cell_m: float = DEFAULT_CELL_M,
    margin_m: float = DEFAULT_MARGIN_M,
) -> Path | None:
    """Bygg ferdig-grunn-DEM fra veg-TIN-ene og skriv terrain_dem.{bin,json}.

    Returnerer Path til .bin, eller None hvis ingen veg-geometri finnes.
    """
    src_epsg = getattr(centerline, "source_epsg", 25833)
    road_tris = [
        _to_25833_xy(t.triangles, src_epsg)
        for t in tins
        if t.road_class not in _EXCLUDE_CLASSES
        and t.triangles is not None and len(t.triangles) > 0
    ]
    if not road_tris:
        logger.info("Ingen veg-TIN-er — ferdig-grunn-DEM hoppes over")
        return None

    all_xy = np.concatenate([t.reshape(-1, 3) for t in road_tris])
    xmin = float(all_xy[:, 0].min()) - margin_m
    xmax = float(all_xy[:, 0].max()) + margin_m
    ymin = float(all_xy[:, 1].min()) - margin_m
    ymax = float(all_xy[:, 1].max()) + margin_m

    grid, header = rasterize_tins(
        road_tris, xmin=xmin, ymin=ymin, xmax=xmax, ymax=ymax, cell_m=cell_m
    )
    if not np.any(grid != NODATA):
        logger.info("Ferdig-grunn-DEM ble tom (ingen dekkede celler)")
        return None

    bin_path, _ = write_dem(grid, header, output_dir)
    logger.info("Ferdig-grunn-DEM skrevet: %s (%dx%d, %.2f m)",
                bin_path, header["ncols"], header["nrows"], cell_m)
    return bin_path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_finished_ground.py -v`
Expected: PASS (alle testene).

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/finished_ground.py tests/test_finished_ground.py
git commit -m "feat(elevasjon): orchestrator build_finished_ground_dem (filtrer terreng, 25833)"
```

---

## Task 4: Wire inn i pipelinen

**Files:**
- Modify: `src/ifc_processor/pipeline.py` (import øverst; kall + retur-nøkkel nær slutten, ved `return {...}` rundt linje 506)

- [ ] **Step 1: Legg til import (toppen av filen, ved de andre `.`-importene rundt linje 14-19)**

```python
from .finished_ground import build_finished_ground_dem
```

- [ ] **Step 2: Generer DEM-en (best-effort) rett FØR `return {...}` (rundt linje 505)**

Finn denne linjen:

```python
    logger.info("Pipeline ferdig. %d SVGer → %s", len(svg_paths), output_dir)
    return {
```

Sett inn rett før `logger.info("Pipeline ferdig...`:

```python
    # Ferdig-grunn-DEM (cut/fill) for 3D-scenens elevasjon — best-effort.
    terrain_dem_path: str | None = None
    try:
        _dem = build_finished_ground_dem(tins, centerline, output_dir)
        if _dem is not None:
            terrain_dem_path = str(_dem)
    except Exception as exc:
        logger.warning("Ferdig-grunn-DEM feilet (hoppes over): %s", exc)

```

- [ ] **Step 3: Legg `terrain_dem` til i retur-dicten**

Endre retur-dicten (rundt linje 506-513) så den inkluderer:

```python
    return {
        "svgs": svg_paths,
        "centerline": str(cl_path),
        "metadata": str(meta_path),
        "stations_json": str(stations_json_path),
        "station_labels_json": str(output_dir / "station_labels.json"),
        "lengdeprofil": lp_svg_path,
        "terrain_dem": terrain_dem_path,
    }
```

- [ ] **Step 4: Verifiser at modulen importerer uten feil**

Run: `python -c "import src.ifc_processor.pipeline"`
Expected: ingen output, exit 0 (ingen ImportError).

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/pipeline.py
git commit -m "feat(elevasjon): generer ferdig-grunn-DEM i pipelinen (best-effort)"
```

---

## Task 5: Backend-endepunkter for DEM-filene

**Files:**
- Modify: `src/api/server.py` (ny rute etter `get_svg` rundt linje 369)
- Test: `tests/test_terrain_dem_endpoint.py` (create)

Mønster kopieres fra `get_svg` (path-traversal-sikring via `relative_to`).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_terrain_dem_endpoint.py
import json
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

from src.api.server import app, UPLOAD_DIR

client = TestClient(app)


def _make_job_with_dem(job_id: str):
    out = UPLOAD_DIR / job_id / "output"
    out.mkdir(parents=True, exist_ok=True)
    grid = np.array([[1.0, 2.0], [3.0, 4.0]], dtype="<f4")
    grid.tofile(out / "terrain_dem.bin")
    (out / "terrain_dem.json").write_text(json.dumps(
        {"wkid": 25833, "xmin": 0.0, "ymin": 0.0, "cell_m": 1.0,
         "ncols": 2, "nrows": 2, "nodata": -9999.0}), encoding="utf-8")
    return out


def test_terrain_dem_json_and_bin_served(tmp_path):
    out = _make_job_with_dem("testjob-dem")
    try:
        r = client.get("/api/jobs/testjob-dem/terrain-dem")
        assert r.status_code == 200
        assert r.json()["wkid"] == 25833

        rb = client.get("/api/jobs/testjob-dem/terrain-dem.bin")
        assert rb.status_code == 200
        assert rb.headers["content-type"] == "application/octet-stream"
        vals = np.frombuffer(rb.content, dtype="<f4")
        assert np.array_equal(vals, np.array([1, 2, 3, 4], dtype="<f4"))
    finally:
        for f in out.iterdir():
            f.unlink()
        out.rmdir()
        out.parent.rmdir()


def test_terrain_dem_404_when_missing():
    r = client.get("/api/jobs/nonexistent-job/terrain-dem")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_terrain_dem_endpoint.py -v`
Expected: FAIL (404 på `/terrain-dem` fordi ruten ikke finnes ennå → faktisk 404 fra FastAPI, men `.bin`-content-type-assert feiler / ruten mangler). Bekreft at testen er rød.

- [ ] **Step 3: Write minimal implementation — legg til etter `get_svg` (rundt linje 369)**

```python
@app.get("/api/jobs/{job_id}/terrain-dem")
def get_terrain_dem_header(job_id: str) -> FileResponse:
    """Serve ferdig-grunn-DEM-headeren (terrain_dem.json) for en jobb."""
    output_dir = (UPLOAD_DIR / job_id / "output").resolve()
    path = (output_dir / "terrain_dem.json").resolve()
    try:
        path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(403, "Ikke tillatt")
    if not path.exists():
        raise HTTPException(404, "Ingen DEM for jobben")
    return FileResponse(str(path), media_type="application/json")


@app.get("/api/jobs/{job_id}/terrain-dem.bin")
def get_terrain_dem_bin(job_id: str) -> FileResponse:
    """Serve ferdig-grunn-DEM-rasteret (terrain_dem.bin, float32 LE) for en jobb."""
    output_dir = (UPLOAD_DIR / job_id / "output").resolve()
    path = (output_dir / "terrain_dem.bin").resolve()
    try:
        path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(403, "Ikke tillatt")
    if not path.exists():
        raise HTTPException(404, "Ingen DEM for jobben")
    return FileResponse(str(path), media_type="application/octet-stream")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_terrain_dem_endpoint.py -v`
Expected: PASS (begge testene).

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_terrain_dem_endpoint.py
git commit -m "feat(elevasjon): backend-endepunkter for ferdig-grunn-DEM (json + bin)"
```

---

## Task 6: Frontend — `CorridorElevationLayer` + wiring

**Files:**
- Modify: `web/profilutforsker.html`

Ingen automatiske tester for frontend her (manuell QA i Task 7). Hold endringene minimale og i tråd med eksisterende `window._X`-mønster.

- [ ] **Step 1: Importer `BaseElevationLayer` + `TileInfo` i import-blokken (rundt linje 1867-1895)**

Utvid `$arcgis.import([...])`-lista og destruktureringen. Legg til i array-et (etter `'@arcgis/core/layers/ElevationLayer.js'`):

```javascript
      '@arcgis/core/layers/BaseElevationLayer.js',
      '@arcgis/core/layers/support/TileInfo.js',
```

Legg `BaseElevationLayer, TileInfo` til i destruktureringen (etter `ElevationLayer`):

```javascript
  const [Map, MapView, SceneView, VectorTileLayer, TileLayer, FeatureLayer,
         SceneLayer, ElevationLayer, BaseElevationLayer, TileInfo, Ground, Basemap, esriId, GraphicsLayer, Graphic] =
```

Og lagre globalt (ved de andre `window._X = X`-linjene rundt 1885-1895):

```javascript
  window._BaseElevationLayer = BaseElevationLayer;
  window._TileInfo = TileInfo;
```

- [ ] **Step 2: Legg til tile-skjema-konstant + layer-fabrikk (rett etter `SCENE_TERRAIN_URL`-konstanten, rundt linje 1088)**

```javascript
// Tile-skjema fra Config_tile_scheme_Geocache_ETRS89_UTM33.xml — MÅ matche
// GeocacheTerreng/GeocacheBilder så korridor-elevasjonen komposit­terer pikselnøyaktig.
const GEOCACHE_TILEINFO = {
  size: [256, 256],
  dpi: 96,
  origin: { x: -2500000, y: 9045984, spatialReference: { wkid: 25833 } },
  spatialReference: { wkid: 25833 },
  lods: [
    { level: 0,  resolution: 21674.710016086701, scale: 81920000 },
    { level: 1,  resolution: 10837.355008043351, scale: 40960000 },
    { level: 2,  resolution: 5418.6775040216753, scale: 20480000 },
    { level: 3,  resolution: 2709.3387520108377, scale: 10240000 },
    { level: 4,  resolution: 1354.6693760054188, scale: 5120000 },
    { level: 5,  resolution: 677.33468800270941, scale: 2560000 },
    { level: 6,  resolution: 338.66734400135471, scale: 1280000 },
    { level: 7,  resolution: 169.33367200067735, scale: 640000 },
    { level: 8,  resolution: 84.666836000338677, scale: 320000 },
    { level: 9,  resolution: 42.333418000169338, scale: 160000 },
    { level: 10, resolution: 21.166709000084669, scale: 80000 },
    { level: 11, resolution: 10.583354500042335, scale: 40000 },
    { level: 12, resolution: 5.2916772500211673, scale: 20000 },
    { level: 13, resolution: 2.6458386250105836, scale: 10000 },
    { level: 14, resolution: 1.3229193125052918, scale: 5000 },
    { level: 15, resolution: 0.66145965625264591, scale: 2500 },
    { level: 16, resolution: 0.33072982812632296, scale: 1250 },
    { level: 17, resolution: 0.16536491406316148, scale: 625 },
  ],
};

// Holder på korridor-elevasjonslaget så vi kan bytte det per jobb.
let corridorElev = null;

// Lag et CorridorElevationLayer fra en jobbs DEM. Returnerer null hvis ingen DEM.
async function makeCorridorElevationLayer(jobId) {
  const BaseElevationLayer = window._BaseElevationLayer;
  const TileInfo = window._TileInfo;
  let header, buf;
  try {
    const hr = await fetch(`${API}/api/jobs/${jobId}/terrain-dem`);
    if (!hr.ok) return null;            // ingen DEM for jobben
    header = await hr.json();
    const br = await fetch(`${API}/api/jobs/${jobId}/terrain-dem.bin`);
    if (!br.ok) return null;
    buf = new Float32Array(await br.arrayBuffer());
  } catch (_) {
    return null;                        // backend nede / nettverksfeil → hopp over
  }

  const { xmin, ymin, cell_m, ncols, nrows, nodata } = header;
  const ymax = ymin + nrows * cell_m;

  // Bilineær sampling av DEM-en ved (wx, wy). NaN utenfor / ved nodata.
  function sample(wx, wy) {
    const fc = (wx - xmin) / cell_m - 0.5;
    const fr = (ymax - wy) / cell_m - 0.5;     // rad 0 = nordligst
    const c0 = Math.floor(fc), r0 = Math.floor(fr);
    if (c0 < 0 || r0 < 0 || c0 + 1 >= ncols || r0 + 1 >= nrows) return NaN;
    const tx = fc - c0, ty = fr - r0;
    const v00 = buf[r0 * ncols + c0],         v10 = buf[r0 * ncols + c0 + 1];
    const v01 = buf[(r0 + 1) * ncols + c0],   v11 = buf[(r0 + 1) * ncols + c0 + 1];
    if (v00 === nodata || v10 === nodata || v01 === nodata || v11 === nodata) return NaN;
    const top = v00 * (1 - tx) + v10 * tx;
    const bot = v01 * (1 - tx) + v11 * tx;
    return top * (1 - ty) + bot * ty;
  }

  const CorridorElevationLayer = BaseElevationLayer.createSubclass({
    load: function () {
      this.tileInfo = TileInfo.fromJSON(GEOCACHE_TILEINFO);
      this.spatialReference = { wkid: 25833 };
      this.fullExtent = {
        xmin, ymin, xmax: xmin + ncols * cell_m, ymax,
        spatialReference: { wkid: 25833 },
      };
    },
    fetchTile: function (level, row, col, options) {
      const lod = GEOCACHE_TILEINFO.lods.find(l => l.level === level)
                  || GEOCACHE_TILEINFO.lods[GEOCACHE_TILEINFO.lods.length - 1];
      const res = lod.resolution;
      const size = GEOCACHE_TILEINFO.size[0];          // 256
      const w = size + 1, h = size + 1;                 // 257x257 posts
      const ox = GEOCACHE_TILEINFO.origin.x;
      const oy = GEOCACHE_TILEINFO.origin.y;
      const tileMinX = ox + col * size * res;
      const tileMaxY = oy - row * size * res;
      const values = new Float32Array(w * h);
      const NO = -9999;
      for (let j = 0; j < h; j++) {
        const wy = tileMaxY - j * res;
        for (let i = 0; i < w; i++) {
          const wx = tileMinX + i * res;
          const z = sample(wx, wy);
          values[j * w + i] = Number.isNaN(z) ? NO : z;
        }
      }
      return { values, width: w, height: h, maxZError: 0, noDataValue: NO };
    },
  });

  return new CorridorElevationLayer({ title: 'Ferdig grunn (korridor)' });
}
```

- [ ] **Step 3: Bygg grunnen med begge lag i `initScene` (rundt linje 1230)**

Erstatt linja:

```javascript
  const ground  = new Ground({ layers: [new ElevationLayer({ url: SCENE_TERRAIN_URL })] });
```

med:

```javascript
  // GeocacheTerreng nederst (naturlig terreng), korridor-elevasjon legges på
  // toppen senere i loadSceneForJob (NoData faller gjennom til GeocacheTerreng).
  const ground  = new Ground({ layers: [new ElevationLayer({ url: SCENE_TERRAIN_URL })] });
```

(Ingen funksjonell endring her — korridorlaget legges til i Step 4. Kommentaren dokumenterer rekkefølgen.)

- [ ] **Step 4: Legg/oppdater korridorlaget når en jobb lastes i 3D**

Finn funksjonen som setter scene-lag per jobb (der `sceneLayer3d = new window._SceneLayer({ url: currentSceneUrl, ... })` settes, rundt linje 1381). Rett etter at scene-laget er satt, legg til:

```javascript
  // Korridor-elevasjon (ferdig grunn) oppå GeocacheTerreng for valgt jobb.
  try {
    if (corridorElev && map3d) { map3d.ground.layers.remove(corridorElev); corridorElev = null; }
    const cel = await makeCorridorElevationLayer(currentJobId);
    if (cel && map3d) {
      corridorElev = cel;
      map3d.ground.layers.add(cel);   // sist i lista → vinner der den har data
    }
  } catch (e) {
    console.warn('Korridor-elevasjon hoppes over:', e);
  }
```

> Bekreft det faktiske navnet på jobb-id-variabelen i denne scopen (søk etter hvor `bim_scene_url`/`currentSceneUrl` settes, og bruk samme jobb-referanse — kalt `currentJobId` her som plassholder for den eksisterende variabelen).

- [ ] **Step 5: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(elevasjon): CorridorElevationLayer (matchende tileInfo) oppå GeocacheTerreng"
```

---

## Task 7: Manuell 3D-verifisering

**Files:** ingen (kun verifisering)

- [ ] **Step 1: Start backend og kjør en IFC-jobb som genererer DEM**

```bash
.\dev.ps1 -Reload
```

Last opp en IFC-vegmodell via web-UI, publiser BIM/3D, og bekreft at `uploads/<job>/output/terrain_dem.bin` + `terrain_dem.json` opprettes.

- [ ] **Step 2: Verifiser DEM-headeren**

Run: `python -c "import json,sys; d=json.load(open(sys.argv[1])); print(d)" uploads/<job>/output/terrain_dem.json`
Expected: `wkid: 25833`, fornuftige `xmin/ymin` (UTM33-område), `ncols/nrows > 0`, `cell_m: 0.5`.

- [ ] **Step 3: Verifiser i scenen (nettleser)**

Åpne Profilutforsker, velg jobben, bytt til 3D. Sjekk:
- Vegen i **skjæring** har ikke lenger terreng som stikker opp gjennom vegbanen.
- Vegen på **fylling** svever ikke — fyllingsskråningen møter terrenget.
- Overgangen korridor↔omkringliggende `GeocacheTerreng` har ikke et tydelig vertikalt sprang (hvis det har det → noter; da legger vi til klient-side feather mot GeocacheTerreng i en oppfølging).

- [ ] **Step 4: Verifiser NoData-gjennomfall / kompositt-antakelse**

Bekreft at terrenget UTENFOR korridoren fortsatt er `GeocacheTerreng` (ikke flatt/hullete). Hvis korridorlaget «vinner» med NoData utenfor footprint (terreng forsvinner), er kompositt-antakelsen feil — da må `fetchTile` returnere `noDataValue` korrekt (sjekk at `-9999` brukes og at SDK-en honorerer `noDataValue` for gjennomfall; dette er den kritiske antakelsen i designet).

- [ ] **Step 5: Oppdater minne + evt. merge**

Når QA er OK: oppdater prosjektminnet (`project_3d_scene_profilutforsker` el. nytt notat) med resultat, og følg `superpowers:finishing-a-development-branch` for merge til main.

---

## Self-Review (utført)

- **Spec-dekning:** Mesh-z-buffer (Task 1), DEM-skriving (Task 2), orchestrator m/terreng-eksklusjon + 25833 (Task 3), pipeline-wiring (Task 4), backend-servering (Task 5), klient-`BaseElevationLayer` m/matchende tileInfo + kompositt oppå GeocacheTerreng (Task 6), 3D-verifisering (Task 7). Kartverket-mosaikk/feather bevisst utelatt — se «Avvik fra spec».
- **Placeholder-skann:** Ingen TBD/TODO. Eneste eksplisitte usikkerhet er jobb-id-variabelnavnet i frontend (Task 6 Step 4), markert for bekreftelse mot eksisterende kode.
- **Type-konsistens:** `NODATA = -9999.0` (Python) ↔ `NO = -9999` (JS). Grid-konvensjon (rad 0 = nordligst, cellesenter-sampling, `ymax = ymin + nrows*cell_m`) er identisk i `rasterize_tins`, `write_dem`-roundtrip og JS-`sample`. Funksjonsnavn: `rasterize_tins`, `write_dem`, `build_finished_ground_dem`, `makeCorridorElevationLayer` brukt konsistent.
- **Kritisk antakelse å verifisere tidlig (Task 7 Step 4):** at `Ground` med flere elevasjonslag honorerer `noDataValue` for gjennomfall til `GeocacheTerreng`. Hele kompositt-strategien hviler på dette.
