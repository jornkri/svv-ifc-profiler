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
    _project_to_2d,
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
        label="Planum",
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


def test_project_to_2d_horizontal_road():
    """For a road running along +X: right (−Y) is positive u, up is positive v."""
    tangent = np.array([1.0, 0.0, 0.0])
    plane_point = np.array([50.0, 0.0, 100.0])
    # Point 3m to the right (−Y direction for +X travel)
    p_right = np.array([50.0, -3.0, 100.0])
    u, v = _project_to_2d(p_right, plane_point, tangent)
    assert u == pytest.approx(3.0, abs=1e-6)
    assert v == pytest.approx(0.0, abs=1e-6)


def test_project_to_2d_graded_road():
    """On a graded road, the horizontal offset should not pick up elevation error."""
    # 10% grade: tangent has z component
    tangent = np.array([1.0, 0.0, 0.1])
    tangent /= np.linalg.norm(tangent)
    plane_point = np.array([50.0, 0.0, 100.0])
    # Point 3m to the right (−Y) at same elevation
    p_right = np.array([50.0, -3.0, 100.0])
    u, v = _project_to_2d(p_right, plane_point, tangent)
    # u should still be ~3.0 regardless of grade
    assert u == pytest.approx(3.0, abs=0.01)
    assert v == pytest.approx(0.0, abs=0.01)


# ---------------------------------------------------------------------------
# _chain_segments — toleransebasert kjeding
# ---------------------------------------------------------------------------

from src.ifc_processor.cross_section import _chain_segments


def test_chain_segments_joins_within_tolerance():
    """15 mm gap mellom segmenter skal kjedes (reelle IFC-gap er 9–340 mm)."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.015, 0.0), (2.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 1
    assert len(chains[0]) >= 3


def test_chain_segments_keeps_large_gap_separate():
    """100 mm gap er over default-toleransen (20 mm) — to kjeder."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.1, 0.0), (2.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 2


def test_chain_segments_exact_touch_still_works():
    """Eksakt like endepunkter (gammel oppførsel) skal fortsatt kjedes."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.0, 0.0), (2.0, 0.5)),
        ((2.0, 0.5), (3.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 1
    assert len(chains[0]) == 4


# ---------------------------------------------------------------------------
# stitch_cross_section_gaps — kjede-endepunkter + gjensidig nærmeste bro
# ---------------------------------------------------------------------------

from src.ifc_processor.cross_section import CrossSection, stitch_cross_section_gaps


def _cs(segments: dict) -> CrossSection:
    return CrossSection(station=0.0, elevation=100.0, segments=segments)


def test_stitch_bridges_same_class_gap():
    """200 mm gap innen samme klasse (skulder) skal broes — gammel kode nektet samme klasse."""
    cs = _cs({"skulder": [((0.0, 0.0), (1.0, 0.0)), ((1.2, 0.0), (2.2, 0.0))]})
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 3
    assert len(_chain_segments(out.segments["skulder"])) == 1


def test_stitch_bridge_lands_in_lower_priority_class():
    """Bro mellom skulder (prio 4) og groft (prio 3) skal ligge i groft."""
    cs = _cs({
        "skulder": [((0.0, 0.0), (1.0, 0.0))],
        "groft": [((1.1, -0.05), (2.0, -0.5))],
    })
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 1
    assert len(out.segments["groft"]) == 2


def test_stitch_never_bridges_terreng():
    """Terreng skal aldri broes — naturlige terrengbrudd forblir åpne."""
    cs = _cs({
        "terreng": [((0.0, 0.0), (1.0, 0.0))],
        "fylling": [((1.1, 0.0), (2.0, -0.5))],
    })
    out = stitch_cross_section_gaps(cs)
    total = sum(len(s) for s in out.segments.values())
    assert total == 2  # ingen bro lagt til


def test_stitch_ignores_gap_above_tolerance():
    """600 mm gap er over tol=0.40 — ingen bro."""
    cs = _cs({"skulder": [((0.0, 0.0), (1.0, 0.0)), ((1.6, 0.0), (2.6, 0.0))]})
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 2


def test_stitch_max_one_bridge_per_endpoint():
    """Tre kjedeender nær hverandre skal gi nøyaktig én bro (gjensidig nærmeste),
    ikke en stjerne av broer."""
    cs = _cs({"fylling": [
        ((0.0, 0.0), (1.0, 0.0)),       # ende A = (1.0, 0)
        ((1.10, 0.0), (2.0, 0.0)),      # ende B = (1.10, 0); d(A,B)=0.100
        ((1.18, 0.05), (1.5, 0.8)),     # ende C = (1.18, 0.05); d(B,C)=0.094, d(A,C)=0.187
    ]})
    out = stitch_cross_section_gaps(cs)
    total = sum(len(s) for s in out.segments.values())
    assert total == 4  # 3 originale + nøyaktig 1 bro (B<->C, gjensidig nærmeste)


def test_stitch_no_endpoint_starvation():
    """Når A-B broes skal ikke C-D-paret blokkeres selv om C sin globalt
    nærmeste ende (B) allerede er brukt — grådig matching etter avstand."""
    cs = _cs({"fylling": [
        ((0.0, 0.0), (1.0, 0.0)),        # ende A = (1.0, 0)
        ((1.1, 0.0), (1.3, 0.0)),        # ender B = (1.1, 0) og C = (1.3, 0)
        ((1.3, 0.35), (2.0, 1.0)),       # ende D = (1.3, 0.35)
    ]})
    out = stitch_cross_section_gaps(cs)
    total = sum(len(s) for s in out.segments.values())
    assert total == 5  # 3 originale + bro A-B + bro C-D
