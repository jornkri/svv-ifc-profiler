# src/api/job_runner.py
"""Bakgrunnsjobb-orkestrator for IFC → AGOL pipeline."""
from __future__ import annotations

import json
import logging
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

try:
    from src.ifc_processor.pipeline import run_pipeline  # noqa: F401
except Exception:  # pragma: no cover
    run_pipeline = None  # type: ignore[assignment]

try:
    from src.arcpy_processor.landxml_parser import parse_landxml  # noqa: F401
except Exception:  # pragma: no cover
    parse_landxml = None  # type: ignore[assignment]

JobStatus = Literal["queued", "running", "done", "done_with_warnings", "failed"]


@dataclass
class JobState:
    job_id: str
    status: JobStatus = "queued"
    progress_pct: int = 0
    message: str = "Venter…"
    centerline_url: str | None = None
    sections_url: str | None = None
    bim_url: str | None = None
    error: str | None = None


_jobs: dict[str, JobState] = {}


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobState(job_id=job_id, message="Starter pipeline…")
    return job_id


def get_job(job_id: str) -> JobState | None:
    return _jobs.get(job_id)


def _update(state: JobState, pct: int, msg: str) -> None:
    state.progress_pct = pct
    state.message = msg
    logger.info("[%s] %d%% %s", state.job_id, pct, msg)


def run_job(
    job_id: str,
    ifc_path: Path,
    xml_path: Path,
    name: str,
    interval: float,
    access_token: str,
    org_url: str,
    output_dir: Path,
    publish_bim: bool = False,
) -> None:
    """Kjør full pipeline i bakgrunnen. Oppdaterer jobbstatus underveis."""
    state = _jobs[job_id]
    state.status = "running"

    try:
        _update(state, 0, "Starter pipeline…")
        _update(state, 5, "Kjører IFC-prosessering…")

        pipeline_result = run_pipeline(
            ifc_path=ifc_path,
            centerline_path=xml_path,
            output_dir=output_dir,
            interval_m=interval,
        )

        meta = json.loads(Path(pipeline_result["metadata"]).read_text())
        n_sections = len(meta["stations"])
        _update(state, 50, f"Genererte {n_sections} tverrprofiler")

        _, source_epsg = parse_landxml(xml_path)

        _update(state, 55, "Publiserer senterlinje til AGOL…")
        cl_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
                "--xml", str(xml_path),
                "--name", f"{name}_senterlinje",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        cl_result = json.loads(cl_proc.stdout)
        state.centerline_url = cl_result.get("url")
        logger.info("[%s] senterlinje stdout: %s", job_id, cl_proc.stdout.strip())
        logger.info("[%s] senterlinje stderr: %s", job_id, cl_proc.stderr.strip())
        _update(state, 70, "Senterlinje publisert til AGOL")

        _update(state, 75, "Publiserer tverrprofiler til AGOL…")
        tp_proc = subprocess.run(
            [
                sys.executable, "-m", "src.arcpy_processor.tverrprofil_to_agol",
                "--stations-json", pipeline_result["stations_json"],
                "--svgs-dir", str(output_dir),
                "--name", f"{name}_tverrprofiler",
                "--folder", "",
                "--source-epsg", str(source_epsg),
                "--token", access_token,
                "--org-url", org_url,
            ],
            check=True, capture_output=True, text=True,
        )
        tp_result = json.loads(tp_proc.stdout)
        state.sections_url = tp_result.get("url")
        logger.info("[%s] tverrprofil stdout: %s", job_id, tp_proc.stdout.strip())
        logger.info("[%s] tverrprofil stderr: %s", job_id, tp_proc.stderr.strip())

        if publish_bim:
            _update(state, 80, "Publiserer BIM som 3D GIS-lag…")
            try:
                bim_proc = subprocess.run(
                    [
                        sys.executable, "-m", "src.arcpy_processor.bim_to_agol",
                        "--ifc", str(ifc_path),
                        "--name", f"{name}_bim",
                        "--folder", "",
                        "--token", access_token,
                        "--org-url", org_url,
                    ],
                    check=True, capture_output=True, text=True,
                )
                bim_result = json.loads(bim_proc.stdout)
                state.bim_url = bim_result.get("url")
                logger.info("[%s] BIM stdout: %s", job_id, bim_proc.stdout.strip())
                _update(state, 100, f"Ferdig — {n_sections} profiler + BIM-lag publisert")
                state.status = "done"
            except subprocess.CalledProcessError as exc:
                logger.warning("[%s] BIM-publisering feilet: %s", job_id, exc.stderr)
                state.error = exc.stderr or f"BIM-subprocess feilet med kode {exc.returncode}"
                _update(state, 100, f"Ferdig — {n_sections} profiler publisert (BIM feilet)")
                state.status = "done_with_warnings"
        else:
            _update(state, 100, f"Ferdig — {n_sections} profiler publisert")
            state.status = "done"

    except subprocess.CalledProcessError as exc:
        state.status = "failed"
        state.error = exc.stderr or f"Subprocess feilet med kode {exc.returncode}"
        logger.error("[%s] Subprocess feilet: %s", job_id, state.error)
    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        logger.error("[%s] Jobb feilet: %s", job_id, exc, exc_info=True)
