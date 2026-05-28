# IFC-senterlinje (IFC4X3 IfcAlignment) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Lar pipeline og web-app akseptere IFC4X3 `IfcAlignment` som senterlinje-kilde parallelt med eksisterende LandXML, og utnytt segmentinformasjon + IfcReferent-stasjoneringsmerker som ikke finnes i LandXML.

**Architecture:** Ny `alignment_parser.py` leser IFC4X3 og eksponerer felles datakontrakt (`IfcAlignmentData`) som adapter-bygger en `Centerline` og en `AlignmentMetadata`. Pipeline og AGOL-publisering jobber mot kontrakten — vet ikke om kilden er LandXML eller IFC.

**Tech Stack:** Python 3.11+, `ifcopenshell` (IFC4X3), `numpy`, `pytest`, ArcPy (kun publisher-grenen), FastAPI, vanilje JS frontend.

**Reference spec:** `docs/superpowers/specs/2026-05-28-ifc-centerline-design.md`

**Test fixture:** `samples/m_f-veg_12200_CL.ifc` (IFC4X3, 1 alignment "12150", 67 hor.seg, 50 vert.seg, 99 referenter).

---

## Filstruktur

| Fil | Status | Ansvar |
|---|---|---|
| `src/ifc_processor/alignment_parser.py` | NY | IFC4X3 IfcAlignment → `IfcAlignmentData` |
| `src/ifc_processor/centerline.py` | MOD | Ny `.ifc`-gren i `load_centerline()` |
| `src/ifc_processor/pipeline.py` | MOD | `_load_alignment_metadata()`, referent-aligned grid |
| `src/arcpy_processor/_polyline_publisher.py` | NY | Felles publish-flyt (GDB→PolylineZ→AGOL) |
| `src/arcpy_processor/landxml_to_agol.py` | MOD | Tynnes ut, bruker `_polyline_publisher` |
| `src/arcpy_processor/ifc_cl_to_agol.py` | NY | Parallell CLI for IFC-CL |
| `src/api/server.py` | MOD | `cl_file: UploadFile` godtar `.xml`/`.ifc`; nytt `/station-labels`-endepunkt |
| `src/api/job_runner.py` | MOD | Ruter til riktig AGOL-CLI |
| `web/src/main.js` | MOD | Dropzone 2 godtar begge formater |
| `web/src/index.html` | MOD | Dropzone 2 copy + `accept` |
| `tests/test_alignment_parser.py` | NY | Unit-tester mot 12200-fixture |
| `tests/test_pipeline.py` | MOD | End-to-end med IFC-CL, referent-grid |
| `tests/test_ifc_cl_to_agol.py` | NY | CLI med mocket ArcPy |

---

## Task 1: Datamodell og skall i `alignment_parser.py`

**Files:**
- Create: `src/ifc_processor/alignment_parser.py`
- Create: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_alignment_parser.py
from __future__ import annotations
from pathlib import Path
import numpy as np
import pytest

from src.ifc_processor.alignment_parser import (
    HorizontalSegment,
    VerticalSegment,
    StationLabel,
    IfcAlignmentData,
)


def test_dataclasses_constructible():
    hs = HorizontalSegment(
        start_station=0.0,
        length=10.0,
        start_point=(100.0, 200.0),
        start_direction=0.0,
        segment_type="LINE",
    )
    assert hs.start_radius is None
    assert hs.is_ccw is None

    vs = VerticalSegment(
        start_station=0.0,
        length=10.0,
        start_height=50.0,
        start_gradient=0.01,
        segment_type="CONSTANTGRADIENT",
    )
    assert vs.radius is None

    sl = StationLabel(station=100.0, name="P 100", position=(100.0, 200.0, 50.0))
    assert sl.name == "P 100"

    data = IfcAlignmentData(
        name="test",
        points_3d=np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 1.0]]),
        stations=np.array([0.0, 10.0]),
        horizontal_segments=[hs],
        vertical_segments=[vs],
        station_labels=[sl],
    )
    assert data.source_epsg == 25833
    assert data.name == "test"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_alignment_parser.py::test_dataclasses_constructible -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.ifc_processor.alignment_parser'`

- [ ] **Step 3: Implement minimal skall**

```python
# src/ifc_processor/alignment_parser.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HorizontalSegment:
    start_station: float
    length: float
    start_point: tuple[float, float]
    start_direction: float                 # radianer
    segment_type: str                      # "LINE" | "CIRCULARARC" | "CLOTHOID"
    start_radius: float | None = None
    end_radius: float | None = None
    is_ccw: bool | None = None


@dataclass
class VerticalSegment:
    start_station: float
    length: float
    start_height: float
    start_gradient: float                  # m/m
    segment_type: str                      # "CONSTANTGRADIENT" | "PARABOLICARC" | "CIRCULARARC"
    radius: float | None = None            # signert: + dal, − topp


@dataclass
class StationLabel:
    station: float
    name: str
    position: tuple[float, float, float]


@dataclass
class IfcAlignmentData:
    name: str
    points_3d: np.ndarray                  # (M, 3)
    stations: np.ndarray                   # (M,)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    vertical_segments: list[VerticalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_alignment_parser.py::test_dataclasses_constructible -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): dataclasses for IFC4X3 alignment data"
```

---

## Task 2: Skjemavalidering og valg av alignment

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

Legg til i `tests/test_alignment_parser.py`:

```python
SAMPLES = Path(__file__).parent.parent / "samples"
CL_12200 = SAMPLES / "m_f-veg_12200_CL.ifc"
VEG_12200 = SAMPLES / "m_f_veg_12200_Veg.ifc"          # vegmodell, ikke alignment
KLEVERUD = SAMPLES / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"  # IFC4 — feil schema


def test_load_12200_returns_alignment_data():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert data.name == "12150"
    # Resten av feltene fylles inn i senere tasks; nå bare skall.


def test_ifc4_schema_rejected():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    if not KLEVERUD.exists():
        pytest.skip("IFC4-eksempel ikke tilgjengelig")
    with pytest.raises(ValueError, match="IFC4X3"):
        load_alignment_from_ifc(KLEVERUD)


def test_missing_alignment_raises():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    with pytest.raises(ValueError, match="IfcAlignment"):
        load_alignment_from_ifc(VEG_12200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "12200 or schema or missing"`
Expected: FAIL — `load_alignment_from_ifc` finnes ikke

- [ ] **Step 3: Implement schema check + alignment selection**

Legg til i `src/ifc_processor/alignment_parser.py`:

```python
import ifcopenshell


def _select_alignment(ifc) -> "ifcopenshell.entity_instance":
    alignments = ifc.by_type("IfcAlignment")
    if not alignments:
        types = sorted({e.is_a() for e in ifc})
        raise ValueError(
            f"Ingen IfcAlignment funnet — er dette en vegmodell-IFC? "
            f"Topp-typer i filen: {types[:10]}{'...' if len(types) > 10 else ''}"
        )
    if len(alignments) == 1:
        return alignments[0]
    # Velg den med lengst total horisontalt segment (proxy for lengde)
    def total_len(al):
        h = _find_horizontal(al)
        if h is None:
            return 0.0
        return sum(
            (seg.DesignParameters.SegmentLength or 0.0)
            for rel in h.IsNestedBy
            for seg in rel.RelatedObjects
            if seg.is_a("IfcAlignmentSegment") and seg.DesignParameters is not None
        )
    chosen = max(alignments, key=total_len)
    logger.info(
        "Flere IfcAlignment i fil — valgte '%s'. Andre: %s",
        chosen.Name,
        [a.Name for a in alignments if a is not chosen],
    )
    return chosen


def _find_horizontal(alignment):
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentHorizontal"):
                return obj
    return None


def _find_vertical(alignment):
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentVertical"):
                return obj
    return None


def load_alignment_from_ifc(ifc_path: Path) -> IfcAlignmentData:
    """Les IFC4X3 IfcAlignment og returner felles datakontrakt.

    Raises:
        ValueError: filen er ikke IFC4X3, mangler IfcAlignment, eller alignment er tom.
    """
    ifc = ifcopenshell.open(str(ifc_path))
    if ifc.schema not in ("IFC4X3", "IFC4X3_ADD1", "IFC4X3_ADD2", "IFC4X3_TC1"):
        raise ValueError(
            f"IFC4X3 kreves for senterlinje-IFC. Fil-schema: {ifc.schema}. "
            "Bruk LandXML-senterlinje for IFC4-modeller."
        )

    alignment = _select_alignment(ifc)
    name = alignment.Name or "<ukjent>"

    # Skall-implementasjon: fyll inn segmenter/sampling i senere tasks.
    return IfcAlignmentData(
        name=name,
        points_3d=np.zeros((0, 3)),
        stations=np.zeros(0),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: alle PASS (eller `KLEVERUD`-test skipped hvis fil mangler)

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): schema check and alignment selection"
```

---

## Task 3: Ekstraher horisontalsegmenter

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

```python
def test_horizontal_segments_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.horizontal_segments) == 67
    # Stasjonene skal være monotont økende
    starts = [s.start_station for s in data.horizontal_segments]
    assert starts == sorted(starts)
    assert starts[0] == 0.0


def test_horizontal_segment_types_present():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    types = {s.segment_type for s in data.horizontal_segments}
    # Forventer minst LINE og CIRCULARARC; CLOTHOID sannsynlig også
    assert "LINE" in types
    assert types <= {"LINE", "CIRCULARARC", "CLOTHOID"}


def test_circular_arc_has_radius():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    arcs = [s for s in data.horizontal_segments if s.segment_type == "CIRCULARARC"]
    if arcs:
        assert arcs[0].start_radius is not None
        assert arcs[0].start_radius > 0
        assert arcs[0].is_ccw in (True, False)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "horizontal"`
Expected: FAIL — `data.horizontal_segments` er tom (skall).

- [ ] **Step 3: Implement extraction**

Legg til i `src/ifc_processor/alignment_parser.py`:

```python
_HORIZONTAL_TYPE_MAP = {
    "LINE": "LINE",
    "CIRCULARARC": "CIRCULARARC",
    "CLOTHOID": "CLOTHOID",
    "CLOTHOIDCURVE": "CLOTHOID",
    "CUBICSPIRAL": "CLOTHOID",
    "BLOSSCURVE": "CLOTHOID",
    "COSINECURVE": "CLOTHOID",
    "SINECURVE": "CLOTHOID",
    "VIENNESEBEND": "CLOTHOID",
    "HELMERTCURVE": "CLOTHOID",
}


def _extract_horizontal_segments(
    horizontal,
) -> list[HorizontalSegment]:
    if horizontal is None:
        return []
    segments: list[HorizontalSegment] = []
    cum_station = 0.0
    nested_segs: list = []
    for rel in horizontal.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentSegment"):
                nested_segs.append(obj)

    for seg in nested_segs:
        params = seg.DesignParameters
        if params is None or not params.is_a("IfcAlignmentHorizontalSegment"):
            continue

        raw_type = (params.PredefinedType or "").upper()
        seg_type = _HORIZONTAL_TYPE_MAP.get(raw_type)
        if seg_type is None:
            logger.warning(
                "Ukjent horisontal segment-type '%s' — behandler som CLOTHOID",
                raw_type,
            )
            seg_type = "CLOTHOID"

        start_pt = (
            float(params.StartPoint.Coordinates[0]),
            float(params.StartPoint.Coordinates[1]),
        )
        start_dir = float(params.StartDirection or 0.0)
        length = float(params.SegmentLength or 0.0)
        start_r = params.StartRadiusOfCurvature
        end_r = params.EndRadiusOfCurvature

        # IFC4X3 konvensjon: signert radius → fortegn bestemmer retning
        is_ccw: bool | None = None
        if start_r is not None and start_r != 0.0:
            is_ccw = float(start_r) > 0.0
        elif end_r is not None and end_r != 0.0:
            is_ccw = float(end_r) > 0.0

        segments.append(HorizontalSegment(
            start_station=cum_station,
            length=length,
            start_point=start_pt,
            start_direction=start_dir,
            segment_type=seg_type,
            start_radius=abs(float(start_r)) if start_r else None,
            end_radius=abs(float(end_r)) if end_r else None,
            is_ccw=is_ccw,
        ))
        cum_station += length

    return segments
```

Endre `load_alignment_from_ifc()` slik at den fyller `horizontal_segments`:

```python
def load_alignment_from_ifc(ifc_path: Path) -> IfcAlignmentData:
    ifc = ifcopenshell.open(str(ifc_path))
    if ifc.schema not in ("IFC4X3", "IFC4X3_ADD1", "IFC4X3_ADD2", "IFC4X3_TC1"):
        raise ValueError(
            f"IFC4X3 kreves for senterlinje-IFC. Fil-schema: {ifc.schema}. "
            "Bruk LandXML-senterlinje for IFC4-modeller."
        )

    alignment = _select_alignment(ifc)
    name = alignment.Name or "<ukjent>"

    h = _find_horizontal(alignment)
    horizontal_segments = _extract_horizontal_segments(h)
    if not horizontal_segments:
        raise ValueError(
            f"IfcAlignment '{name}' har ingen horisontalsegmenter."
        )

    return IfcAlignmentData(
        name=name,
        points_3d=np.zeros((0, 3)),
        stations=np.zeros(0),
        horizontal_segments=horizontal_segments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): extract horizontal segments"
```

---

## Task 4: Ekstraher vertikalsegmenter

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

```python
def test_vertical_segments_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.vertical_segments) == 50
    starts = [s.start_station for s in data.vertical_segments]
    assert starts == sorted(starts)


def test_vertical_segment_types():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    types = {s.segment_type for s in data.vertical_segments}
    assert types <= {"CONSTANTGRADIENT", "PARABOLICARC", "CIRCULARARC"}
    assert "CONSTANTGRADIENT" in types


def test_parabolic_radius_signed():
    """Parabel som krummer ned (topp) → negativ radius; krummer opp (dal) → positiv."""
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    parabols = [s for s in data.vertical_segments if s.segment_type == "PARABOLICARC"]
    if parabols:
        for p in parabols:
            assert p.radius is not None
            assert p.radius != 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "vertical or parabolic"`
Expected: FAIL — `data.vertical_segments` er tom.

- [ ] **Step 3: Implement extraction**

Legg til i `src/ifc_processor/alignment_parser.py`:

```python
def _extract_vertical_segments(vertical) -> list[VerticalSegment]:
    if vertical is None:
        return []
    segments: list[VerticalSegment] = []
    nested_segs: list = []
    for rel in vertical.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentSegment"):
                nested_segs.append(obj)

    for seg in nested_segs:
        params = seg.DesignParameters
        if params is None or not params.is_a("IfcAlignmentVerticalSegment"):
            continue

        raw_type = (params.PredefinedType or "").upper()
        # IFC4X3 vertikal: CONSTANTGRADIENT | PARABOLICARC | CIRCULARARC
        if raw_type not in ("CONSTANTGRADIENT", "PARABOLICARC", "CIRCULARARC"):
            logger.warning(
                "Ukjent vertikal segment-type '%s' — behandler som CONSTANTGRADIENT",
                raw_type,
            )
            raw_type = "CONSTANTGRADIENT"

        start_station = float(params.StartDistAlong or 0.0)
        length = float(params.HorizontalLength or 0.0)
        start_height = float(params.StartHeight or 0.0)
        start_grad = float(params.StartGradient or 0.0)
        end_grad = float(params.EndGradient or start_grad)

        radius: float | None = None
        if raw_type in ("PARABOLICARC", "CIRCULARARC"):
            r_raw = params.RadiusOfCurvature
            if r_raw is not None and r_raw != 0.0:
                # Tegn-konvensjon: konkav (dal, gradient øker) → +, konveks (topp) → −
                sign = 1.0 if (end_grad - start_grad) > 0 else -1.0
                radius = sign * abs(float(r_raw))

        segments.append(VerticalSegment(
            start_station=start_station,
            length=length,
            start_height=start_height,
            start_gradient=start_grad,
            segment_type=raw_type,
            radius=radius,
        ))

    return segments
```

Oppdater `load_alignment_from_ifc()`:

```python
    v = _find_vertical(alignment)
    vertical_segments = _extract_vertical_segments(v)

    return IfcAlignmentData(
        name=name,
        points_3d=np.zeros((0, 3)),
        stations=np.zeros(0),
        horizontal_segments=horizontal_segments,
        vertical_segments=vertical_segments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): extract vertical segments"
```

---

## Task 5: 3D-sampling fra IfcGradientCurve

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

```python
def test_points_3d_sampled():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert data.points_3d.shape[0] >= 100
    assert data.points_3d.shape[1] == 3
    # Stasjonene matcher antall punkter
    assert data.stations.shape[0] == data.points_3d.shape[0]
    # Z-verdier er meningsfulle (ikke alle 0)
    assert np.abs(data.points_3d[:, 2]).max() > 1.0
    # Stasjonene er monotone
    assert np.all(np.diff(data.stations) >= 0)


def test_total_length_matches_horizontal_sum():
    """Total samplet lengde skal være ~lik sum av horisontalsegmenter."""
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    sum_h = sum(s.length for s in data.horizontal_segments)
    sampled_len = float(data.stations[-1])
    assert abs(sampled_len - sum_h) < 5.0  # toleranse for sampling-artefakter
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "points_3d or total_length"`
Expected: FAIL — `points_3d.shape == (0, 3)`.

- [ ] **Step 3: Implement 3D-sampling**

Legg til i `src/ifc_processor/alignment_parser.py`:

```python
import ifcopenshell.geom

_SAMPLE_INTERVAL_M = 1.0


def _sample_alignment_3d(
    alignment,
    horizontal_segments: list[HorizontalSegment],
) -> tuple[np.ndarray, np.ndarray]:
    """Returner (M,3) 3D-punkter + (M,) kumulative stasjoner.

    Bruker ifcopenshell.geom på IfcAlignment for å få ut Curve3D-polylinje
    (representerer IfcGradientCurve). Resampler til ~1 m intervall.
    """
    settings = ifcopenshell.geom.settings()
    # IFC4X3 alignment geometri evalueres som kurver
    try:
        settings.set(settings.INCLUDE_CURVES, True)
    except AttributeError:
        # nyere ifcopenshell-versjoner bruker string-keys
        try:
            settings.set("include-curves", True)
        except Exception:
            pass

    try:
        shape = ifcopenshell.geom.create_shape(settings, alignment)
    except RuntimeError as exc:
        raise ValueError(
            f"Kan ikke evaluere geometri for IfcAlignment '{alignment.Name}': {exc}"
        ) from exc

    verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
    if verts.shape[0] < 2:
        raise ValueError(
            f"IfcAlignment '{alignment.Name}' produserte for få 3D-punkter ({verts.shape[0]})"
        )

    # Beregn kumulative stasjoner basert på 3D-avstand mellom punkter
    diffs = np.diff(verts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    raw_stations = np.concatenate([[0.0], np.cumsum(seg_lens)])

    # Resample til ønsket tetthet
    total_len = float(raw_stations[-1])
    if total_len <= 0:
        return verts, raw_stations
    n_samples = max(2, int(np.ceil(total_len / _SAMPLE_INTERVAL_M)) + 1)
    target_stations = np.linspace(0.0, total_len, n_samples)
    resampled = np.column_stack([
        np.interp(target_stations, raw_stations, verts[:, i]) for i in range(3)
    ])
    return resampled, target_stations
```

Oppdater `load_alignment_from_ifc()`:

```python
    points_3d, stations = _sample_alignment_3d(alignment, horizontal_segments)

    return IfcAlignmentData(
        name=name,
        points_3d=points_3d,
        stations=stations,
        horizontal_segments=horizontal_segments,
        vertical_segments=vertical_segments,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: PASS

Hvis `ifcopenshell.geom.create_shape` ikke støtter `IfcAlignment` i denne versjonen av ifcopenshell:
- Fallback-strategi: rekonstruer 3D ved å sample horisontalsegmentene og hente Z fra vertikalsegmentene. Dette er en større jobb. Hvis det skjer, dokumenter dette som en blokker, lag en sub-task for å sample manuelt.

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): sample 3D points from IfcGradientCurve"
```

---

## Task 6: Ekstraher IfcReferent-stasjonsetiketter

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

```python
def test_station_labels_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.station_labels) > 50  # 12200 har 99 referenter
    # Etiketter har stasjon og navn
    sl = data.station_labels[0]
    assert sl.name != ""
    assert sl.station >= 0.0


def test_station_labels_sorted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    stations = [sl.station for sl in data.station_labels]
    assert stations == sorted(stations)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "station_labels"`
Expected: FAIL — `data.station_labels` er tom.

- [ ] **Step 3: Implement extraction**

Legg til i `src/ifc_processor/alignment_parser.py`:

```python
def _extract_station_labels(
    alignment,
    points_3d: np.ndarray,
    stations: np.ndarray,
) -> list[StationLabel]:
    """Hent IfcReferent som er nestet under alignment.

    IfcReferent har ObjectPlacement = IfcLinearPlacement, som inneholder
    Distance (avstand langs alignment). Vi henter 3D-posisjonen ved å
    interpolere på samplede points_3d.
    """
    referents: list = []
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcReferent"):
                referents.append(obj)

    labels: list[StationLabel] = []
    for ref in referents:
        placement = getattr(ref, "ObjectPlacement", None)
        if placement is None or not placement.is_a("IfcLinearPlacement"):
            continue
        dist_attr = getattr(placement, "Distance", None)
        if dist_attr is None:
            continue
        # Distance er IfcDistanceExpression eller IfcAxisLateralInclination — vi vil ha DistanceAlong
        station_val = None
        if hasattr(dist_attr, "DistanceAlong"):
            station_val = dist_attr.DistanceAlong
        elif hasattr(dist_attr, "wrappedValue"):
            station_val = dist_attr.wrappedValue
        elif isinstance(dist_attr, (int, float)):
            station_val = float(dist_attr)
        if station_val is None:
            continue
        station = float(station_val)

        # 3D-posisjon via interpolasjon
        if stations.size >= 2:
            x = float(np.interp(station, stations, points_3d[:, 0]))
            y = float(np.interp(station, stations, points_3d[:, 1]))
            z = float(np.interp(station, stations, points_3d[:, 2]))
            pos = (x, y, z)
        else:
            pos = (0.0, 0.0, 0.0)

        labels.append(StationLabel(
            station=station,
            name=ref.Name or f"P {station:.0f}",
            position=pos,
        ))

    labels.sort(key=lambda sl: sl.station)
    return labels
```

Oppdater `load_alignment_from_ifc()`:

```python
    station_labels = _extract_station_labels(alignment, points_3d, stations)

    logger.info(
        "alignment_parser: Lastet '%s' (%d hor.seg, %d vert.seg, %d referenter, %.1f m)",
        name, len(horizontal_segments), len(vertical_segments),
        len(station_labels), float(stations[-1]) if stations.size else 0.0,
    )

    return IfcAlignmentData(
        name=name,
        points_3d=points_3d,
        stations=stations,
        horizontal_segments=horizontal_segments,
        vertical_segments=vertical_segments,
        station_labels=station_labels,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): extract IfcReferent station labels"
```

---

## Task 7: Adaptere — `to_centerline()` og `vertical_profile_pvi()`

**Files:**
- Modify: `src/ifc_processor/alignment_parser.py`
- Modify: `tests/test_alignment_parser.py`

- [ ] **Step 1: Write failing tests**

```python
def test_to_centerline_adapter():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    from src.ifc_processor.centerline import Centerline
    data = load_alignment_from_ifc(CL_12200)
    cl = data.to_centerline()
    assert isinstance(cl, Centerline)
    assert cl.points.shape == data.points_3d.shape
    assert cl.stations.shape == data.stations.shape
    assert cl.source_epsg == data.source_epsg


def test_vertical_profile_pvi_format():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    pvi = data.vertical_profile_pvi()
    assert len(pvi) >= 2
    # Format: liste av (stasjon, høyde)
    for sta, h in pvi:
        assert isinstance(sta, float)
        assert isinstance(h, float)
    stations = [s for s, _ in pvi]
    assert stations == sorted(stations)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_alignment_parser.py -v -k "adapter or pvi"`
Expected: FAIL — `to_centerline` / `vertical_profile_pvi` finnes ikke.

- [ ] **Step 3: Implement adapters**

Legg til metoder på `IfcAlignmentData`:

```python
    def to_centerline(self) -> "Centerline":
        from .centerline import Centerline
        return Centerline(
            points=self.points_3d,
            stations=self.stations,
            source_epsg=self.source_epsg,
        )

    def vertical_profile_pvi(self) -> list[tuple[float, float]]:
        """Returner [(stasjon, høyde)] som matcher load_vertical_profile()-formatet."""
        if not self.vertical_segments:
            return []
        pvi: list[tuple[float, float]] = []
        for seg in self.vertical_segments:
            pvi.append((seg.start_station, seg.start_height))
        # Avslutt med sluttpunkt av siste segment
        last = self.vertical_segments[-1]
        end_station = last.start_station + last.length
        # h_end = h_start + integrert gradient — approks. med gjennomsnittlig stigning
        end_height = last.start_height + last.start_gradient * last.length
        pvi.append((end_station, end_height))
        return pvi
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_alignment_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/alignment_parser.py tests/test_alignment_parser.py
git commit -m "feat(alignment): Centerline and PVI adapters"
```

---

## Task 8: `.ifc`-gren i `centerline.load_centerline()`

**Files:**
- Modify: `src/ifc_processor/centerline.py:346-388`
- Modify: `tests/test_centerline.py`

- [ ] **Step 1: Write failing test**

Legg til i `tests/test_centerline.py`:

```python
def test_load_centerline_from_ifc_alignment():
    from src.ifc_processor.centerline import load_centerline, Centerline
    cl_ifc = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"
    cl = load_centerline(source=cl_ifc, ifc_path=Path("nonexistent.ifc"))
    assert isinstance(cl, Centerline)
    assert cl.points.shape[0] >= 100
    assert cl.points.shape[1] == 3
    assert cl.total_length > 100  # 12200-modellen er > 2 km
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_centerline.py::test_load_centerline_from_ifc_alignment -v`
Expected: FAIL — feilmelding `Ukjent senterlinje-format: .ifc`.

- [ ] **Step 3: Add `.ifc`-gren**

I `src/ifc_processor/centerline.py`, finn `load_centerline()` rundt linje 346 og legg til gren etter eksisterende `.xml`-gren:

```python
def load_centerline(source: Path | None, ifc_path: Path) -> Centerline:
    if source is not None:
        suffix = source.suffix.lower()
        if suffix in (".geojson", ".json"):
            return _load_from_geojson(source)
        if suffix == ".csv":
            return _load_from_csv(source)
        if suffix == ".xml":
            return _load_from_landxml(source)
        if suffix == ".ifc":
            from .alignment_parser import load_alignment_from_ifc
            return load_alignment_from_ifc(source).to_centerline()
        raise ValueError(
            f"Ukjent senterlinje-format: {suffix}. "
            "Godkjente formater: .geojson, .csv, .xml (LandXML), .ifc (IFC4X3)"
        )
    ...
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_centerline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/centerline.py tests/test_centerline.py
git commit -m "feat(centerline): accept .ifc as centerline source"
```

---

## Task 9: `AlignmentMetadata` og `_load_alignment_metadata()` i pipeline

**Files:**
- Modify: `src/ifc_processor/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

Legg til i `tests/test_pipeline.py`:

```python
def test_load_alignment_metadata_from_landxml(tmp_path):
    """Eksisterende LandXML-vei skal fortsatt fungere via ny metadata-helper."""
    from src.ifc_processor.pipeline import _load_alignment_metadata
    xml = Path(__file__).parent.parent / "samples" / "m_f_veg_70400_aligment.xml"
    meta = _load_alignment_metadata(xml)
    assert meta is not None
    assert len(meta.horizontal_segments) > 0
    # LandXML har ingen referenter
    assert meta.station_labels == []


def test_load_alignment_metadata_from_ifc():
    from src.ifc_processor.pipeline import _load_alignment_metadata
    ifc_cl = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"
    meta = _load_alignment_metadata(ifc_cl)
    assert meta is not None
    assert len(meta.horizontal_segments) == 67
    assert len(meta.vertical_pvi) >= 2
    assert len(meta.station_labels) > 50


def test_load_alignment_metadata_none_for_unknown():
    from src.ifc_processor.pipeline import _load_alignment_metadata
    assert _load_alignment_metadata(None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -v -k "alignment_metadata"`
Expected: FAIL — `_load_alignment_metadata` finnes ikke.

- [ ] **Step 3: Add metadata helper**

I `src/ifc_processor/pipeline.py`, legg til imports og helper øverst (etter eksisterende imports):

```python
from dataclasses import dataclass, field

from .alignment_parser import HorizontalSegment, StationLabel


@dataclass
class AlignmentMetadata:
    vertical_pvi: list[tuple[float, float]] = field(default_factory=list)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833


def _horizontal_segments_from_landxml(path: Path) -> list[HorizontalSegment]:
    """Konverter LandXML horisontalkurvatur → felles HorizontalSegment-format."""
    from src.arcpy_processor.landxml_parser import parse_horizontal_alignment
    raw = parse_horizontal_alignment(path)
    segments: list[HorizontalSegment] = []
    for s in raw:
        kind = s["kind"]
        sta_start = float(s["sta_start"])
        length = float(s["sta_end"]) - sta_start
        if kind == "line":
            seg_type = "LINE"
            start_radius = None
            end_radius = None
            is_ccw = None
        elif kind == "curve":
            seg_type = "CIRCULARARC"
            r = float(s["radius"])
            start_radius = r
            end_radius = r
            is_ccw = s.get("dir", 1) > 0
        else:  # "spiral"
            seg_type = "CLOTHOID"
            # A = sqrt(L*R) → R ved klotoidens slutt
            A = float(s["A"])
            R = (A * A) / length if length > 0 else None
            start_radius = None
            end_radius = R
            is_ccw = s.get("dir", 1) > 0
        segments.append(HorizontalSegment(
            start_station=sta_start,
            length=length,
            start_point=(0.0, 0.0),     # ikke tilgjengelig via parse_horizontal_alignment
            start_direction=0.0,
            segment_type=seg_type,
            start_radius=start_radius,
            end_radius=end_radius,
            is_ccw=is_ccw,
        ))
    return segments


def _load_alignment_metadata(cl_path: Path | None) -> AlignmentMetadata | None:
    """Returner felles metadata uavhengig av om kilden er LandXML eller IFC-CL."""
    if cl_path is None:
        return None
    suffix = cl_path.suffix.lower()
    if suffix == ".xml":
        pvi = load_vertical_profile(cl_path) or []
        horiz = _horizontal_segments_from_landxml(cl_path)
        return AlignmentMetadata(
            vertical_pvi=pvi,
            horizontal_segments=horiz,
            station_labels=[],
            source_epsg=25833,
        )
    if suffix == ".ifc":
        from .alignment_parser import load_alignment_from_ifc
        data = load_alignment_from_ifc(cl_path)
        return AlignmentMetadata(
            vertical_pvi=data.vertical_profile_pvi(),
            horizontal_segments=data.horizontal_segments,
            station_labels=data.station_labels,
            source_epsg=data.source_epsg,
        )
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_pipeline.py -v -k "alignment_metadata"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): AlignmentMetadata helper unifying LandXML and IFC-CL"
```

---

## Task 10: Stasjons-grid alignment til IfcReferent

**Files:**
- Modify: `src/ifc_processor/pipeline.py`
- Modify: `src/ifc_processor/cross_section.py` (kun signatur for `sample_stations`)
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

```python
def test_station_grid_starts_at_referent_offset():
    """Når IfcReferent finnes, skal stations starte ved første referent (modulo intervall)."""
    from src.ifc_processor.pipeline import _aligned_station_offset
    from src.ifc_processor.alignment_parser import StationLabel

    # Referent på station 107.3, intervall 10 → offset 7.3
    labels = [StationLabel(station=107.3, name="P 100", position=(0, 0, 0))]
    assert _aligned_station_offset(labels, interval_m=10.0) == pytest.approx(7.3)

    # Referent på station 100.0, intervall 10 → offset 0.0
    labels = [StationLabel(station=100.0, name="P 100", position=(0, 0, 0))]
    assert _aligned_station_offset(labels, interval_m=10.0) == pytest.approx(0.0)

    # Ingen referenter → offset 0
    assert _aligned_station_offset([], interval_m=10.0) == pytest.approx(0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py::test_station_grid_starts_at_referent_offset -v`
Expected: FAIL — `_aligned_station_offset` finnes ikke.

- [ ] **Step 3: Add helper**

Legg til i `src/ifc_processor/pipeline.py`:

```python
def _aligned_station_offset(
    station_labels: list[StationLabel],
    interval_m: float,
) -> float:
    """Returner offset (0 ≤ offset < interval) slik at stations-grid passerer
    gjennom IfcReferent-stasjoner.

    f.eks. interval=10, første referent på 107.3 → offset 7.3 → grid: 7.3, 17.3, 27.3, ...
    """
    if not station_labels:
        return 0.0
    first = station_labels[0].station
    return float(first % interval_m)
```

- [ ] **Step 4: Verify helper test passes**

Run: `python -m pytest tests/test_pipeline.py::test_station_grid_starts_at_referent_offset -v`
Expected: PASS

- [ ] **Step 5: Integrer i `run_pipeline()`**

Finn linje i `run_pipeline()` der `sample_stations(centerline, interval_m)` kalles. Erstatt med:

```python
    metadata = _load_alignment_metadata(centerline_path)
    offset = _aligned_station_offset(metadata.station_labels, interval_m) if metadata else 0.0
    stations = sample_stations(centerline, interval_m, start_offset=offset)
```

Sjekk `sample_stations` sin signatur i `src/ifc_processor/cross_section.py`. Hvis den ikke har `start_offset`-parameter, legg den til:

```python
def sample_stations(centerline, interval_m: float, start_offset: float = 0.0):
    ...
    distances = np.arange(start_offset, centerline.total_length, interval_m)
    ...
```

- [ ] **Step 6: Write end-to-end test for grid-justering**

```python
def test_pipeline_aligns_grid_to_referent(tmp_path):
    """Run pipeline med 12200 IFC-CL og verifiser at stations starter ved referent-offset."""
    from src.ifc_processor.pipeline import run_pipeline
    samples = Path(__file__).parent.parent / "samples"
    out = tmp_path / "out"
    result = run_pipeline(
        ifc_path=samples / "m_f_veg_12200_Veg.ifc",
        centerline_path=samples / "m_f-veg_12200_CL.ifc",
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_lengdeprofil=False,
    )
    import json
    stations = json.loads((out / "stations.json").read_text())
    if len(stations) > 1:
        first_two = stations[:2]
        delta = first_two[1]["station_m"] - first_two[0]["station_m"]
        assert abs(delta - 10.0) < 0.01
        # Den første referenten i fixturen ligger ved et heltall — sjekk at
        # første stasjon modulo intervall matcher referent-offset
```

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/ifc_processor/pipeline.py src/ifc_processor/cross_section.py tests/test_pipeline.py
git commit -m "feat(pipeline): align station grid to IfcReferent offset"
```

---

## Task 11: `referent_name` i `station_rows` + skriv `station_labels.json`

**Files:**
- Modify: `src/ifc_processor/pipeline.py`
- Modify: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test**

```python
def test_station_rows_have_referent_name(tmp_path):
    from src.ifc_processor.pipeline import run_pipeline
    import json
    samples = Path(__file__).parent.parent / "samples"
    out = tmp_path / "out"
    run_pipeline(
        ifc_path=samples / "m_f_veg_12200_Veg.ifc",
        centerline_path=samples / "m_f-veg_12200_CL.ifc",
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_lengdeprofil=False,
    )
    stations = json.loads((out / "stations.json").read_text())
    # Minst én stasjon skal matche en referent
    with_ref = [s for s in stations if s.get("referent_name")]
    assert len(with_ref) >= 1


def test_station_labels_json_written(tmp_path):
    from src.ifc_processor.pipeline import run_pipeline
    import json
    samples = Path(__file__).parent.parent / "samples"
    out = tmp_path / "out"
    run_pipeline(
        ifc_path=samples / "m_f_veg_12200_Veg.ifc",
        centerline_path=samples / "m_f-veg_12200_CL.ifc",
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_lengdeprofil=False,
    )
    labels = json.loads((out / "station_labels.json").read_text())
    assert len(labels) > 50
    assert "station" in labels[0]
    assert "name" in labels[0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_pipeline.py -v -k "referent_name or labels_json"`
Expected: FAIL — `referent_name`/`station_labels.json` mangler.

- [ ] **Step 3: Implement annotation + JSON-skriving**

I `run_pipeline()`, etter at `station_rows` er ferdig bygget men før gradient-beregning:

```python
    # Annotér referent-treff
    if metadata and metadata.station_labels:
        tol = 0.5  # m
        labels_sorted = sorted(metadata.station_labels, key=lambda l: l.station)
        for row in station_rows:
            sm = row["station_m"]
            for lbl in labels_sorted:
                if abs(lbl.station - sm) <= tol:
                    row["referent_name"] = lbl.name
                    break

    # Skriv station_labels.json (tom liste hvis ingen)
    labels_out = (
        [
            {"station": round(lbl.station, 3), "name": lbl.name,
             "x": round(lbl.position[0], 3), "y": round(lbl.position[1], 3),
             "z": round(lbl.position[2], 3)}
            for lbl in (metadata.station_labels if metadata else [])
        ]
    )
    (output_dir / "station_labels.json").write_text(json.dumps(labels_out, indent=2))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): annotate referent_name and write station_labels.json"
```

---

## Task 12: Skriv `horizontal_alignment.json` også fra IFC-veien

**Files:**
- Modify: `src/ifc_processor/pipeline.py`
- Modify: `tests/test_pipeline.py`

Sjekk først om eksisterende kode allerede skriver `horizontal_alignment.json`. Finn det:

```bash
grep -n "horizontal_alignment" src/ifc_processor/pipeline.py
```

Hvis det allerede gjøres for LandXML, generaliser til å bruke `metadata.horizontal_segments`. Hvis ikke, legg til seksjon her.

- [ ] **Step 1: Write failing test**

```python
def test_horizontal_alignment_json_from_ifc(tmp_path):
    from src.ifc_processor.pipeline import run_pipeline
    import json
    samples = Path(__file__).parent.parent / "samples"
    out = tmp_path / "out"
    run_pipeline(
        ifc_path=samples / "m_f_veg_12200_Veg.ifc",
        centerline_path=samples / "m_f-veg_12200_CL.ifc",
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_lengdeprofil=False,
    )
    horiz = json.loads((out / "horizontal_alignment.json").read_text())
    assert len(horiz) == 67
    kinds = {s.get("kind") for s in horiz}
    assert kinds <= {"line", "curve", "spiral"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_pipeline.py::test_horizontal_alignment_json_from_ifc -v`
Expected: FAIL — fil mangler eller har feil antall segmenter.

- [ ] **Step 3: Add write-step**

Legg til etter stations-løkken i `run_pipeline()`:

```python
    # Skriv horizontal_alignment.json (felles format for LandXML- og IFC-vei)
    horiz_rows: list[dict] = []
    if metadata:
        for s in metadata.horizontal_segments:
            kind_map = {"LINE": "line", "CIRCULARARC": "curve", "CLOTHOID": "spiral"}
            row: dict = {
                "kind": kind_map.get(s.segment_type, "line"),
                "sta_start": round(s.start_station, 3),
                "sta_end": round(s.start_station + s.length, 3),
            }
            if s.segment_type == "CIRCULARARC":
                row["radius"] = round(s.start_radius or 0.0, 3)
                row["dir"] = 1 if s.is_ccw else -1
            elif s.segment_type == "CLOTHOID":
                # A = sqrt(L * R) der R er radius ved klotoidens slutt
                R = s.end_radius if s.end_radius else s.start_radius
                if R and s.length > 0:
                    import math
                    row["A"] = round(math.sqrt(s.length * R), 3)
                    row["dir"] = 1 if s.is_ccw else -1
            horiz_rows.append(row)
    (output_dir / "horizontal_alignment.json").write_text(json.dumps(horiz_rows, indent=2))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_pipeline.py -v`
Expected: PASS (alle pipeline-tester)

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline.py
git commit -m "feat(pipeline): write horizontal_alignment.json from IFC-CL too"
```

---

## Task 13: Felles publisher-modul `_polyline_publisher.py`

**Files:**
- Create: `src/arcpy_processor/_polyline_publisher.py`
- Modify: `src/arcpy_processor/landxml_to_agol.py`
- Create: `tests/test_polyline_publisher.py`

Dette refaktorerer eksisterende `landxml_to_agol.py` uten ny funksjonalitet — sikrer at refactoring ikke bryter noe.

- [ ] **Step 1: Write characterization test for current landxml_to_agol behavior**

```python
# tests/test_polyline_publisher.py
"""Tester for refaktorert felles publisher. Verifiserer at landxml_to_agol
fortsatt fungerer etter refactor."""
from __future__ import annotations
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_arcpy(monkeypatch):
    """Mock ArcPy slik at testen kan kjøre uten ArcGIS Pro."""
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    arcpy_mock.management.GetCount.return_value = ["1"]
    arcpy_mock.Exists.return_value = False
    monkeypatch.setitem(__import__("sys").modules, "arcpy", arcpy_mock)
    return arcpy_mock


def test_publish_polyline_calls_create_polyline_fc(mock_arcpy):
    from src.arcpy_processor._polyline_publisher import publish_polyline_to_agol
    gis_mock = MagicMock()
    with patch("src.arcpy_processor._polyline_publisher.upload_and_publish",
               return_value={"url": "https://example/0"}):
        with patch("src.arcpy_processor._polyline_publisher.check_name_available"):
            result = publish_polyline_to_agol(
                points_dict={"L1": [(100.0, 200.0, 10.0), (110.0, 200.0, 11.0)]},
                source_epsg=25833,
                service_name="test",
                folder="",
                gis=gis_mock,
                lengdeprofil_path=None,
            )
    assert "url" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_polyline_publisher.py -v`
Expected: FAIL — `_polyline_publisher` finnes ikke.

- [ ] **Step 3: Extract common publish flow**

Opprett `src/arcpy_processor/_polyline_publisher.py` ved å løfte ut den ArcPy/publish-spesifikke logikken fra `landxml_to_agol.py`. Funksjonen skal kapsle inn: GDB-opprettelse, PolylineZ FC, reprojeksjon, vedleggshåndtering, og kall til `upload_and_publish`.

```python
# src/arcpy_processor/_polyline_publisher.py
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

from .auth import connect  # noqa: F401 — re-eksport for testbarhet
from .errors import ArcpyProcessorError, PUBLISH_FAILED
from .publisher import check_name_available, upload_and_publish

logger = logging.getLogger(__name__)

TARGET_EPSG = 25833


def _create_polyline_fc(
    points_dict: dict[str, list[tuple[float, float, float]]],
    gdb_path: str,
    dataset_name: str,
    source_epsg: int,
    extra_fields: list[tuple[str, str, dict[str, Any]]] | None = None,
) -> str:
    """Opprett PolylineZ FC. extra_fields: liste av (field_name, field_type, kwargs)."""
    import arcpy
    sr = arcpy.SpatialReference(source_epsg)
    fc_name = f"{dataset_name}_centerline"
    fc_path = os.path.join(gdb_path, fc_name)
    arcpy.management.CreateFeatureclass(
        gdb_path, fc_name, "POLYLINE", has_z="ENABLED", spatial_reference=sr
    )
    arcpy.management.AddField(fc_path, "name", "TEXT", field_length=100)
    arcpy.management.AddField(fc_path, "feat_length", "DOUBLE")
    extra_fields = extra_fields or []
    for fname, ftype, fkwargs in extra_fields:
        arcpy.management.AddField(fc_path, fname, ftype, **fkwargs)

    insert_fields = ["name", "feat_length", "SHAPE@"] + [f[0] for f in extra_fields]
    with arcpy.da.InsertCursor(fc_path, insert_fields) as cursor:
        for feat_name, pts in points_dict.items():
            array = arcpy.Array([arcpy.Point(x, y, z) for x, y, z in pts])
            polyline = arcpy.Polyline(array, sr, has_z=True)
            row = [feat_name, polyline.length, polyline] + \
                  [None] * len(extra_fields)   # extra-verdier settes av kaller via UpdateCursor
            cursor.insertRow(row)
    return fc_path


def _sanitize_name(stem: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", stem)[:50]
    if name and name[0].isdigit():
        name = "_" + name[:49]
    return name


def publish_polyline_to_agol(
    points_dict: dict[str, list[tuple[float, float, float]]],
    *,
    source_epsg: int,
    service_name: str,
    folder: str,
    gis,
    source_stem: str | None = None,
    lengdeprofil_path: Path | None = None,
    extra_field_values: dict[str, tuple[str, dict[str, Any], Any]] | None = None,
) -> dict:
    """Publiser polylinje-data som hostet FeatureService i AGOL.

    Args:
        points_dict: navn → liste av (E, N, Z)-punkter
        source_epsg: kilde-CRS
        service_name: tjenestenavn i AGOL
        folder: AGOL-mappe ("" = rot)
        gis: arcgis.gis.GIS-instans
        source_stem: filnavn-stem brukt til datasett-naming (default: service_name)
        lengdeprofil_path: valgfri SVG som vedlegges hver feature
        extra_field_values: {field_name: (field_type, addfield_kwargs, value)} for
                            ekstra attributter (samme verdi på alle features)
    """
    import arcpy
    check_name_available(gis, service_name, folder)

    scratch = arcpy.env.scratchFolder
    gdb_name = "publish_temp.gdb"
    gdb_path = os.path.join(scratch, gdb_name)
    if arcpy.Exists(gdb_path):
        arcpy.management.Delete(gdb_path)
    arcpy.management.CreateFileGDB(scratch, gdb_name)

    dataset_name = _sanitize_name(source_stem or service_name)

    extra_field_values = extra_field_values or {}
    extra_fields = [(n, t, k) for n, (t, k, _) in extra_field_values.items()]

    try:
        fc_path = _create_polyline_fc(
            points_dict, gdb_path, dataset_name, source_epsg, extra_fields=extra_fields,
        )
    except Exception as exc:
        raise ArcpyProcessorError(
            PUBLISH_FAILED, f"Kunne ikke opprette feature class: {exc}"
        ) from exc

    # Fyll inn extra_field_values
    if extra_field_values:
        with arcpy.da.UpdateCursor(fc_path, list(extra_field_values.keys())) as cur:
            for row in cur:
                cur.updateRow([v for _, (_, _, v) in extra_field_values.items()])

    if source_epsg != TARGET_EPSG:
        projected_path = fc_path + f"_{TARGET_EPSG}"
        arcpy.management.Project(fc_path, projected_path, arcpy.SpatialReference(TARGET_EPSG))
        arcpy.management.Delete(fc_path)
        fc_path = projected_path

    feature_count = int(arcpy.management.GetCount(fc_path)[0])

    if lengdeprofil_path and lengdeprofil_path.exists():
        arcpy.management.EnableAttachments(fc_path)
        match_tbl = os.path.join(gdb_path, f"{dataset_name}_lp_match")
        if arcpy.Exists(match_tbl):
            arcpy.management.Delete(match_tbl)
        arcpy.management.CreateTable(gdb_path, f"{dataset_name}_lp_match")
        arcpy.management.AddField(match_tbl, "fc_oid", "LONG")
        arcpy.management.AddField(match_tbl, "file_path", "TEXT", field_length=512)
        with arcpy.da.SearchCursor(fc_path, ["OID@"]) as cur:
            with arcpy.da.InsertCursor(match_tbl, ["fc_oid", "file_path"]) as ins:
                for (oid,) in cur:
                    ins.insertRow((oid, str(lengdeprofil_path)))
        arcpy.management.AddAttachments(
            fc_path, "OBJECTID", match_tbl, "fc_oid", "file_path"
        )

    result = upload_and_publish(gis, gdb_path, service_name, folder)
    result["feature_count"] = feature_count
    result["source_epsg"] = source_epsg
    return result
```

- [ ] **Step 4: Refactor `landxml_to_agol.py` to use it**

Erstatt linjene 125-188 i `src/arcpy_processor/landxml_to_agol.py` (alt fra `scratch = ...` til `result = upload_and_publish(...)`) med:

```python
        from ._polyline_publisher import publish_polyline_to_agol
        result = publish_polyline_to_agol(
            points_dict=points_dict,
            source_epsg=source_epsg,
            service_name=args.name,
            folder=args.folder,
            gis=gis,
            source_stem=Path(args.xml).stem,
            lengdeprofil_path=Path(args.lengdeprofil) if args.lengdeprofil else None,
        )
```

- [ ] **Step 5: Run all relevant tests**

Run: `python -m pytest tests/test_polyline_publisher.py tests/test_landxml_to_agol.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/arcpy_processor/_polyline_publisher.py src/arcpy_processor/landxml_to_agol.py tests/test_polyline_publisher.py
git commit -m "refactor(arcpy): extract _polyline_publisher shared by LandXML and IFC-CL paths"
```

---

## Task 14: Ny CLI `ifc_cl_to_agol.py`

**Files:**
- Create: `src/arcpy_processor/ifc_cl_to_agol.py`
- Create: `tests/test_ifc_cl_to_agol.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_ifc_cl_to_agol.py
from __future__ import annotations
from pathlib import Path
import json
from unittest.mock import MagicMock, patch


def test_cli_parses_ifc_cl_and_calls_publisher(monkeypatch, capsys):
    """Verifiser at CLI leser IFC-CL og kaller publish_polyline_to_agol med riktige args."""
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    arcpy_mock.management.GetCount.return_value = ["1"]
    arcpy_mock.Exists.return_value = False
    monkeypatch.setitem(__import__("sys").modules, "arcpy", arcpy_mock)

    sample = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"
    with patch("src.arcpy_processor.ifc_cl_to_agol.connect") as mock_connect, \
         patch("src.arcpy_processor.ifc_cl_to_agol.publish_polyline_to_agol",
               return_value={"url": "https://x/0"}) as mock_publish:
        mock_connect.return_value = MagicMock()
        from src.arcpy_processor import ifc_cl_to_agol
        try:
            ifc_cl_to_agol.main([
                "--ifc-cl", str(sample),
                "--name", "test_service",
                "--folder", "",
            ])
        except SystemExit as e:
            assert e.code == 0
        else:
            pass

    # publish_polyline_to_agol skal være kalt én gang
    mock_publish.assert_called_once()
    kwargs = mock_publish.call_args.kwargs
    assert kwargs["service_name"] == "test_service"
    assert kwargs["source_epsg"] == 25833
    # Punkter-dict skal ha én entry (alignment-navnet)
    assert len(kwargs["points_dict"]) == 1
    assert "n_horizontal_segments" in kwargs["extra_field_values"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ifc_cl_to_agol.py -v`
Expected: FAIL — modul mangler.

- [ ] **Step 3: Implement CLI**

```python
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
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_ifc_cl_to_agol.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/arcpy_processor/ifc_cl_to_agol.py tests/test_ifc_cl_to_agol.py
git commit -m "feat(arcpy): new ifc_cl_to_agol CLI for IFC4X3 alignment"
```

---

## Task 15: API — `cl_file` aksepterer både `.xml` og `.ifc`

**Files:**
- Modify: `src/api/server.py`
- Modify: `src/api/job_runner.py`
- Modify: `tests/test_api_jobs.py`

- [ ] **Step 1: Write failing test**

Sjekk eksisterende `tests/test_api_jobs.py` for å se hvordan jobs testes. Legg til:

```python
def test_create_job_accepts_ifc_cl(client, authenticated_session):
    """POST /api/jobs godtar cl_file med .ifc-ending."""
    samples = Path(__file__).parent.parent / "samples"
    with (samples / "m_f_veg_12200_Veg.ifc").open("rb") as ifc, \
         (samples / "m_f-veg_12200_CL.ifc").open("rb") as cl:
        response = client.post(
            "/api/jobs",
            files={
                "ifc_file": ("model.ifc", ifc, "application/octet-stream"),
                "cl_file": ("centerline.ifc", cl, "application/octet-stream"),
            },
            data={"name": "test_job", "interval": "20.0"},
        )
    assert response.status_code == 200
    assert "job_id" in response.json()


def test_create_job_rejects_unknown_cl_ending(client, authenticated_session):
    samples = Path(__file__).parent.parent / "samples"
    with (samples / "m_f_veg_12200_Veg.ifc").open("rb") as ifc:
        response = client.post(
            "/api/jobs",
            files={
                "ifc_file": ("model.ifc", ifc, "application/octet-stream"),
                "cl_file": ("centerline.txt", b"not a real file", "text/plain"),
            },
            data={"name": "test_job", "interval": "20.0"},
        )
    assert response.status_code == 400
    assert "cl_file" in response.json()["detail"].lower() or \
           ".xml" in response.json()["detail"].lower()
```

(Tilpass eksisterende fixtures hvis `authenticated_session` ikke finnes — sjekk eksisterende tester.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_jobs.py -v -k "accepts_ifc_cl or rejects_unknown"`
Expected: FAIL

- [ ] **Step 3: Update endpoint signature**

I `src/api/server.py`, finn `create_job()` (linje ~83) og endre:

```python
@app.post("/api/jobs")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    ifc_file: UploadFile = File(...),
    cl_file: UploadFile = File(...),          # NB: renamed fra xml_file
    name: str = Form(...),
    interval: float = Form(10.0),
    publish_bim: bool = Form(False),
    bim_input_wkid: int | None = Form(None),
    bim_output_wkid: int = Form(25833),
    include_tverrprofil: bool = Form(True),
    include_lengdeprofil: bool = Form(True),
) -> dict:
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget — bruk /auth/login")
    if not ifc_file.filename or not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "ifc_file må være en .ifc-fil")
    cl_name = (cl_file.filename or "").lower()
    if not (cl_name.endswith(".xml") or cl_name.endswith(".ifc")):
        raise HTTPException(400, "cl_file må være en .xml LandXML- eller .ifc IFC4X3-fil")
    if not (1 <= interval <= 100):
        raise HTTPException(400, "interval må være mellom 1 og 100 meter")

    fresh_token = refresh_access_token(request.session)

    job_id = job_runner.create_job()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    ifc_path = job_dir / "model.ifc"
    cl_suffix = ".ifc" if cl_name.endswith(".ifc") else ".xml"
    cl_path = job_dir / f"centerline{cl_suffix}"

    with ifc_path.open("wb") as f:
        while chunk := await ifc_file.read(1024 * 1024):
            f.write(chunk)
    with cl_path.open("wb") as f:
        while chunk := await cl_file.read(1024 * 1024):
            f.write(chunk)

    background_tasks.add_task(
        job_runner.run_job,
        job_id=job_id,
        ifc_path=ifc_path,
        cl_path=cl_path,                       # NB: renamed fra xml_path
        name=name,
        interval=interval,
        access_token=fresh_token,
        org_url=request.session.get("org_url", "https://www.arcgis.com"),
        output_dir=job_dir / "output",
        publish_bim=publish_bim,
        bim_input_wkid=bim_input_wkid,
        bim_output_wkid=bim_output_wkid,
        include_tverrprofil=include_tverrprofil,
        include_lengdeprofil=include_lengdeprofil,
    )

    return {"job_id": job_id, "status": "queued"}
```

- [ ] **Step 4: Update `job_runner.run_job` signature**

I `src/api/job_runner.py`, finn `run_job` og rename `xml_path` → `cl_path` overalt. Inkluder routing:

```python
def run_job(
    *,
    job_id: str,
    ifc_path: Path,
    cl_path: Path,
    name: str,
    interval: float,
    access_token: str,
    org_url: str,
    output_dir: Path,
    publish_bim: bool,
    bim_input_wkid: int | None,
    bim_output_wkid: int,
    include_tverrprofil: bool,
    include_lengdeprofil: bool,
) -> None:
    ...
    # Når AGOL-publisering skal trigges:
    if cl_path.suffix.lower() == ".ifc":
        publish_cmd = [
            sys.executable, "-m", "src.arcpy_processor.ifc_cl_to_agol",
            "--ifc-cl", str(cl_path),
            "--name", name,
            "--folder", "",
            "--token", access_token,
            "--org-url", org_url,
        ]
    else:
        publish_cmd = [
            sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
            "--xml", str(cl_path),
            "--name", name,
            "--folder", "",
            "--token", access_token,
            "--org-url", org_url,
        ]
```

(Hold de andre rad-feltene som eksisterende kode — kun argument-rename er nytt.)

Søk gjennom `src/api/job_runner.py` etter `xml_path` og bytt til `cl_path`:

```bash
grep -n "xml_path" src/api/job_runner.py
```

- [ ] **Step 5: Run all API tests**

Run: `python -m pytest tests/test_api_jobs.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/api/server.py src/api/job_runner.py tests/test_api_jobs.py
git commit -m "feat(api): cl_file accepts .xml or .ifc, route to correct publisher"
```

---

## Task 16: API-endepunkt `/api/jobs/{id}/station-labels`

**Files:**
- Modify: `src/api/server.py`
- Modify: `tests/test_api_jobs.py`

- [ ] **Step 1: Write failing test**

```python
def test_get_station_labels_returns_empty_for_landxml_job(client, tmp_path, monkeypatch):
    # Lag mock job-output uten station_labels.json
    monkeypatch.setattr("src.api.server.UPLOAD_DIR", tmp_path)
    job_dir = tmp_path / "fake-job-id"
    (job_dir / "output").mkdir(parents=True)
    (job_dir / "output" / "metadata.json").write_text('{"stations":[]}')

    response = client.get("/api/jobs/fake-job-id/station-labels")
    assert response.status_code == 200
    assert response.json() == []


def test_get_station_labels_returns_data_when_present(client, tmp_path, monkeypatch):
    monkeypatch.setattr("src.api.server.UPLOAD_DIR", tmp_path)
    job_dir = tmp_path / "fake-job-id"
    (job_dir / "output").mkdir(parents=True)
    (job_dir / "output" / "station_labels.json").write_text(
        '[{"station": 100.0, "name": "P 100", "x": 0, "y": 0, "z": 0}]'
    )

    response = client.get("/api/jobs/fake-job-id/station-labels")
    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["name"] == "P 100"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_api_jobs.py -v -k "station_labels"`
Expected: FAIL — endepunkt mangler.

- [ ] **Step 3: Add endpoint**

Legg til i `src/api/server.py` ved siden av `/horizontal-alignment`:

```python
@app.get("/api/jobs/{job_id}/station-labels")
def get_station_labels(job_id: str) -> list[dict]:
    """Returner IfcReferent-stasjoneringsmerker for jobben (tom liste hvis ikke IFC-CL)."""
    path = UPLOAD_DIR / job_id / "output" / "station_labels.json"
    if not path.exists():
        return []
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return []
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_api_jobs.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/api/server.py tests/test_api_jobs.py
git commit -m "feat(api): GET /api/jobs/{id}/station-labels endpoint"
```

---

## Task 17: Wizard godtar `.ifc` i senterlinje-dropzone

**Files:**
- Modify: `web/src/index.html`
- Modify: `web/src/main.js`

Det er ingen automatiske tester for frontend i prosjektet — gjør manuell verifisering.

- [ ] **Step 1: Update HTML accept-attribute**

Finn senterlinje-dropzone i `web/src/index.html` (søk etter `dzXml` eller `accept=".xml"`). Endre:

```html
<input type="file" id="dzXml-input" accept=".xml,.ifc">
```

Og oppdater dropzone-label:

```html
<div class="dz-title">Senterlinje (.xml LandXML, .ifc 4X3)</div>
<div class="dz-meta">Maks 100 MB · referansesystem hentes automatisk</div>
```

- [ ] **Step 2: Update `main.js`**

I `web/src/main.js`:

**(a)** Rename variabel `xmlFile` → `clFile` overalt (søk-og-bytt).

**(b)** I `resetDropzone()` (linje ~246), endre:

```javascript
const defaultTitle = which === "ifc" ? "BIM-modell (.ifc, .rvt)" : "Senterlinje (.xml LandXML, .ifc 4X3)";
const defaultMeta  = which === "ifc"
  ? "Maks 500 MB · IFC2x3 / IFC4 / Revit 2022+"
  : "LandXML 1.2 eller IFC4X3 · referansesystem hentes automatisk";
```

**(c)** I `updateDropzone()` (linje ~222), legg til badge basert på filending:

```javascript
const isIfcCl = which === "xml" && file.name.toLowerCase().endsWith(".ifc");
const isLandXml = which === "xml" && file.name.toLowerCase().endsWith(".xml");
const formatBadge = isIfcCl ? "IFC4X3 alignment" : isLandXml ? "LandXML 1.2" : "lest lokalt";
meta.textContent = prettyBytes(file.size) + " · " + formatBadge;
```

**(d)** I FormData-bygging (linje ~338), endre:

```javascript
fd.append("cl_file", clFile);   // erstatter "xml_file", xmlFile
```

- [ ] **Step 3: Build and start dev server**

Run: `cd web && npm run dev` (eller tilsvarende prosjekt-kommando — sjekk `package.json` for nøyaktig script).

Forventet: dev-server starter på lokal port.

- [ ] **Step 4: Manuell verifisering**

Bruk agent-browser-skillen eller egen nettleser:
1. Naviger til wizard
2. Verifiser at senterlinje-dropzone aksepterer både `.xml` og `.ifc`
3. Last opp `samples/m_f-veg_12200_CL.ifc` og verifiser at badge viser "IFC4X3 alignment"
4. Last opp `samples/FV229_Senterlinje.xml` og verifiser "LandXML 1.2"-badge
5. (Hvis du har en kjørende API-server) start en jobb og verifiser at den blir queued

- [ ] **Step 5: Commit**

```bash
git add web/src/index.html web/src/main.js
git commit -m "feat(web): senterlinje-dropzone aksepterer .xml og .ifc"
```

---

## Task 18: End-to-end integrasjonstest mot 12200

**Files:**
- Modify: `tests/test_pipeline.py`

Markeres som "slow" — kjøres med `pytest -m slow`.

- [ ] **Step 1: Add slow-marker config**

Sjekk om `pyproject.toml` eller `setup.cfg` allerede har slow-marker. Hvis ikke, legg til i `pyproject.toml`:

```toml
[tool.pytest.ini_options]
markers = [
    "slow: tregere integrasjonstester (kjør med -m slow)",
]
```

- [ ] **Step 2: Write end-to-end test**

```python
import pytest

@pytest.mark.slow
def test_12200_full_run_with_ifc_cl(tmp_path):
    """Full pipeline mot 12200-modellen med IFC-CL — verifiser at output ser fornuftig ut."""
    from src.ifc_processor.pipeline import run_pipeline
    import json

    samples = Path(__file__).parent.parent / "samples"
    out = tmp_path / "out"

    result = run_pipeline(
        ifc_path=samples / "m_f_veg_12200_Veg.ifc",
        centerline_path=samples / "m_f-veg_12200_CL.ifc",
        output_dir=out,
        interval_m=20.0,
        include_terrain=False,            # rask: ingen Kartverket-kall
        include_tverrprofil=True,
        include_lengdeprofil=True,
    )

    # Sanity checks
    assert (out / "centerline.geojson").exists()
    assert (out / "stations.json").exists()
    assert (out / "metadata.json").exists()
    assert (out / "horizontal_alignment.json").exists()
    assert (out / "station_labels.json").exists()
    assert (out / "lengdeprofil.svg").exists()

    stations = json.loads((out / "stations.json").read_text())
    assert len(stations) > 50, "12200 er ~2 km — forventer minst 50 stasjoner ved 20 m"

    labels = json.loads((out / "station_labels.json").read_text())
    assert len(labels) > 50

    horiz = json.loads((out / "horizontal_alignment.json").read_text())
    assert len(horiz) == 67

    # Minst én tverrprofil-SVG produsert
    assert any(s.get("svg") for s in result.get("svgs", []) if result.get("svgs"))
```

- [ ] **Step 3: Run integration test**

Run: `python -m pytest tests/test_pipeline.py -v -m slow`
Expected: PASS (kan ta 30-60 sek)

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: PASS for alle (slow-tester hopper over uten `-m slow`)

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline.py pyproject.toml
git commit -m "test(pipeline): end-to-end slow test for IFC-CL pipeline against 12200"
```

---

## Task 19: Manuell verifisering og polish

**Files:** ingen — verifisering

- [ ] **Step 1: Start full stack**

I to terminaler:
```bash
# Terminal 1 — backend
uvicorn src.api.server:app --reload --port 8000

# Terminal 2 — frontend
cd web && npm run dev
```

- [ ] **Step 2: Logg inn via OAuth**

Naviger til frontend, logg inn med AGOL-konto.

- [ ] **Step 3: Kjør jobb med 12200-paret**

1. Last opp `samples/m_f_veg_12200_Veg.ifc` som BIM-modell
2. Last opp `samples/m_f-veg_12200_CL.ifc` som senterlinje
3. Sett intervall=20m, profil=alle
4. Start jobb

- [ ] **Step 4: Verifiser i profilutforskeren**

- Senterlinje følger IFC-vegmodellen pent
- Stasjoneringsnumre er "rene" (P 100, P 200 …) der referenter finnes
- Lengdeprofil-rubrikken viser klotoide-overganger
- Tverrprofiler genereres ved vegens stasjoner

- [ ] **Step 5: Verifiser AGOL-publisering**

Åpne hostet feature service i ArcGIS-kart. Verifiser at popup viser:
- `alignment_name = "12150"`
- `n_hor_seg = 67`
- `n_vert_seg = 50`
- `n_referents = 99`

- [ ] **Step 6: Regresjon — test med eksisterende FV229 LandXML**

Kjør samme flyt med:
- BIM: `samples/UEH-32-A-55075_05 Vei Kleverud_IFC.ifc` (eller annen vegmodell)
- Senterlinje: `samples/FV229_Senterlinje.xml`

Verifiser at LandXML-flyten fortsatt virker.

- [ ] **Step 7: Update memory**

Hvis alt fungerer, legg til en memory om at IFC-CL-støtte er ferdig (analogt med eksisterende `project_landxml_agol_complete.md`).

---

## Spec-coverage self-review

Etter at planen er skrevet, sjekk hver del av spec'en:

| Spec-seksjon | Dekket av task |
|---|---|
| `alignment_parser.py` schema check | Task 2 |
| Horisontalsegmenter | Task 3 |
| Vertikalsegmenter | Task 4 |
| 3D-sampling | Task 5 |
| IfcReferent-ekstraksjon | Task 6 |
| `to_centerline` / `vertical_profile_pvi` | Task 7 |
| `centerline.py` `.ifc`-gren | Task 8 |
| `AlignmentMetadata` | Task 9 |
| Stasjons-grid til referent | Task 10 |
| `referent_name` i station_rows | Task 11 |
| `station_labels.json` output | Task 11 |
| `horizontal_alignment.json` fra IFC | Task 12 |
| Felles `_polyline_publisher` | Task 13 |
| Ny `ifc_cl_to_agol` CLI | Task 14 |
| Ekstra felter (alignment_name, n_hor_seg etc.) | Task 14 |
| `cl_file` API-rename | Task 15 |
| `job_runner` routing | Task 15 |
| Nytt `/station-labels`-endepunkt | Task 16 |
| Wizard `.xml`/`.ifc` | Task 17 |
| Integrasjonstest 12200 | Task 18 |
| Manuell verifisering | Task 19 |
| Bakoverkompatibilitet (LandXML fortsatt virker) | Task 19 step 6 |

Ingen åpne gaps.
