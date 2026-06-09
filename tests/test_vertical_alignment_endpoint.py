# tests/test_vertical_alignment_endpoint.py
import json
import shutil

from fastapi.testclient import TestClient

from src.api.server import app, UPLOAD_DIR

client = TestClient(app)


def test_vertical_alignment_served_when_present():
    """Endpoint returnerer innholdet i vertical_alignment.json når filen finnes."""
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
        shutil.rmtree(UPLOAD_DIR / "testjob-vert", ignore_errors=True)


def test_vertical_alignment_empty_when_missing():
    """Endpoint returnerer [] (ikke 404) når filen mangler."""
    r = client.get("/api/jobs/no-such-job-vert-xyz/vertical-alignment")
    assert r.status_code == 200
    assert r.json() == []
