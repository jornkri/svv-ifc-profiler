# src/ifc_processor/finished_ground.py
"""Ferdig-grunn-DEM fra BIM-veg-TIN-er (ren Python, ingen ArcPy).

Rasteriserer veg-TIN-trekanter til et regulært høydegrid via en mesh-z-buffer
(topp-z per celle). Brukes som ekstra elevasjonslag oppå GeocacheTerreng i
Profilutforsker-3D, så vegmodellen hviler riktig (cut/fill).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

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
