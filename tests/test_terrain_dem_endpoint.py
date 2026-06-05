# tests/test_terrain_dem_endpoint.py
import json
import shutil
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


def test_terrain_dem_json_and_bin_served():
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
        shutil.rmtree(out.parent)


def test_terrain_dem_404_when_missing():
    r = client.get("/api/jobs/nonexistent-job/terrain-dem")
    assert r.status_code == 404
    assert client.get("/api/jobs/nonexistent-job/terrain-dem.bin").status_code == 404
