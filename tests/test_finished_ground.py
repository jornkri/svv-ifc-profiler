# tests/test_finished_ground.py
import json
from dataclasses import dataclass

import numpy as np

from src.ifc_processor.finished_ground import (
    NODATA,
    build_finished_ground_dem,
    rasterize_tins,
    write_dem,
)


def _flat_triangle(z, x0, y0, size):
    """Én stor flat trekant i z-planet som dekker [x0,x0+size]x[y0,y0+size]-ish."""
    # To trekanter dekker et kvadrat; her bruker vi én rettvinklet trekant.
    return np.array([[[x0, y0, z], [x0 + size, y0, z], [x0, y0 + size, z]]])


def test_rasterize_single_triangle_fills_covered_cells():
    tris = _flat_triangle(z=5.0, x0=0.0, y0=0.0, size=4.0)
    grid, header = rasterize_tins([tris], xmin=0.0, ymin=0.0, xmax=4.0, ymax=4.0, cell_m=1.0)
    assert header["ncols"] == 4 and header["nrows"] == 4
    # Nedre-venstre celle (rad 3, kol 0) senter (0.5,0.5): innenfor → 5.0
    assert grid[3, 0] == 5.0
    # Øvre-høyre celle (rad 0, kol 3) senter (3.5,3.5): utenfor rettvinklet trekant → NoData
    assert grid[0, 3] == NODATA


def test_rasterize_keeps_topmost_z_on_overlap():
    low = _flat_triangle(z=2.0, x0=0.0, y0=0.0, size=4.0)
    high = _flat_triangle(z=9.0, x0=0.0, y0=0.0, size=4.0)
    grid, _ = rasterize_tins([low, high], xmin=0.0, ymin=0.0, xmax=4.0, ymax=4.0, cell_m=1.0)
    assert grid[3, 0] == 9.0  # høyeste vinner uansett rekkefølge


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
