# IFC-profiler backend — implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Python-pipeline som leser IFC 2X3-vegmodell med TIN-elementer, tar inn en senterlinje-GeoJSON, kutter tverrprofiler hvert 10 m og produserer R700-konforme SVG-filer.

**Architecture:** Fem moduler med klare grenser: `ifc_reader` (IFC → TINLayer-liste), `centerline` (hybrid senterlinje-provider), `cross_section` (stasjonssampling + snittplan-kuttning), `renderer` (R700 SVG), `pipeline` (orchestrering). All intern geometri i IFC lokalt koordinatsystem.

**Tech Stack:** Python 3.11, ifcopenshell, numpy, shapely, matplotlib (SVG-output), pytest

---

## Filstruktur

```
src/ifc_processor/
  ifc_reader.py        ← NY: parse IFC, klassifiser TINer etter Layer-property
  centerline.py        ← OMSKRIVES: hybrid GeoJSON / IfcAlignment / medialakse
  cross_section.py     ← OMSKRIVES: stasjonssampling + numpy plan-triangel-snitting
  renderer.py          ← OMSKRIVES: R700 SVG med matplotlib
  pipeline.py          ← NY: orkestrerer hele kjøringen
  longitudinal_profile.py  ← UENDRET (stub, utenfor scope)
  georef.py            ← NY stub (ikke i scope, men opprett tom modul)
  __init__.py          ← oppdater eksporter

tests/
  test_ifc_reader.py   ← NY
  test_centerline.py   ← NY
  test_cross_section.py ← NY
  test_renderer.py     ← NY
  test_pipeline.py     ← NY
  test_smoke.py        ← UENDRET (eksisterende smoke-tester)

output/                ← NY: gitignored, produsert av pipeline
```

---

## Felles datakontraktar (les dette før alle oppgaver)

```python
# TINLayer: ett klassifisert triangelnett fra IFC
@dataclass
class TINLayer:
    element_id: str
    name: str
    layer: str            # rå Layer-streng fra IFC-egenskapssett
    road_class: str       # "planum" | "skjaering" | "fylling" | "groft" | "unknown"
    triangles: np.ndarray  # shape (N, 3, 3): N triangler × 3 hjørnepunkter × XYZ

# Centerline: ordnede 3D-punkter med kumulativ stasjonering
@dataclass
class Centerline:
    points: np.ndarray    # shape (M, 3): X, Y, Z
    stations: np.ndarray  # shape (M,): kumulativ lengde i meter

# Station: ett punkt langs senterlinjen
@dataclass
class Station:
    distance: float        # meter fra start
    position: np.ndarray   # shape (3,): X, Y, Z
    tangent: np.ndarray    # shape (3,): normalisert retningsvektor

# CrossSection: resultat av ett tverrsnitt
@dataclass
class CrossSection:
    station: float         # stasjonering (m)
    elevation: float       # z-koordinat for senterlinjen ved denne stasjonen
    # road_class → liste av linjestykker [(u1,v1), (u2,v2)] i 2D snittplan
    # u = horisontal akse (venstre–høyre), v = vertikal akse (opp–ned)
    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]]
```

---

## Oppgave 1: IFC Reader

**Filer:**
- Opprett: `src/ifc_processor/ifc_reader.py`
- Opprett: `tests/test_ifc_reader.py`

- [ ] **Steg 1.1: Skriv den feilviklende testen**

```python
# tests/test_ifc_reader.py
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.ifc_reader import TINLayer, classify_layer, read_ifc_tins

SAMPLE_IFC = Path("samples/UEH-32-A-55075_05 Vei Kleverud_IFC.ifc")

def test_classify_layer_planum():
    assert classify_layer("3D_D_Planum_ColGreyS") == "planum"

def test_classify_layer_skjaering():
    assert classify_layer("3D_D_Skjæring_Grass01") == "skjaering"

def test_classify_layer_fylling():
    assert classify_layer("3D_D_Fylling_Grass01") == "fylling"

def test_classify_layer_groft():
    assert classify_layer("3D_D_Grøfteskråning_Grass01") == "groft"

def test_classify_layer_unknown():
    assert classify_layer("UkjentLag") == "unknown"

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_count():
    tins = read_ifc_tins(SAMPLE_IFC)
    assert len(tins) == 28

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_has_planum():
    tins = read_ifc_tins(SAMPLE_IFC)
    classes = {t.road_class for t in tins}
    assert "planum" in classes

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_triangles_shape():
    tins = read_ifc_tins(SAMPLE_IFC)
    for tin in tins:
        assert tin.triangles.ndim == 3
        assert tin.triangles.shape[1] == 3  # 3 hjørnepunkter
        assert tin.triangles.shape[2] == 3  # XYZ
```

- [ ] **Steg 1.2: Kjør test for å bekrefte at den feiler**

```bash
cd "/Users/Jorn.Kristiansen/SVV - Modellbasert prosjektstyring i planleggingsfasen/svv-ifc-profiler"
python -m pytest tests/test_ifc_reader.py -v
```
Forventet: `ModuleNotFoundError` eller `ImportError`

- [ ] **Steg 1.3: Implementer `ifc_reader.py`**

```python
# src/ifc_processor/ifc_reader.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np

logger = logging.getLogger(__name__)

_LAYER_KEYWORDS: dict[str, str] = {
    "planum": "planum",
    "skjæring": "skjaering",
    "skjaering": "skjaering",
    "fylling": "fylling",
    "grøfteskråning": "groft",
    "grofteskraning": "groft",
}


@dataclass
class TINLayer:
    element_id: str
    name: str
    layer: str
    road_class: str        # "planum" | "skjaering" | "fylling" | "groft" | "unknown"
    triangles: np.ndarray  # shape (N, 3, 3)


def classify_layer(layer_name: str) -> str:
    lower = layer_name.lower()
    for keyword, cls in _LAYER_KEYWORDS.items():
        if keyword in lower:
            return cls
    return "unknown"


def _get_property(element, pset_name: str, prop_name: str) -> str | None:
    for rel in getattr(element, "IsDefinedBy", []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not (hasattr(pset, "Name") and pset.Name == pset_name):
            continue
        for prop in getattr(pset, "HasProperties", []):
            if prop.Name == prop_name:
                val = getattr(prop, "NominalValue", None)
                return str(val.wrappedValue) if val else None
    return None


def read_ifc_tins(ifc_path: Path) -> list[TINLayer]:
    ifc = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    result: list[TINLayer] = []
    for element in ifc.by_type("IfcBuildingElementProxy"):
        layer = _get_property(element, "Attributter", "Layer") or ""
        if not layer:
            # Fall tilbake til navn-basert klassifisering
            layer = element.Name or ""
            logger.warning("Element %s mangler Layer-egenskap, bruker navn: %s", element.GlobalId, layer)

        road_class = classify_layer(layer)

        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
        except Exception as exc:
            logger.warning("Kan ikke hente geometri for %s: %s", element.GlobalId, exc)
            continue

        verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.array(shape.geometry.faces, dtype=int).reshape(-1, 3)
        triangles = verts[faces]  # shape (N, 3, 3)

        result.append(TINLayer(
            element_id=element.GlobalId,
            name=element.Name or "",
            layer=layer,
            road_class=road_class,
            triangles=triangles,
        ))

    return result
```

- [ ] **Steg 1.4: Kjør testene**

```bash
python -m pytest tests/test_ifc_reader.py -v
```
Forventet: Alle tester PASS. `test_read_ifc_tins_*` kan ta 10–30 sek (IFC-parsing).

- [ ] **Steg 1.5: Commit**

```bash
git add src/ifc_processor/ifc_reader.py tests/test_ifc_reader.py
git commit -m "feat: add IFC TIN reader with Layer-based classification"
```

---

## Oppgave 2: Centerline Provider

**Filer:**
- Omskriv: `src/ifc_processor/centerline.py`
- Opprett: `tests/test_centerline.py`

- [ ] **Steg 2.1: Skriv de feilviklende testene**

```python
# tests/test_centerline.py
import json
import tempfile
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.centerline import Centerline, load_centerline, _stations_from_points

def _make_geojson(coords: list[list[float]]) -> Path:
    tmp = tempfile.NamedTemporaryFile(suffix=".geojson", delete=False, mode="w")
    json.dump({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {}
        }]
    }, tmp)
    tmp.close()
    return Path(tmp.name)

def test_stations_from_points_straight_line():
    pts = np.array([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]])
    stations = _stations_from_points(pts)
    assert stations[0] == pytest.approx(0.0)
    assert stations[1] == pytest.approx(10.0)
    assert stations[2] == pytest.approx(20.0)

def test_load_centerline_from_geojson():
    coords = [[0.0, 0.0, 0.0], [10.0, 0.0, 1.0], [20.0, 0.0, 2.0]]
    gj = _make_geojson(coords)
    cl = load_centerline(source=gj, ifc_path=Path("nonexistent.ifc"))
    assert isinstance(cl, Centerline)
    assert cl.points.shape == (3, 3)
    assert cl.stations[-1] == pytest.approx(np.sqrt(100 + 1) + np.sqrt(100 + 1), rel=1e-3)
    gj.unlink()

def test_load_centerline_no_source_no_ifc():
    with pytest.raises(ValueError, match="Ingen senterlinje"):
        load_centerline(source=None, ifc_path=Path("nonexistent.ifc"))

def test_centerline_total_length():
    pts = np.array([[0., 0., 0.], [3., 4., 0.]])  # lengde = 5
    stations = _stations_from_points(pts)
    cl = Centerline(points=pts, stations=stations)
    assert cl.total_length == pytest.approx(5.0)
```

- [ ] **Steg 2.2: Kjør test for å bekrefte at den feiler**

```bash
python -m pytest tests/test_centerline.py -v
```
Forventet: `ImportError` (modul finnes men har feil API)

- [ ] **Steg 2.3: Omskriv `centerline.py`**

```python
# src/ifc_processor/centerline.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Centerline:
    points: np.ndarray    # shape (M, 3): X, Y, Z i IFC lokalt koordinatsystem
    stations: np.ndarray  # shape (M,): kumulativ lengde i meter

    @property
    def total_length(self) -> float:
        return float(self.stations[-1]) if len(self.stations) > 0 else 0.0


def _stations_from_points(points: np.ndarray) -> np.ndarray:
    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    return np.concatenate([[0.0], np.cumsum(seg_lengths)])


def _load_from_geojson(path: Path) -> Centerline:
    data = json.loads(path.read_text())
    features = data.get("features", [data] if data.get("type") == "Feature" else [])
    for feat in features:
        geom = feat.get("geometry", feat)
        if geom.get("type") == "LineString":
            coords = geom["coordinates"]
            pts = np.array([[c[0], c[1], c[2] if len(c) > 2 else 0.0] for c in coords])
            return Centerline(points=pts, stations=_stations_from_points(pts))
    raise ValueError(f"Ingen LineString funnet i {path}")


def _load_from_csv(path: Path) -> Centerline:
    pts = np.loadtxt(path, delimiter=",", usecols=(0, 1, 2))
    if pts.ndim == 1:
        pts = pts.reshape(1, 3)
    return Centerline(points=pts, stations=_stations_from_points(pts))


def _try_ifc_alignment(ifc_path: Path) -> Centerline | None:
    try:
        import ifcopenshell
        ifc = ifcopenshell.open(str(ifc_path))
        alignments = ifc.by_type("IfcAlignment")
        if not alignments:
            return None
        # IFC 4.3: hent punktrekke fra første alignment
        al = alignments[0]
        reps = getattr(al, "Representation", None)
        if reps is None:
            return None
        for rep in reps.Representations:
            for item in rep.Items:
                if item.is_a("IfcPolyline"):
                    pts = np.array([[p.Coordinates[0], p.Coordinates[1],
                                     p.Coordinates[2] if len(p.Coordinates) > 2 else 0.0]
                                    for p in item.Points])
                    return Centerline(points=pts, stations=_stations_from_points(pts))
    except Exception as exc:
        logger.warning("Kan ikke lese IfcAlignment: %s", exc)
    return None


def _medial_axis_from_tins(tins: list) -> Centerline:
    from shapely.ops import unary_union
    from shapely.geometry import MultiPolygon, Polygon

    all_pts = np.vstack([t.triangles.reshape(-1, 3)[:, :2] for t in tins])
    from shapely.geometry import MultiPoint
    footprint = MultiPoint(all_pts).convex_hull
    medial = footprint.boundary.interpolate(
        [i / 100 for i in range(101)], normalized=True
    )
    # Enkel tilnærming: bruk konturlinja i stedet for ekte medialakse
    coords = list(footprint.centroid.coords) * 2  # fallback
    logger.warning("Bruker forenklet medialakse-fallback — resultat kan være unøyaktig")
    pts = np.array([[c[0], c[1], 0.0] for c in list(footprint.exterior.coords)[::5]])
    return Centerline(points=pts, stations=_stations_from_points(pts))


def load_centerline(source: Path | None, ifc_path: Path) -> Centerline:
    """Last senterlinje.

    Prioritering:
    1. Eksplisitt kildefil (GeoJSON eller CSV)
    2. IfcAlignment i IFC 4.3-fil
    3. Medialakse fra Planum-TINer (upresist fallback)

    Raises:
        ValueError: hvis ingen senterlinje kan bestemmes
    """
    if source is not None:
        suffix = source.suffix.lower()
        if suffix in (".geojson", ".json"):
            return _load_from_geojson(source)
        if suffix == ".csv":
            return _load_from_csv(source)
        raise ValueError(f"Ukjent senterlinje-format: {suffix}. Godkjente formater: .geojson, .csv")

    if ifc_path.exists():
        cl = _try_ifc_alignment(ifc_path)
        if cl is not None:
            logger.info("Bruker IfcAlignment fra IFC-fil")
            return cl

        try:
            from .ifc_reader import read_ifc_tins
            tins = read_ifc_tins(ifc_path)
            planum = [t for t in tins if t.road_class == "planum"]
            if planum:
                logger.warning("Ingen eksplisitt senterlinje — faller tilbake til medialakse fra Planum")
                return _medial_axis_from_tins(planum)
        except Exception as exc:
            logger.warning("Medialakse-fallback feilet: %s", exc)

    raise ValueError(
        "Ingen senterlinje funnet. Oppgi senterlinje som:\n"
        "  --centerline senterlinje.geojson   (GeoJSON med LineString)\n"
        "  --centerline stasjoner.csv          (X,Y,Z per linje)"
    )
```

- [ ] **Steg 2.4: Oppdater `__init__.py`**

```python
# src/ifc_processor/__init__.py
"""IFC-prosessor: les IFC, ekstraher senterlinje, generer tverr- og lengdeprofiler."""

from .centerline import Centerline, load_centerline
from .cross_section import CrossSection, generate_cross_sections
from .ifc_reader import TINLayer, read_ifc_tins
from .longitudinal_profile import generate_longitudinal_profile

__all__ = [
    "Centerline",
    "load_centerline",
    "CrossSection",
    "generate_cross_sections",
    "TINLayer",
    "read_ifc_tins",
    "generate_longitudinal_profile",
]
```

- [ ] **Steg 2.5: Kjør testene**

```bash
python -m pytest tests/test_centerline.py -v
```
Forventet: Alle 4 tester PASS.

- [ ] **Steg 2.6: Commit**

```bash
git add src/ifc_processor/centerline.py src/ifc_processor/__init__.py tests/test_centerline.py
git commit -m "feat: rewrite centerline provider with hybrid GeoJSON/IfcAlignment/fallback"
```

---

## Oppgave 3: Stasjonssampling og tverrsnittskutting

**Filer:**
- Omskriv: `src/ifc_processor/cross_section.py`
- Opprett: `tests/test_cross_section.py`

- [ ] **Steg 3.1: Skriv de feilviklende testene**

```python
# tests/test_cross_section.py
import numpy as np
import pytest
from src.ifc_processor.centerline import Centerline, _stations_from_points
from src.ifc_processor.cross_section import (
    CrossSection,
    Station,
    sample_stations,
    cut_cross_section,
    _intersect_triangle_plane,
)
from src.ifc_processor.ifc_reader import TINLayer


def _straight_centerline(length=100.0, n=11) -> Centerline:
    pts = np.array([[x, 0.0, 0.0] for x in np.linspace(0, length, n)])
    return Centerline(points=pts, stations=_stations_from_points(pts))


def _flat_road_tin(y_min=-5.0, y_max=5.0, z=0.0) -> TINLayer:
    """Flat vegflate langs x-aksen, bredde 10 m."""
    triangles = np.array([
        [[0., y_min, z], [100., y_min, z], [100., y_max, z]],
        [[0., y_min, z], [100., y_max, z], [0., y_max, z]],
    ])
    return TINLayer(
        element_id="test-planum",
        name="Planum",
        layer="3D_D_Planum_Test",
        road_class="planum",
        triangles=triangles,
    )


def test_sample_stations_count():
    cl = _straight_centerline(100.0)
    stations = sample_stations(cl, interval_m=10.0)
    assert len(stations) == 11  # 0, 10, 20, ..., 100


def test_sample_stations_distances():
    cl = _straight_centerline(100.0)
    stations = sample_stations(cl, interval_m=10.0)
    for i, s in enumerate(stations):
        assert s.distance == pytest.approx(i * 10.0, abs=0.1)


def test_sample_stations_tangent_direction():
    cl = _straight_centerline(100.0)
    stations = sample_stations(cl, interval_m=10.0)
    for s in stations:
        # Tangent skal peke langs x-aksen
        assert s.tangent[0] == pytest.approx(1.0, abs=1e-6)
        assert s.tangent[1] == pytest.approx(0.0, abs=1e-6)


def test_intersect_triangle_plane_crossing():
    # Triangel krysser planet x=5
    tri = np.array([[0., 0., 0.], [10., 0., 0.], [5., 5., 0.]])
    plane_point = np.array([5., 0., 0.])
    plane_normal = np.array([1., 0., 0.])
    segs = _intersect_triangle_plane(tri, plane_point, plane_normal)
    assert len(segs) == 2


def test_intersect_triangle_plane_no_crossing():
    # Triangel helt på én side av planet
    tri = np.array([[0., 0., 0.], [1., 0., 0.], [0., 1., 0.]])
    plane_point = np.array([5., 0., 0.])
    plane_normal = np.array([1., 0., 0.])
    segs = _intersect_triangle_plane(tri, plane_point, plane_normal)
    assert len(segs) == 0


def test_cut_cross_section_returns_segments():
    cl = _straight_centerline(100.0)
    station = sample_stations(cl, interval_m=10.0)[5]  # x=50
    tin = _flat_road_tin()
    cs = cut_cross_section([tin], station)
    assert isinstance(cs, CrossSection)
    assert "planum" in cs.segments
    assert len(cs.segments["planum"]) > 0


def test_cut_cross_section_elevation():
    cl = _straight_centerline(100.0)
    station = sample_stations(cl, interval_m=10.0)[0]
    tin = _flat_road_tin(z=0.0)
    cs = cut_cross_section([tin], station)
    assert cs.elevation == pytest.approx(0.0, abs=0.1)
```

- [ ] **Steg 3.2: Kjør test for å bekrefte at den feiler**

```bash
python -m pytest tests/test_cross_section.py -v
```
Forventet: `ImportError` (mangler `Station`, `sample_stations`, `cut_cross_section`, `_intersect_triangle_plane`)

- [ ] **Steg 3.3: Omskriv `cross_section.py`**

```python
# src/ifc_processor/cross_section.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .centerline import Centerline
from .ifc_reader import TINLayer

logger = logging.getLogger(__name__)


@dataclass
class Station:
    distance: float       # meter fra start
    position: np.ndarray  # shape (3,): XYZ
    tangent: np.ndarray   # shape (3,): normalisert retningsvektor


@dataclass
class CrossSection:
    station: float
    elevation: float      # z-koordinat til senterlinjen
    # road_class → liste av linjestykker i 2D snittplan
    # hvert linjestykke: ((u1, v1), (u2, v2)) der u=horisontal, v=vertikal
    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = field(
        default_factory=dict
    )


def sample_stations(centerline: Centerline, interval_m: float = 10.0) -> list[Station]:
    pts = centerline.points
    sts = centerline.stations
    total = sts[-1]

    target_distances = np.arange(0.0, total + 1e-9, interval_m)
    stations: list[Station] = []

    for d in target_distances:
        idx = np.searchsorted(sts, d)
        idx = np.clip(idx, 1, len(sts) - 1)

        t = (d - sts[idx - 1]) / max(sts[idx] - sts[idx - 1], 1e-12)
        pos = pts[idx - 1] + t * (pts[idx] - pts[idx - 1])

        tang = pts[idx] - pts[idx - 1]
        norm = np.linalg.norm(tang)
        tang = tang / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])

        stations.append(Station(distance=float(d), position=pos, tangent=tang))

    return stations


def _intersect_triangle_plane(
    tri: np.ndarray,
    plane_point: np.ndarray,
    plane_normal: np.ndarray,
) -> list[np.ndarray]:
    """Returner 0 eller 2 skjæringspunkter der triangelet krysser planet."""
    d = (tri - plane_point) @ plane_normal  # signed distances, shape (3,)
    signs = np.sign(d)

    if np.all(signs >= 0) or np.all(signs <= 0):
        return []

    pts: list[np.ndarray] = []
    for i in range(3):
        j = (i + 1) % 3
        if signs[i] * signs[j] < 0:
            t = d[i] / (d[i] - d[j])
            pts.append(tri[i] + t * (tri[j] - tri[i]))

    return pts if len(pts) == 2 else []


def _project_to_2d(
    p: np.ndarray,
    plane_point: np.ndarray,
    tangent: np.ndarray,
) -> tuple[float, float]:
    """Projiser 3D-punkt til 2D i snittplanets koordinatsystem."""
    u = np.cross(tangent, np.array([0.0, 0.0, 1.0]))
    u_norm = np.linalg.norm(u)
    u = u / u_norm if u_norm > 1e-9 else np.array([0.0, 1.0, 0.0])
    v = np.array([0.0, 0.0, 1.0])
    delta = p - plane_point
    return float(delta @ u), float(delta @ v)


def cut_cross_section(tins: list[TINLayer], station: Station) -> CrossSection:
    """Snitt alle TINer med et plan vinkelrett på tangenten ved stasjonen."""
    plane_point = station.position
    plane_normal = station.tangent

    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}

    for tin in tins:
        cls = tin.road_class
        tin_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []

        for tri in tin.triangles:
            pts_3d = _intersect_triangle_plane(tri, plane_point, plane_normal)
            if len(pts_3d) == 2:
                uv1 = _project_to_2d(pts_3d[0], plane_point, plane_normal)
                uv2 = _project_to_2d(pts_3d[1], plane_point, plane_normal)
                tin_segs.append((uv1, uv2))

        if tin_segs:
            segments.setdefault(cls, []).extend(tin_segs)

    if not segments:
        logger.warning("Tomt snitt ved stasjon %.1f m — hopper over", station.distance)

    return CrossSection(
        station=station.distance,
        elevation=float(station.position[2]),
        segments=segments,
    )


def generate_cross_sections(
    ifc_path: Path,
    centerline: Centerline,
    interval_m: float = 10.0,
    width_m: float = 30.0,
) -> list[CrossSection]:
    from .ifc_reader import read_ifc_tins
    tins = read_ifc_tins(ifc_path)
    stations = sample_stations(centerline, interval_m)
    result = []
    for s in stations:
        cs = cut_cross_section(tins, s)
        result.append(cs)
    return result
```

- [ ] **Steg 3.4: Kjør testene**

```bash
python -m pytest tests/test_cross_section.py -v
```
Forventet: Alle 7 tester PASS.

- [ ] **Steg 3.5: Commit**

```bash
git add src/ifc_processor/cross_section.py tests/test_cross_section.py
git commit -m "feat: implement station sampling and numpy plane-triangle cross-section cutter"
```

---

## Oppgave 4: R700 SVG-renderer

**Filer:**
- Omskriv: `src/ifc_processor/renderer.py`
- Opprett: `tests/test_renderer.py`

- [ ] **Steg 4.1: Skriv de feilviklende testene**

```python
# tests/test_renderer.py
import tempfile
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.cross_section import CrossSection
from src.ifc_processor.renderer import render_cross_section_svg

def _simple_cross_section(station=50.0, elevation=100.0) -> CrossSection:
    return CrossSection(
        station=station,
        elevation=elevation,
        segments={
            "planum": [((-5.0, 0.0), (5.0, 0.0))],
            "skjaering": [((5.0, 0.0), (10.0, -3.0))],
            "unknown": [((-15.0, 0.0), (-5.0, 0.0))],
        }
    )

def test_render_produces_svg_file():
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "station_050.0.svg"
        render_cross_section_svg(cs, out)
        assert out.exists()
        assert out.stat().st_size > 0

def test_render_svg_contains_profile_number():
    cs = _simple_cross_section(station=1234.5)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert "1234" in content  # profilnummer

def test_render_svg_contains_elevation():
    cs = _simple_cross_section(elevation=98.75)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert "98" in content  # kotehøyde

def test_render_svg_is_valid_xml():
    import xml.etree.ElementTree as ET
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        ET.parse(str(out))  # kaster exception hvis ugyldig XML
```

Merk: Bruk `−` (minus-tegn) i testen eller bytt ut med `(-5.0, 0.0)` — standard ASCII minus.

- [ ] **Steg 4.2: Kjør test for å bekrefte at den feiler**

```bash
python -m pytest tests/test_renderer.py -v
```
Forventet: `ImportError` (mangler `render_cross_section_svg`)

- [ ] **Steg 4.3: Omskriv `renderer.py`**

```python
# src/ifc_processor/renderer.py
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile

logger = logging.getLogger(__name__)

# R700-linjestilar per vegkomponent
_STYLE: dict[str, dict] = {
    "planum":    {"color": "black", "linewidth": 2.0, "linestyle": "-", "zorder": 3},
    "skjaering": {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "fylling":   {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "groft":     {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "unknown":   {"color": "black", "linewidth": 0.5, "linestyle": "--", "zorder": 1},
}

_SCALE = 1 / 200  # 1:200 standard
_PAPER_W_MM = 420  # A3 bredde
_PAPER_H_MM = 297  # A3 høyde


def render_cross_section_svg(cross_section: CrossSection, output_path: Path) -> Path:
    """Render ett tverrprofil som R700-konform SVG.

    Args:
        cross_section: Tverrprofildata med segmenter per vegkomponent.
        output_path:   Destinasjon for SVG-filen.

    Returns:
        Path til produsert SVG-fil.
    """
    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    # --- Rutenett (graf-papir / "ruteark") ---
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#cccccc", linewidth=0.4, linestyle="-")
    ax.grid(which="minor", color="#eeeeee", linewidth=0.2, linestyle="-")
    ax.minorticks_on()

    # --- Samle alle koordinater for auto-skalering ---
    all_u: list[float] = []
    all_v: list[float] = []
    for segs in cross_section.segments.values():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])

    if not all_u:
        logger.warning("Ingen segmenter å rendre for stasjon %.1f", cross_section.station)
        plt.close(fig)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), format="svg")
        return output_path

    u_margin = max(5.0, (max(all_u) - min(all_u)) * 0.15)
    v_margin = max(3.0, (max(all_v) - min(all_v)) * 0.15)
    ax.set_xlim(min(all_u) - u_margin, max(all_u) + u_margin)
    ax.set_ylim(min(all_v) - v_margin, max(all_v) + v_margin)

    # --- Horisontal referanselinje med kotehøyde ---
    base_v = min(all_v) - v_margin * 0.4
    ref_elev = round(cross_section.elevation, 2)
    ax.axhline(y=0.0, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8, 0.0,
        f"{ref_elev:.2f}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    # --- Tegn segmenter ---
    for road_class, segs in cross_section.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for (u1, v1), (u2, v2) in segs:
            ax.plot([u1, u2], [v1, v2], **style)

    # --- Profilnummer over profilen ---
    ax.set_title(
        f"Profil {cross_section.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )

    # --- Akseetiketter ---
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel(f"Høyde over {ref_elev:.0f} m (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    # --- Tittelfelt (nede til høyre, R700 U-tegning) ---
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:200 · Stasjon {cross_section.station:.2f} m",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    plt.close(fig)
    return output_path


def render_cross_section_png(
    cross_section: CrossSection,
    output_path: Path,
    *,
    scale: float = 1.0 / 200.0,
    paper_size: tuple[float, float] = (420, 297),
) -> Path:
    """Render som PNG via SVG (stub — PNG-eksport er utenfor MVP-scope)."""
    raise NotImplementedError("PNG-eksport er utenfor MVP-scope. Bruk render_cross_section_svg.")


def render_longitudinal_profile_png(
    profile: LongitudinalProfile,
    output_path: Path,
) -> Path:
    raise NotImplementedError("Lengdeprofil er utenfor scope for MVP")
```

- [ ] **Steg 4.4: Kjør testene**

```bash
python -m pytest tests/test_renderer.py -v
```
Forventet: Alle 4 tester PASS.

- [ ] **Steg 4.5: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "feat: R700-compliant SVG cross-section renderer with grid and elevation label"
```

---

## Oppgave 5: Pipeline og georef-stub

**Filer:**
- Opprett: `src/ifc_processor/pipeline.py`
- Opprett: `src/ifc_processor/georef.py`
- Opprett: `tests/test_pipeline.py`
- Oppdater: `src/ifc_processor/__init__.py`

- [ ] **Steg 5.1: Skriv den feilviklende testen**

```python
# tests/test_pipeline.py
import json
import tempfile
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.pipeline import run_pipeline

SAMPLE_IFC = Path("samples/UEH-32-A-55075_05 Vei Kleverud_IFC.ifc")


def _write_test_centerline(tmp: Path) -> Path:
    """Skriv en enkel senterlinje-GeoJSON for testing."""
    cl_path = tmp / "centerline.geojson"
    cl_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0, 100.0], [50.0, 0.0, 100.5], [100.0, 0.0, 101.0]]
            },
            "properties": {}
        }]
    }))
    return cl_path


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_pipeline_produces_output_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cl_path = _write_test_centerline(tmp_path)
        out_dir = tmp_path / "output"

        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=cl_path,
            output_dir=out_dir,
            interval_m=50.0,
        )

        assert Path(result["centerline"]).exists()
        assert Path(result["metadata"]).exists()
        assert len(result["svgs"]) >= 1
        for svg in result["svgs"]:
            assert Path(svg).exists()


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_pipeline_metadata_has_stations():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cl_path = _write_test_centerline(tmp_path)
        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )
        meta = json.loads(Path(result["metadata"]).read_text())
        assert "stations" in meta
        assert len(meta["stations"]) >= 1


def test_pipeline_raises_without_centerline(tmp_path):
    fake_ifc = tmp_path / "empty.ifc"
    fake_ifc.write_text("")
    with pytest.raises(ValueError, match="Ingen senterlinje"):
        run_pipeline(ifc_path=fake_ifc, centerline_path=None, output_dir=tmp_path / "out")
```

- [ ] **Steg 5.2: Kjør test for å bekrefte at den feiler**

```bash
python -m pytest tests/test_pipeline.py -v
```
Forventet: `ImportError` (mangler `pipeline.py`)

- [ ] **Steg 5.3: Opprett `georef.py` (stub)**

```python
# src/ifc_processor/georef.py
"""Koordinattransform: IFC lokalt koordinatsystem → ETRS89/NTM.

Georeferering er et forhåndstrinn som kjøres separat (ArcPy på Windows).
Denne modulen er en stub for fremtidig integrasjon.
"""
from __future__ import annotations
from pathlib import Path


def read_prj(prj_path: Path) -> dict:
    """Les .prj-fil og returner koordinatreferansesystem-info."""
    return {"wkt": prj_path.read_text().strip()}
```

- [ ] **Steg 5.4: Implementer `pipeline.py`**

```python
# src/ifc_processor/pipeline.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from .centerline import load_centerline
from .cross_section import cut_cross_section, sample_stations
from .ifc_reader import read_ifc_tins
from .renderer import render_cross_section_svg

logger = logging.getLogger(__name__)


def _save_centerline_geojson(centerline, path: Path) -> None:
    coords = [[float(p[0]), float(p[1]), float(p[2])] for p in centerline.points]
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"note": "IFC lokalt koordinatsystem — ikke georeferert"}
        }]
    }, indent=2))


def run_pipeline(
    ifc_path: Path,
    centerline_path: Path | None = None,
    output_dir: Path = Path("output"),
    interval_m: float = 10.0,
) -> dict:
    """Kjør full pipeline: IFC → tverrprofil-SVGer + metadata.

    Args:
        ifc_path:        Sti til .ifc-fil.
        centerline_path: Sti til senterlinje (GeoJSON eller CSV). Hvis None,
                         forsøker IfcAlignment, deretter medialakse-fallback.
        output_dir:      Katalog for SVG-er og metadata.
        interval_m:      Stasjoneringsintervall i meter (default 10).

    Returns:
        Dict med nøklene "svgs", "centerline", "metadata".

    Raises:
        ValueError: Hvis ingen senterlinje kan bestemmes.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Leser TINer fra %s", ifc_path)
    tins = read_ifc_tins(ifc_path)
    logger.info("Leste %d TINer", len(tins))

    centerline = load_centerline(source=centerline_path, ifc_path=ifc_path)
    logger.info("Senterlinje: %.1f m lang, %d punkter", centerline.total_length, len(centerline.points))

    stations = sample_stations(centerline, interval_m)
    logger.info("Genererer %d tverrprofiler (intervall: %.1f m)", len(stations), interval_m)

    svg_paths: list[str] = []
    metadata_rows: list[dict] = []

    for s in stations:
        try:
            cs = cut_cross_section(tins, s)
        except Exception as exc:
            logger.warning("Hopper over stasjon %.1f m: %s", s.distance, exc)
            continue

        svg_path = output_dir / f"station_{s.distance:07.1f}.svg"
        render_cross_section_svg(cs, svg_path)
        svg_paths.append(str(svg_path))
        metadata_rows.append({
            "station": round(s.distance, 3),
            "elevation": round(cs.elevation, 3),
            "svg": str(svg_path),
            "segment_classes": list(cs.segments.keys()),
        })

    cl_path = output_dir / "centerline.geojson"
    _save_centerline_geojson(centerline, cl_path)

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps({"stations": metadata_rows}, indent=2))

    logger.info("Pipeline ferdig. %d SVGer → %s", len(svg_paths), output_dir)
    return {
        "svgs": svg_paths,
        "centerline": str(cl_path),
        "metadata": str(meta_path),
    }
```

- [ ] **Steg 5.5: Legg til `output/` i `.gitignore`**

Åpne `.gitignore` og legg til under `# Prosjekt-spesifikt`:
```
output/
```
(Merk: `output/` finnes allerede i `.gitignore` — verifiser med `grep "^output" .gitignore`)

- [ ] **Steg 5.6: Oppdater `__init__.py` med pipeline-eksport**

```python
# src/ifc_processor/__init__.py
"""IFC-prosessor: les IFC, ekstraher senterlinje, generer tverr- og lengdeprofiler."""

from .centerline import Centerline, load_centerline
from .cross_section import CrossSection, Station, generate_cross_sections, sample_stations
from .ifc_reader import TINLayer, read_ifc_tins
from .longitudinal_profile import generate_longitudinal_profile
from .pipeline import run_pipeline

__all__ = [
    "Centerline",
    "load_centerline",
    "CrossSection",
    "Station",
    "generate_cross_sections",
    "sample_stations",
    "TINLayer",
    "read_ifc_tins",
    "generate_longitudinal_profile",
    "run_pipeline",
]
```

- [ ] **Steg 5.7: Kjør alle tester**

```bash
python -m pytest tests/ -v
```
Forventet: Alle tester PASS. `test_pipeline_*`-testene mot IFC-fil kan ta 30–60 sek.

- [ ] **Steg 5.8: Commit**

```bash
git add src/ifc_processor/pipeline.py src/ifc_processor/georef.py \
        src/ifc_processor/__init__.py tests/test_pipeline.py
git commit -m "feat: add pipeline orchestrator, georef stub, and end-to-end tests"
```

---

## Oppgave 6: Røyktester og manuell verifisering

**Filer:**
- Oppdater: `tests/test_smoke.py`

- [ ] **Steg 6.1: Oppdater smoke-test for ny API**

```python
# tests/test_smoke.py
"""Smoke-tester: sjekk at modulene kan importeres og at API-en svarer."""

from fastapi.testclient import TestClient


def test_imports():
    from src.ifc_processor import (
        Centerline,
        CrossSection,
        Station,
        TINLayer,
        generate_cross_sections,
        load_centerline,
        read_ifc_tins,
        run_pipeline,
        sample_stations,
    )
    assert callable(load_centerline)
    assert callable(read_ifc_tins)
    assert callable(run_pipeline)
    assert callable(sample_stations)


def test_health_endpoint():
    from src.api.server import app

    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
```

- [ ] **Steg 6.2: Kjør røyktestene**

```bash
python -m pytest tests/test_smoke.py -v
```
Forventet: Begge PASS.

- [ ] **Steg 6.3: Manuell ende-til-ende kjøring med testfil**

Lag en enkel senterlinje-GeoJSON for testmodellen (erstatt koordinatene med faktiske verdier fra IFC-modellen):

```bash
cat > /tmp/test_cl.geojson << 'EOF'
{
  "type": "FeatureCollection",
  "features": [{
    "type": "Feature",
    "geometry": {
      "type": "LineString",
      "coordinates": [[0.0, 0.0, 0.0], [50.0, 0.0, 0.5], [100.0, 0.0, 1.0]]
    },
    "properties": {}
  }]
}
EOF

python -c "
from pathlib import Path
from src.ifc_processor.pipeline import run_pipeline
import logging
logging.basicConfig(level=logging.INFO)

result = run_pipeline(
    ifc_path=Path('samples/UEH-32-A-55075_05 Vei Kleverud_IFC.ifc'),
    centerline_path=Path('/tmp/test_cl.geojson'),
    output_dir=Path('output/test'),
    interval_m=10.0,
)
print('SVGer:', result['svgs'][:3])
print('Metadata:', result['metadata'])
"
```
Forventet: Logger viser TIN-lesing, stasjonsgenerering, SVG-produksjon. Åpne en `.svg`-fil fra `output/test/` og verifiser at du ser rutenett, linjestykker og profilnummer.

- [ ] **Steg 6.4: Commit**

```bash
git add tests/test_smoke.py
git commit -m "test: update smoke tests for new ifc_processor public API"
```

---

## Sjekkliste: spec-dekning

| Spec-krav | Oppgave |
|---|---|
| Les IFC, klassifiser TINer etter Layer | Oppgave 1 |
| Hybrid senterlinje GeoJSON/IfcAlignment/fallback | Oppgave 2 |
| Tverrsnitt hvert 10 m | Oppgave 3 |
| R700-konform SVG (rutenett, kotehøyde, profilnummer) | Oppgave 4 |
| centerline.geojson + metadata.json output | Oppgave 5 |
| Feil: ingen senterlinje → ValueError | Oppgave 2 + 5 |
| Feil: tomt snitt → advarsel, hopp over | Oppgave 3 |
| Feil: mangler Layer-property → navn-fallback | Oppgave 1 |
| Georef-stub (ikke i MVP-pipeline) | Oppgave 5 |
