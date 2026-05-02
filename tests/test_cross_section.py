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
