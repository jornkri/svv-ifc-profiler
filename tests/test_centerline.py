# tests/test_centerline.py
import json
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.centerline import Centerline, load_centerline, _stations_from_points

def _make_geojson(tmp_path: Path, coords: list[list[float]]) -> Path:
    gj = tmp_path / "test_centerline.geojson"
    gj.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {}
        }]
    }))
    return gj

def test_stations_from_points_straight_line():
    pts = np.array([[0., 0., 0.], [10., 0., 0.], [20., 0., 0.]])
    stations = _stations_from_points(pts)
    assert stations[0] == pytest.approx(0.0)
    assert stations[1] == pytest.approx(10.0)
    assert stations[2] == pytest.approx(20.0)

def test_load_centerline_from_geojson(tmp_path):
    coords = [[0.0, 0.0, 0.0], [10.0, 0.0, 1.0], [20.0, 0.0, 2.0]]
    gj = _make_geojson(tmp_path, coords)
    cl = load_centerline(source=gj, ifc_path=Path("nonexistent.ifc"))
    assert isinstance(cl, Centerline)
    assert cl.points.shape == (3, 3)
    assert cl.stations[-1] == pytest.approx(np.sqrt(100 + 1) + np.sqrt(100 + 1), rel=1e-3)

def test_load_centerline_no_source_no_ifc():
    with pytest.raises(ValueError, match="Ingen senterlinje"):
        load_centerline(source=None, ifc_path=Path("nonexistent.ifc"))

def test_centerline_total_length():
    pts = np.array([[0., 0., 0.], [3., 4., 0.]])  # lengde = 5
    stations = _stations_from_points(pts)
    cl = Centerline(points=pts, stations=stations)
    assert cl.total_length == pytest.approx(5.0)


def test_load_centerline_from_ifc_alignment():
    from src.ifc_processor.centerline import load_centerline, Centerline
    cl_ifc = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"
    cl = load_centerline(source=cl_ifc, ifc_path=Path("nonexistent.ifc"))
    assert isinstance(cl, Centerline)
    assert cl.points.shape[0] >= 100
    assert cl.points.shape[1] == 3
    assert cl.total_length > 100  # 12200-modellen er > 2 km
