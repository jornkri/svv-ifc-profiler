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
