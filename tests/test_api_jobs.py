# tests/test_api_jobs.py
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


def test_create_job_returns_id():
    from src.api.job_runner import create_job, get_job
    job_id = create_job()
    assert job_id is not None
    state = get_job(job_id)
    assert state is not None
    assert state.status == "queued"


def test_get_job_unknown_returns_none():
    from src.api.job_runner import get_job
    assert get_job("does-not-exist-xyz") is None


def test_run_job_success(tmp_path):
    """run_job sets status=done after successful pipeline + subprocesses."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"
    fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"
    fake_xml.write_text("")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    meta = {"stations": [{"station": 0.0}, {"station": 10.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [str(output_dir / "station_0000000.0.svg")],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl/FeatureServer"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp/FeatureServer"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp]):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestJob",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
        )

    state = get_job(job_id)
    assert state.status == "done"
    assert state.progress_pct == 100
    assert state.centerline_url == "https://agol/cl/FeatureServer"
    assert state.sections_url == "https://agol/tp/FeatureServer"


def test_run_job_sets_failed_on_subprocess_error(tmp_path):
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"
    fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"
    fake_xml.write_text("")
    output_dir = tmp_path / "output"
    output_dir.mkdir()

    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=subprocess.CalledProcessError(1, "cmd", stderr="AGOL feilet")):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            xml_path=fake_xml,
            name="TestFail",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
        )

    state = get_job(job_id)
    assert state.status == "failed"
    assert "AGOL feilet" in state.error


import io
import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def set_env_for_server(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-key")
    monkeypatch.setenv("AGOL_CLIENT_ID", "test_client")
    monkeypatch.setenv("AGOL_ORG_URL", "https://test.maps.arcgis.com")


@pytest.fixture
def client():
    from src.api.server import app
    return TestClient(app)


def _login(client):
    """Simulate OAuth2 login via mocked AGOL callbacks."""
    login_resp = client.get("/auth/login", follow_redirects=False)
    params = dict(p.split("=", 1) for p in
                  login_resp.headers["location"].split("?")[1].split("&"))
    state = params["state"]
    token_mock = MagicMock(raise_for_status=MagicMock(),
                           json=MagicMock(return_value={"access_token": "tok", "refresh_token": "r"}))
    user_mock = MagicMock(raise_for_status=MagicMock(),
                          json=MagicMock(return_value={"username": "u", "fullName": "N"}))
    with patch("src.api.auth_routes.httpx.post", return_value=token_mock), \
         patch("src.api.auth_routes.httpx.get", return_value=user_mock):
        client.get(f"/auth/callback?code=x&state={state}", follow_redirects=False)


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_post_jobs_requires_auth(client):
    resp = client.post(
        "/api/jobs",
        data={"name": "Test", "interval": "10"},
        files={"ifc_file": ("m.ifc", io.BytesIO(b"fake")),
               "xml_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 401


def test_post_jobs_validates_file_type(client):
    _login(client)
    resp = client.post(
        "/api/jobs",
        data={"name": "Test", "interval": "10"},
        files={"ifc_file": ("model.txt", io.BytesIO(b"bad")),
               "xml_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 400


def test_post_jobs_creates_job_and_returns_id(client):
    _login(client)
    with patch("src.api.job_runner.run_job"):  # prevent actual execution
        resp = client.post(
            "/api/jobs",
            data={"name": "TestService", "interval": "10"},
            files={"ifc_file": ("model.ifc", io.BytesIO(b"fake")),
                   "xml_file": ("cl.xml", io.BytesIO(b"<xml/>"))},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert data["status"] == "queued"


def test_get_job_status_queued(client):
    _login(client)
    with patch("src.api.job_runner.run_job"):
        create_resp = client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "xml_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    job_id = create_resp.json()["job_id"]

    status_resp = client.get(f"/api/jobs/{job_id}")
    assert status_resp.status_code == 200
    data = status_resp.json()
    assert "status" in data
    assert "progress_pct" in data
    assert "message" in data
    assert "centerline_url" in data
    assert "sections_url" in data
    assert "error" in data


def test_get_job_404_for_unknown(client):
    assert client.get("/api/jobs/does-not-exist").status_code == 404
