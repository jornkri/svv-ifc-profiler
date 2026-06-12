# Lengdefall-påskrift i interaktiv lengdeprofil — Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tegn `+X,X %` / `–X,X %` langs designlinja i den interaktive lengdeprofilen, én verdi per konstant-fall-strekk (tangent), i tråd med håndbok R700.

**Architecture:** Vertikalgeometrien parses allerede i pipeline, men eksponeres ikke til frontend. Vi speiler det eksisterende `horizontal_alignment.json`-mønsteret: pipeline reduserer IFC `vertical_segments` (eller LandXML/PVI-fallback) til en kilde-agnostisk liste konstant-fall-strekk → skriver `vertical_alignment.json` → nytt REST-endepunkt serverer fila → frontend henter den inn i `vertGrades` og tegner påskriftene på designlinja.

**Tech Stack:** Python (dataclasses, ifcopenshell), FastAPI (`src/api/server.py`), vanilla JS + håndbygd SVG (`web/profilutforsker.html`), pytest.

**Design-spec:** `docs/superpowers/specs/2026-06-09-lengdefall-paaskrift-lengdeprofil-design.md`

---

## File Structure

- **Create:** `src/ifc_processor/vertical_tangents.py` — ren, testbar hjelpefunksjon `constant_grade_tangents(...)` som reduserer IFC-segmenter / PVI-liste til `[{sta_start, sta_end, gradient_pct}]`. Holdes adskilt fra `pipeline.py` så logikken kan enhetstestes uten å kjøre hele pipelinen.
- **Modify:** `src/ifc_processor/pipeline.py` — utvid `AlignmentMetadata` med `vertical_segments`; før inn fra IFC; skriv `vertical_alignment.json`.
- **Modify:** `src/api/server.py` — nytt endepunkt `GET /api/jobs/{job_id}/vertical-alignment`.
- **Modify:** `web/profilutforsker.html` — hent inn `vertGrades`; tegn påskrift på designlinja.
- **Create:** `tests/test_vertical_tangents.py` — enhetstester for tangent-utledning.
- **Modify:** `tests/test_api_jobs.py` (eller ny `tests/test_vertical_alignment_endpoint.py`) — endepunkt-test.

---

### Task 1: Ren tangent-utledning (`constant_grade_tangents`)

**Files:**
- Create: `src/ifc_processor/vertical_tangents.py`
- Test: `tests/test_vertical_tangents.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vertical_tangents.py
from __future__ import annotations

from src.ifc_processor.alignment_parser import VerticalSegment
from src.ifc_processor.vertical_tangents import constant_grade_tangents


def test_ifc_segments_only_constantgradient():
    """Rene CONSTANTGRADIENT-tangenter → én rad per segment, gradient i prosent, 1 desimal."""
    segs = [
        VerticalSegment(0.0, 240.0, 100.0, 0.025, "CONSTANTGRADIENT"),
        VerticalSegment(240.0, 40.0, 106.0, 0.0, "PARABOLICARC", radius=2000.0),
        VerticalSegment(280.0, 230.0, 106.0, -0.018, "CONSTANTGRADIENT"),
    ]
    out = constant_grade_tangents(vertical_segments=segs, pvi=[])
    assert out == [
        {"sta_start": 0.0, "sta_end": 240.0, "gradient_pct": 2.5},
        {"sta_start": 280.0, "sta_end": 510.0, "gradient_pct": -1.8},
    ]


def test_ifc_fallback_to_pvi_when_no_constantgradient():
    """Modell uten CONSTANTGRADIENT-segmenter faller tilbake til PVI-utledning."""
    segs = [
        VerticalSegment(0.0, 100.0, 50.0, 0.02, "PARABOLICARC", radius=1500.0),
    ]
    pvi = [(0.0, 50.0), (100.0, 52.0), (300.0, 48.0)]
    out = constant_grade_tangents(vertical_segments=segs, pvi=pvi)
    assert out == [
        {"sta_start": 0.0, "sta_end": 100.0, "gradient_pct": 2.0},
        {"sta_start": 100.0, "sta_end": 300.0, "gradient_pct": -2.0},
    ]


def test_landxml_pvi_only():
    """Tom vertical_segments + PVI-liste (LandXML) → fall mellom nabo-PVI-er."""
    pvi = [(0.0, 100.0), (240.0, 106.0), (510.0, 101.16)]
    out = constant_grade_tangents(vertical_segments=[], pvi=pvi)
    assert out == [
        {"sta_start": 0.0, "sta_end": 240.0, "gradient_pct": 2.5},
        {"sta_start": 240.0, "sta_end": 510.0, "gradient_pct": -1.8},
    ]


def test_empty_inputs_give_empty_list():
    assert constant_grade_tangents(vertical_segments=[], pvi=[]) == []


def test_pvi_single_point_gives_empty_list():
    assert constant_grade_tangents(vertical_segments=[], pvi=[(0.0, 100.0)]) == []


def test_zero_length_pvi_segment_skipped():
    """Degenerert PVI-par (samme stasjon) hoppes over uten å dele på null."""
    pvi = [(0.0, 100.0), (0.0, 100.0), (200.0, 96.0)]
    out = constant_grade_tangents(vertical_segments=[], pvi=pvi)
    assert out == [{"sta_start": 0.0, "sta_end": 200.0, "gradient_pct": -2.0}]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vertical_tangents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ifc_processor.vertical_tangents'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/ifc_processor/vertical_tangents.py
"""Reduser vertikalgeometri til konstant-fall-strekk (tangenter) for R700-påskrift.

Kilde-agnostisk: tar enten IFC-VerticalSegment-liste (foretrukket, eksakt gradient)
eller en PVI-liste [(stasjon, høyde)] (LandXML, eller IFC-fallback uten
CONSTANTGRADIENT-segmenter). Returnerer [{sta_start, sta_end, gradient_pct}] med
gradient i prosent, avrundet til 1 desimal (R700-presisjon).
"""
from __future__ import annotations

from .alignment_parser import VerticalSegment


def _from_constantgradient(segments: list[VerticalSegment]) -> list[dict]:
    rows: list[dict] = []
    for seg in segments:
        if seg.segment_type != "CONSTANTGRADIENT":
            continue
        rows.append({
            "sta_start": round(seg.start_station, 3),
            "sta_end": round(seg.start_station + seg.length, 3),
            "gradient_pct": round(seg.start_gradient * 100, 1),
        })
    return rows


def _from_pvi(pvi: list[tuple[float, float]]) -> list[dict]:
    rows: list[dict] = []
    for (s0, z0), (s1, z1) in zip(pvi, pvi[1:]):
        ds = s1 - s0
        if ds <= 1e-6:
            continue
        rows.append({
            "sta_start": round(s0, 3),
            "sta_end": round(s1, 3),
            "gradient_pct": round((z1 - z0) / ds * 100, 1),
        })
    return rows


def constant_grade_tangents(
    *,
    vertical_segments: list[VerticalSegment],
    pvi: list[tuple[float, float]],
) -> list[dict]:
    """Bygg liste konstant-fall-strekk.

    Prioritet:
      1. IFC CONSTANTGRADIENT-segmenter (eksakt gradient).
      2. Hvis ingen slike finnes: PVI-utledning (LandXML, eller IFC uten tangent-segmenter).
    """
    rows = _from_constantgradient(vertical_segments)
    if rows:
        return rows
    return _from_pvi(pvi)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vertical_tangents.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/vertical_tangents.py tests/test_vertical_tangents.py
git commit -m "feat(vertikal): ren tangent-utledning for lengdefall-paaskrift"
```

---

### Task 2: Før `vertical_segments` inn i `AlignmentMetadata` og skriv `vertical_alignment.json`

**Files:**
- Modify: `src/ifc_processor/pipeline.py:25-30` (dataclass), `:78-96` (`_load_alignment_metadata`), `:447-467` (JSON-skriving)

- [ ] **Step 1: Utvid `AlignmentMetadata` med `vertical_segments`**

I `src/ifc_processor/pipeline.py`, endre dataclass (linje 25-30) fra:

```python
@dataclass
class AlignmentMetadata:
    vertical_pvi: list[tuple[float, float]] = field(default_factory=list)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833
```

til:

```python
@dataclass
class AlignmentMetadata:
    vertical_pvi: list[tuple[float, float]] = field(default_factory=list)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833
    vertical_segments: list[VerticalSegment] = field(default_factory=list)
```

- [ ] **Step 2: Importér `VerticalSegment` i pipeline.py**

I `src/ifc_processor/pipeline.py`, linje 12, endre:

```python
from .alignment_parser import HorizontalSegment, StationLabel
```

til:

```python
from .alignment_parser import HorizontalSegment, StationLabel, VerticalSegment
```

- [ ] **Step 3: Før `vertical_segments` inn i begge grenene av `_load_alignment_metadata`**

I `src/ifc_processor/pipeline.py`, `.xml`-grenen (linje 81-86) — LandXML har ingen IFC-segmenter, så feltet er tomt:

```python
        return AlignmentMetadata(
            vertical_pvi=pvi,
            horizontal_segments=horiz,
            station_labels=[],
            source_epsg=25833,
            vertical_segments=[],
        )
```

`.ifc`-grenen (linje 90-95):

```python
        return AlignmentMetadata(
            vertical_pvi=data.vertical_profile_pvi(),
            horizontal_segments=data.horizontal_segments,
            station_labels=data.station_labels,
            source_epsg=data.source_epsg,
            vertical_segments=data.vertical_segments,
        )
```

- [ ] **Step 4: Skriv `vertical_alignment.json` ved siden av `horizontal_alignment.json`**

I `src/ifc_processor/pipeline.py`, rett etter linje 467 (`(output_dir / "horizontal_alignment.json").write_text(...)`), legg til:

```python
    # Skriv vertical_alignment.json — konstant-fall-strekk for R700-stigningspåskrift
    from .vertical_tangents import constant_grade_tangents
    vert_rows = constant_grade_tangents(
        vertical_segments=align_meta.vertical_segments if align_meta else [],
        pvi=align_meta.vertical_pvi if align_meta else [],
    )
    (output_dir / "vertical_alignment.json").write_text(json.dumps(vert_rows, indent=2))
```

- [ ] **Step 5: Verifiser at modulen importeres og kjører uten feil**

Run: `python -c "from src.ifc_processor.pipeline import AlignmentMetadata; m=AlignmentMetadata(); print('vertical_segments' in m.__dataclass_fields__)"`
Expected: `True`

Run: `python -c "from src.ifc_processor.vertical_tangents import constant_grade_tangents; print(constant_grade_tangents(vertical_segments=[], pvi=[(0.0,10.0),(100.0,12.0)]))"`
Expected: `[{'sta_start': 0.0, 'sta_end': 100.0, 'gradient_pct': 2.0}]`

- [ ] **Step 6: Commit**

```bash
git add src/ifc_processor/pipeline.py
git commit -m "feat(vertikal): skriv vertical_alignment.json fra pipeline"
```

---

### Task 3: API-endepunkt `GET /api/jobs/{job_id}/vertical-alignment`

**Files:**
- Modify: `src/api/server.py:345-354` (etter `get_horizontal_alignment`)
- Test: `tests/test_vertical_alignment_endpoint.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_vertical_alignment_endpoint.py
import json
import shutil

from fastapi.testclient import TestClient

from src.api.server import app, UPLOAD_DIR

client = TestClient(app)


def test_vertical_alignment_served_when_present():
    out = UPLOAD_DIR / "testjob-vert" / "output"
    out.mkdir(parents=True, exist_ok=True)
    rows = [
        {"sta_start": 0.0, "sta_end": 240.0, "gradient_pct": 2.5},
        {"sta_start": 280.0, "sta_end": 510.0, "gradient_pct": -1.8},
    ]
    (out / "vertical_alignment.json").write_text(json.dumps(rows), encoding="utf-8")
    try:
        r = client.get("/api/jobs/testjob-vert/vertical-alignment")
        assert r.status_code == 200
        assert r.json() == rows
    finally:
        shutil.rmtree(out.parent)


def test_vertical_alignment_empty_when_missing():
    r = client.get("/api/jobs/nonexistent-job/vertical-alignment")
    assert r.status_code == 200
    assert r.json() == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_vertical_alignment_endpoint.py -v`
Expected: FAIL — `test_vertical_alignment_served_when_present` gives 404 (route ikke definert)

- [ ] **Step 3: Write the endpoint**

I `src/api/server.py`, rett etter `get_horizontal_alignment` (etter linje 354), legg til:

```python
@app.get("/api/jobs/{job_id}/vertical-alignment")
def get_vertical_alignment(job_id: str) -> list[dict]:
    """Returner vertikale konstant-fall-strekk for jobben (tom liste hvis mangler)."""
    path = UPLOAD_DIR / job_id / "output" / "vertical_alignment.json"
    if not path.exists():
        return []
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_vertical_alignment_endpoint.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_vertical_alignment_endpoint.py
git commit -m "feat(api): endepunkt /vertical-alignment"
```

---

### Task 4: Frontend — hent `vertGrades`

**Files:**
- Modify: `web/profilutforsker.html:1321` (deklarasjon), `:2573-2583` (fetch)

- [ ] **Step 1: Deklarer `vertGrades` ved siden av `horCurves`**

I `web/profilutforsker.html`, etter linje 1321:

```javascript
let horCurves = [];  // [{kind, sta_start, sta_end, radius?, A?, dir?}, ...]
```

legg til:

```javascript
let vertGrades = [];  // [{sta_start, sta_end, gradient_pct}, ...]  (R700 lengdefall-påskrift)
```

- [ ] **Step 2: Hent vertical-alignment der horizontal-alignment hentes**

I `web/profilutforsker.html`, rett etter horisontal-fetch-blokken (etter linje 2581, før `buildGeomLabels();` på linje 2583), legg til:

```javascript
    // Last vertikal kurvatur (konstant-fall-strekk) fra API (tom liste hvis ikke tilgjengelig)
    try {
      const vgRes = await fetch(API + '/api/jobs/' + jobId + '/vertical-alignment',
                                { credentials: 'include' });
      vertGrades = vgRes.ok ? await vgRes.json() : [];
    } catch (err) {
      console.warn('vertical-alignment fetch:', err);
      vertGrades = [];
    }
```

- [ ] **Step 3: Verifiser at fila fortsatt parser (ingen syntaksfeil)**

Run: `node --check web/profilutforsker.html`
Expected: Feiler IKKE på JS-parsing av script-blokken? `node --check` forventer ren JS, ikke HTML. Bruk i stedet et raskt grep-sjekk at begge nye linjer finnes:

Run: `python -c "t=open(r'web/profilutforsker.html',encoding='utf-8').read(); assert 'let vertGrades' in t and \"/vertical-alignment\" in t; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(2d): hent vertical-alignment til vertGrades"
```

---

### Task 5: Frontend — tegn `±X,X %`-påskrift på designlinja

**Files:**
- Modify: `web/profilutforsker.html:3398` (rett etter at designlinja er tegnet)

- [ ] **Step 1: Legg inn påskrift-tegning rett etter designlinja**

I `web/profilutforsker.html`, rett etter linje 3398 (`$(`<path d="${rd}" ... />`);` for designlinja, før kommentaren `// Profile height labels at 100m`), legg til:

```javascript
  // Lengdefall-påskrift (R700): +X,X % / –X,X % midt på hvert konstant-fall-strekk.
  // Klipp til synlig zoom-vindu; hopp over strekk helt utenfor.
  vertGrades
    .filter(t => t.sta_end > stMin && t.sta_start < stMax)
    .forEach(t => {
      const mid = (Math.max(t.sta_start, stMin) + Math.min(t.sta_end, stMax)) / 2;
      const s = _lpNearest(mid);
      const cx = xOf(mid), cy = yOf(s.z);
      if (cy <= GPT + 14) return;  // for nær toppen — hopp over
      const g = t.gradient_pct;
      // Fortegn: '–' (vises alltid for nedoverbakke), '+' for oppoverbakke. Komma som desimaltegn.
      const sign = g < 0 ? '–' : '+';
      const txt = `${sign}${Math.abs(g).toFixed(1).replace('.', ',')} %`;
      const w = txt.length * 5.2 + 6;
      $(`<rect x="${(cx - w / 2).toFixed(1)}" y="${(cy - 16).toFixed(1)}" width="${w.toFixed(1)}" height="12" rx="2" fill="${isDark ? 'rgba(30,32,34,0.78)' : 'rgba(255,255,255,0.82)'}"/>`);
      $(`<text x="${cx.toFixed(1)}" y="${(cy - 7).toFixed(1)}" text-anchor="middle" font-size="8.5" font-weight="600" fill="${CR}" font-family="var(--font-mono)">${txt}</text>`);
    });
```

- [ ] **Step 2: Verifiser at koden finnes og fila er intakt**

Run: `python -c "t=open(r'web/profilutforsker.html',encoding='utf-8').read(); assert 'Lengdefall-påskrift' in t and 'vertGrades' in t; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Manuell live-verifisering**

Start API + åpne profilutforskeren mot en kjent jobb med vertikalgeometri (samme mønster som tidligere features). Kontroller:
- Påskrift `+X,X %` / `–X,X %` vises midt på hvert tangent-strekk på designlinja.
- Verdiene og fortegnene stemmer mot den statiske R700-PNG-en for samme jobb.
- Zoom/panorering klipper påskrift korrekt; ingen feil i konsollen.
- Jobb uten vertikalgeometri (f.eks. kun TIN-elevert) viser ingen påskrift og ingen feil.

- [ ] **Step 4: Commit**

```bash
git add web/profilutforsker.html
git commit -m "feat(2d): tegn lengdefall-paaskrift paa designlinja (R700)"
```

---

## Self-Review

**1. Spec coverage:**
- Datamodell (`AlignmentMetadata.vertical_segments` + tangent-bygger) → Task 1 + Task 2 ✓
- `vertical_alignment.json`-utdata → Task 2 Step 4 ✓
- IFC CONSTANTGRADIENT + PVI-fallback + LandXML-PVI → Task 1 (`constant_grade_tangents`) ✓
- API-endepunkt → Task 3 ✓
- Frontend fetch (`vertGrades`) → Task 4 ✓
- Frontend tegning (`±X,X %`, komma, `–` alltid, alltid-på, klipping) → Task 5 ✓
- `gradient_pct` per stasjon urørt → ingen task rører linje 472-476 ✓
- Vertikalkurver får ingen påskrift → `_from_constantgradient` filtrerer på `CONSTANTGRADIENT` ✓

**2. Placeholder scan:** Ingen TBD/TODO; all kode er konkret og komplett.

**3. Type consistency:** `constant_grade_tangents(*, vertical_segments, pvi)` kalles med nøyaktig disse keyword-argumentene i Task 2 Step 4. `VerticalSegment`-feltrekkefølge (`start_station, length, start_height, start_gradient, segment_type, radius`) matcher `alignment_parser.py:29-36`. JSON-feltnavn (`sta_start`, `sta_end`, `gradient_pct`) er identiske i pipeline, endepunkt-test og frontend.

**Merknad:** Det ligger en preeksisterende, urelatert uncommittet endring i `tests/test_pipeline_stations_json.py` i arbeidstreet. Den skal IKKE forkastes — `git add` kun de eksplisitte filene oppgitt i hver commit.
