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
               side_effect=[mock_proc_cl, mock_proc_tp]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            cl_path=fake_xml,
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


def test_run_job_passes_source_epsg_to_tverrprofil(tmp_path):
    """run_job skal sende --source-epsg til tverrprofil_to_agol basert på LandXML."""
    from src.api.job_runner import create_job, run_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [], "centerline": str(output_dir / "c.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp"})
    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp]) as mock_run, \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 5111)):
        run_job(job_id=job_id, ifc_path=fake_ifc, cl_path=fake_xml,
                name="T", interval=10.0, access_token="tok",
                org_url="https://x.arcgis.com", output_dir=output_dir)

    tp_call_args = mock_run.call_args_list[1][0][0]
    assert "--source-epsg" in tp_call_args
    assert "5111" in tp_call_args


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
               side_effect=subprocess.CalledProcessError(1, "cmd", stderr="AGOL feilet")), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            cl_path=fake_xml,
            name="TestFail",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
        )

    state = get_job(job_id)
    assert state.status == "failed"
    assert "AGOL feilet" in state.error


def test_run_job_with_publish_bim_success(tmp_path):
    """publish_bim=True kjører tre subprocesser og setter bim_url."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{"station": 0.0}, {"station": 10.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl/FeatureServer"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp/FeatureServer"})
    bim_stdout = json.dumps({"status": "ok", "url": "https://agol/bim/FeatureServer"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)
    mock_proc_bim = MagicMock(stdout=bim_stdout, returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp, mock_proc_bim]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            cl_path=fake_xml,
            name="TestBIM",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
            publish_bim=True,
        )

    state = get_job(job_id)
    assert state.status == "done"
    assert state.bim_url == "https://agol/bim/FeatureServer"
    assert state.centerline_url == "https://agol/cl/FeatureServer"
    assert state.sections_url == "https://agol/tp/FeatureServer"


def test_run_job_with_publish_bim_bim_fails_gives_done_with_warnings(tmp_path):
    """Når BIM-subprocess feiler settes done_with_warnings; senterlinje og tverrprofiler er ok."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp"})

    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)
    bim_error = subprocess.CalledProcessError(1, "cmd", stderr="BIM-konvertering feilet")

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp, bim_error]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            cl_path=fake_xml,
            name="TestBIMFail",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
            publish_bim=True,
        )

    state = get_job(job_id)
    assert state.status == "done_with_warnings"
    assert state.bim_url is None
    assert state.centerline_url == "https://agol/cl"
    assert state.sections_url == "https://agol/tp"
    assert "BIM-konvertering feilet" in state.error


def test_run_job_with_publish_bim_bad_json_gives_done_with_warnings(tmp_path):
    """BIM subprocess exits 0 but stdout is not valid JSON → done_with_warnings."""
    from src.api.job_runner import create_job, run_job, get_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_xml = tmp_path / "cl.xml"; fake_xml.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(json.dumps(meta))

    pipeline_result = {
        "svgs": [],
        "centerline": str(output_dir / "centerline.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }

    cl_stdout = json.dumps({"status": "ok", "url": "https://agol/cl"})
    tp_stdout = json.dumps({"status": "ok", "url": "https://agol/tp"})
    mock_proc_cl = MagicMock(stdout=cl_stdout, returncode=0)
    mock_proc_tp = MagicMock(stdout=tp_stdout, returncode=0)
    mock_proc_bim = MagicMock(stdout="not valid json", returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp, mock_proc_bim]), \
         patch("src.api.job_runner.parse_landxml", return_value=({}, 25833)):
        run_job(
            job_id=job_id,
            ifc_path=fake_ifc,
            cl_path=fake_xml,
            name="TestBIMBadJson",
            interval=10.0,
            access_token="tok",
            org_url="https://test.arcgis.com",
            output_dir=output_dir,
            publish_bim=True,
        )

    state = get_job(job_id)
    assert state.status == "done_with_warnings"
    assert state.bim_url is None
    assert state.centerline_url == "https://agol/cl"
    assert state.sections_url == "https://agol/tp"


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
    monkeypatch.setattr("src.api.server.refresh_access_token",
                        lambda session: session.get("access_token", "tok"))


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
               "cl_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 401


def test_post_jobs_validates_file_type(client):
    _login(client)
    resp = client.post(
        "/api/jobs",
        data={"name": "Test", "interval": "10"},
        files={"ifc_file": ("model.txt", io.BytesIO(b"bad")),
               "cl_file": ("cl.xml", io.BytesIO(b"<x/>"))},
    )
    assert resp.status_code == 400


def test_post_jobs_creates_job_and_returns_id(client):
    _login(client)
    with patch("src.api.job_runner.run_job"):  # prevent actual execution
        resp = client.post(
            "/api/jobs",
            data={"name": "TestService", "interval": "10"},
            files={"ifc_file": ("model.ifc", io.BytesIO(b"fake")),
                   "cl_file": ("cl.xml", io.BytesIO(b"<xml/>"))},
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
                   "cl_file": ("c.xml", io.BytesIO(b"<x/>"))},
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


def test_post_jobs_passes_publish_bim_true_to_run_job(client):
    """publish_bim=true i skjemaet skal sendes videre til run_job."""
    _login(client)
    with patch("src.api.job_runner.run_job") as mock_run_job:
        client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10", "publish_bim": "true"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "cl_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    mock_run_job.assert_called_once()
    _, kwargs = mock_run_job.call_args
    assert kwargs.get("publish_bim") is True


def test_get_job_status_includes_bim_url(client):
    """GET /api/jobs/{id} skal inneholde bim_url-feltet."""
    _login(client)
    with patch("src.api.job_runner.run_job"):
        create_resp = client.post(
            "/api/jobs",
            data={"name": "S", "interval": "10"},
            files={"ifc_file": ("m.ifc", io.BytesIO(b"x")),
                   "cl_file": ("c.xml", io.BytesIO(b"<x/>"))},
        )
    job_id = create_resp.json()["job_id"]
    status_resp = client.get(f"/api/jobs/{job_id}")
    assert "bim_url" in status_resp.json()


def test_job_state_has_xb_url_field():
    from src.api.job_runner import JobState
    state = JobState(job_id="test-123")
    assert state.xb_url is None


def test_persist_state_includes_xb_url(tmp_path):
    from src.api.job_runner import JobState, _persist_state
    state = JobState(job_id="test-456", output_dir=tmp_path)
    state.xb_url = "https://experience.arcgis.com/builder/?id=abc"
    _persist_state(state)
    data = json.loads((tmp_path / "job_state.json").read_text())
    assert data["xb_url"] == "https://experience.arcgis.com/builder/?id=abc"


def test_run_job_skips_xb_when_template_missing(tmp_path):
    """XB creation is silently skipped if the template file does not exist."""
    mock_cl_result = {
        "url": "https://services/CL/FeatureServer",
        "item_id": "cl_id",
        "utm33_centerline_paths": [],
    }
    mock_tp_result = {
        "url": "https://services/TP/FeatureServer",
        "item_id": "tp_id",
        "utm33_stations": [],
    }

    mock_pipeline_result = {
        "metadata": str(tmp_path / "meta.json"),
        "stations_json": str(tmp_path / "stations.json"),
    }
    (tmp_path / "meta.json").write_text(json.dumps({"stations": [{"station": 0.0}]}))
    (tmp_path / "stations.json").write_text(json.dumps([]))

    with patch("src.api.job_runner.run_pipeline", return_value=mock_pipeline_result), \
         patch("src.api.job_runner.parse_landxml", return_value=(MagicMock(), 25833)), \
         patch("src.api.job_runner.subprocess.run") as mock_sub:

        mock_sub.side_effect = [
            MagicMock(stdout=json.dumps(mock_cl_result), stderr=""),
            MagicMock(stdout=json.dumps(mock_tp_result), stderr=""),
        ]

        from src.api import job_runner
        job_id = job_runner.create_job()
        job_runner._jobs[job_id].output_dir = tmp_path / "output"

        job_runner.run_job(
            job_id=job_id,
            ifc_path=tmp_path / "model.ifc",
            cl_path=tmp_path / "cl.xml",
            name="TestProject",
            interval=10.0,
            access_token="tok",
            org_url="https://www.arcgis.com",
            output_dir=tmp_path / "output",
        )

    state = job_runner.get_job(job_id)
    assert state.xb_url is None   # template missing → skipped
    assert state.status in ("done", "done_with_warnings")


def test_get_job_response_includes_xb_url():
    from fastapi.testclient import TestClient
    from src.api.server import app
    from src.api import job_runner

    job_id = job_runner.create_job()
    state = job_runner._jobs[job_id]
    state.status = "done"
    state.xb_url = "https://experience.arcgis.com/builder/?id=xyz"

    client = TestClient(app)
    resp = client.get(f"/api/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["xb_url"] == "https://experience.arcgis.com/builder/?id=xyz"


def test_get_station_labels_returns_empty_for_landxml_job(client, tmp_path, monkeypatch):
    """LandXML-jobb uten station_labels.json skal gi tom liste (ikke 404)."""
    monkeypatch.setattr("src.api.server.UPLOAD_DIR", tmp_path)
    job_dir = tmp_path / "fake-job-id"
    (job_dir / "output").mkdir(parents=True)
    (job_dir / "output" / "metadata.json").write_text('{"stations":[]}')

    response = client.get("/api/jobs/fake-job-id/station-labels")
    assert response.status_code == 200
    assert response.json() == []


def test_get_station_labels_returns_data_when_present(client, tmp_path, monkeypatch):
    """station-labels skal returnere innholdet i station_labels.json."""
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


def test_create_job_accepts_ifc_cl(client):
    """POST /api/jobs godtar cl_file med .ifc-ending og ruter med .ifc-sti."""
    _login(client)
    with patch("src.api.job_runner.run_job") as mock_run_job:
        resp = client.post(
            "/api/jobs",
            data={"name": "test_job", "interval": "20.0"},
            files={"ifc_file": ("model.ifc", io.BytesIO(b"fake")),
                   "cl_file": ("centerline.ifc", io.BytesIO(b"fake"))},
        )
    assert resp.status_code == 200
    assert "job_id" in resp.json()
    _, kwargs = mock_run_job.call_args
    assert kwargs["cl_path"].suffix.lower() == ".ifc"


def test_create_job_rejects_unknown_cl_ending(client):
    """cl_file med ukjent ending (.txt) skal gi 400."""
    _login(client)
    resp = client.post(
        "/api/jobs",
        data={"name": "test_job", "interval": "20.0"},
        files={"ifc_file": ("model.ifc", io.BytesIO(b"fake")),
               "cl_file": ("centerline.txt", io.BytesIO(b"bad"))},
    )
    assert resp.status_code == 400
    assert "cl_file" in resp.json()["detail"].lower() or \
           ".xml" in resp.json()["detail"].lower()


def test_run_job_routes_ifc_cl_to_ifc_publisher(tmp_path):
    """Når cl_path er .ifc skal senterlinje-publiseringen rute til ifc_cl_to_agol."""
    from src.api.job_runner import create_job, run_job

    fake_ifc = tmp_path / "model.ifc"; fake_ifc.write_text("")
    fake_cl = tmp_path / "centerline.ifc"; fake_cl.write_text("")
    output_dir = tmp_path / "output"; output_dir.mkdir()
    (output_dir / "metadata.json").write_text(json.dumps({"stations": [{}]}))

    pipeline_result = {
        "svgs": [], "centerline": str(output_dir / "c.geojson"),
        "metadata": str(output_dir / "metadata.json"),
        "stations_json": str(output_dir / "stations.json"),
    }
    mock_proc_cl = MagicMock(stdout=json.dumps({"status": "ok", "url": "https://agol/cl"}), returncode=0)
    mock_proc_tp = MagicMock(stdout=json.dumps({"status": "ok", "url": "https://agol/tp"}), returncode=0)

    job_id = create_job()
    with patch("src.api.job_runner.run_pipeline", return_value=pipeline_result), \
         patch("src.api.job_runner.subprocess.run",
               side_effect=[mock_proc_cl, mock_proc_tp]) as mock_run, \
         patch("src.api.job_runner.parse_landxml") as mock_parse:
        run_job(job_id=job_id, ifc_path=fake_ifc, cl_path=fake_cl,
                name="T", interval=10.0, access_token="tok",
                org_url="https://x.arcgis.com", output_dir=output_dir)

    cl_call_args = mock_run.call_args_list[0][0][0]
    assert "src.arcpy_processor.ifc_cl_to_agol" in cl_call_args
    assert "--ifc-cl" in cl_call_args
    # .ifc skal ikke kalle parse_landxml — source-epsg er 25833
    mock_parse.assert_not_called()
    tp_call_args = mock_run.call_args_list[1][0][0]
    assert "25833" in tp_call_args


def test_list_jobs_response_includes_xb_url(tmp_path):
    from fastapi.testclient import TestClient
    from unittest.mock import patch
    import json as _json

    job_id = "test-list-xb"
    output_dir = tmp_path / job_id / "output"
    output_dir.mkdir(parents=True)

    meta = {"stations": [{"station": 0.0}]}
    (output_dir / "metadata.json").write_text(_json.dumps(meta))

    agol_urls = {
        "centerline_url": "https://cl",
        "sections_url": "https://sec",
        "xb_url": "https://experience.arcgis.com/builder/?id=abc",
    }
    (output_dir / "agol_urls.json").write_text(_json.dumps(agol_urls))

    from src.api.server import app
    client = TestClient(app)

    with patch("src.api.server.UPLOAD_DIR", tmp_path):
        resp = client.get("/api/jobs")

    assert resp.status_code == 200
    jobs = resp.json()
    match = next((j for j in jobs if j["job_id"] == job_id), None)
    assert match is not None
    assert match["xb_url"] == "https://experience.arcgis.com/builder/?id=abc"
