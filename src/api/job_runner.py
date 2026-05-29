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

_UPLOADS = Path("uploads")

logger = logging.getLogger(__name__)

try:
    from src.ifc_processor.pipeline import run_pipeline  # noqa: F401
except Exception:  # pragma: no cover
    run_pipeline = None  # type: ignore[assignment]

try:
    from src.arcpy_processor.landxml_parser import (  # noqa: F401
        parse_landxml,
        parse_horizontal_alignment,
    )
except Exception:  # pragma: no cover
    parse_landxml = None  # type: ignore[assignment]
    parse_horizontal_alignment = None  # type: ignore[assignment]


def _write_horizontal_alignment_json(xml_path: Path, output_dir: Path) -> None:
    """Skriv horizontal_alignment.json hvis LandXML har Alignment-blokk.

    Stille no-op hvis parse_horizontal_alignment ikke er tilgjengelig, hvis filen
    ikke inneholder Alignment-elementer, eller hvis parsing feiler (logg-bare).
    """
    if parse_horizontal_alignment is None:
        return
    try:
        segments = parse_horizontal_alignment(Path(xml_path))
    except Exception as exc:  # pragma: no cover — defensiv mot ufullstendig data
        logger.warning("Kunne ikke lese horisontal alignment fra %s: %s", xml_path, exc)
        return
    if not segments:
        return
    out = Path(output_dir) / "horizontal_alignment.json"
    out.write_text(json.dumps(segments, indent=2), encoding="utf-8")

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
    xb_url: str | None = None
    error: str | None = None
    output_dir: Path | None = field(default=None, repr=False)


_jobs: dict[str, JobState] = {}


def _persist_state(state: JobState) -> None:
    if state.output_dir is None:
        return
    try:
        state.output_dir.mkdir(parents=True, exist_ok=True)
        (state.output_dir / "job_state.json").write_text(
            json.dumps({
                "job_id": state.job_id,
                "status": state.status,
                "progress_pct": state.progress_pct,
                "message": state.message,
                "centerline_url": state.centerline_url,
                "sections_url": state.sections_url,
                "bim_url": state.bim_url,
                "xb_url": state.xb_url,
                "error": state.error,
            }),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Kunne ikke persistere jobstate: %s", exc)


def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobState(job_id=job_id, message="Starter pipeline…")
    return job_id


def get_job(job_id: str) -> JobState | None:
    state = _jobs.get(job_id)
    if state is not None:
        return state
    # Server kan ha restartet — prøv å lese fra disk
    state_file = _UPLOADS / job_id / "output" / "job_state.json"
    if state_file.exists():
        try:
            data = json.loads(state_file.read_text(encoding="utf-8"))
            state = JobState(**{k: v for k, v in data.items()})
            _jobs[job_id] = state
            return state
        except Exception as exc:
            logger.warning("Kunne ikke laste jobstate fra disk (%s): %s", state_file, exc)
    return None


def _update(state: JobState, pct: int, msg: str) -> None:
    state.progress_pct = pct
    state.message = msg
    logger.info("[%s] %d%% %s", state.job_id, pct, msg)
    _persist_state(state)


def run_job(
    job_id: str,
    ifc_path: Path,
    cl_path: Path,
    name: str,
    interval: float,
    access_token: str,
    org_url: str,
    output_dir: Path,
    publish_bim: bool = False,
    bim_input_wkid: int | None = None,
    bim_output_wkid: int = 25833,
    include_tverrprofil: bool = True,
    include_lengdeprofil: bool = True,
) -> None:
    """Kjør full pipeline i bakgrunnen. Oppdaterer jobbstatus underveis."""
    state = _jobs[job_id]
    state.status = "running"
    state.output_dir = output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    _persist_state(state)

    try:
        _update(state, 0, "Starter pipeline…")
        _update(state, 5, "Kjører IFC-prosessering…")

        profile_labels = [
            lbl for lbl, flag in [
                ("tverrprofil", include_tverrprofil),
                ("lengdeprofil", include_lengdeprofil),
            ] if flag
        ]
        _update(state, 5, f"Kjører IFC-prosessering ({', '.join(profile_labels)})…")

        pipeline_result = run_pipeline(
            ifc_path=ifc_path,
            centerline_path=cl_path,
            output_dir=output_dir,
            interval_m=interval,
            include_terrain=True,
            include_tverrprofil=include_tverrprofil,
            include_lengdeprofil=include_lengdeprofil,
        )

        meta = json.loads(Path(pipeline_result["metadata"]).read_text())
        n_sections = len(meta["stations"])
        _update(state, 50, f"Genererte {n_sections} stasjoner")

        is_ifc_cl = cl_path.suffix.lower() == ".ifc"
        if is_ifc_cl:
            # IFC4X3-senterlinje er i EUREF89 UTM33 (EPSG:25833)
            source_epsg = 25833
        else:
            _, source_epsg = parse_landxml(cl_path)
        # horizontal_alignment.json skrives nå av run_pipeline (for både LandXML og IFC-CL).

        lp_svg = pipeline_result.get("lengdeprofil")
        if is_ifc_cl:
            cl_cmd = [
                sys.executable, "-m", "src.arcpy_processor.ifc_cl_to_agol",
                "--ifc-cl", str(cl_path),
                "--name", f"{name}_senterlinje",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ]
        else:
            cl_cmd = [
                sys.executable, "-m", "src.arcpy_processor.landxml_to_agol",
                "--xml", str(cl_path),
                "--name", f"{name}_senterlinje",
                "--folder", "",
                "--token", access_token,
                "--org-url", org_url,
            ]
        if lp_svg:
            cl_cmd += ["--lengdeprofil", lp_svg]
        lp_label = " + lengdeprofil" if lp_svg else ""
        _update(state, 55, f"Publiserer senterlinje{lp_label} til AGOL…")
        cl_proc = subprocess.run(cl_cmd, check=True, capture_output=True, text=True)
        cl_result = json.loads(cl_proc.stdout)
        state.centerline_url = cl_result.get("url")
        logger.info("[%s] senterlinje stdout: %s", job_id, cl_proc.stdout.strip())
        logger.info("[%s] senterlinje stderr: %s", job_id, cl_proc.stderr.strip())

        # Persist UTM33 centerline queried back from AGOL
        if "utm33_centerline_paths" in cl_result and cl_result["utm33_centerline_paths"]:
            cl_utm33 = {
                "type": "FeatureCollection",
                "features": [{
                    "type": "Feature",
                    "geometry": {"type": "MultiLineString",
                                 "coordinates": cl_result["utm33_centerline_paths"]},
                    "properties": {},
                }],
            }
            (output_dir / "centerline_utm33.geojson").write_text(
                json.dumps(cl_utm33), encoding="utf-8"
            )
            logger.info("[%s] Lagret UTM33-senterlinje lokalt", job_id)

        _update(state, 70, f"Senterlinje{lp_label} publisert til AGOL")

        tp_result: dict = {}
        if include_tverrprofil:
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

            # Persist UTM33 station coordinates queried back from AGOL
            if "utm33_stations" in tp_result and tp_result["utm33_stations"]:
                (output_dir / "stations_utm33.json").write_text(
                    json.dumps(tp_result["utm33_stations"]), encoding="utf-8"
                )
                logger.info("[%s] Lagret %d UTM33-stasjoner lokalt",
                            job_id, len(tp_result["utm33_stations"]))

        def _persist_agol_urls() -> None:
            """Skriv agol_urls.json med alle tilgjengelige URL-er."""
            _agol = {k: v for k, v in {
                "centerline_url": state.centerline_url,
                "sections_url": state.sections_url,
                "bim_url": state.bim_url,
                "xb_url": state.xb_url,
            }.items() if v}
            if _agol:
                (output_dir / "agol_urls.json").write_text(
                    json.dumps(_agol), encoding="utf-8"
                )

        _persist_agol_urls()

        # Create / update Experience Builder app
        _xb_template = Path(__file__).parent.parent.parent / "templates" / "xb_config_template.json"
        if (
            include_tverrprofil
            and state.centerline_url
            and state.sections_url
            and _xb_template.exists()
        ):
            _update(state, 78, "Oppretter Experience Builder-app…")
            try:
                from arcgis.gis import GIS as _GIS
                from src.arcpy_processor.experience_builder import create_or_update_experience
                _gis = _GIS(url=org_url, token=access_token)
                state.xb_url = create_or_update_experience(
                    gis=_gis,
                    name=f"{name}_profilutforsker",
                    centerline_item_id=cl_result.get("item_id", ""),
                    sections_item_id=tp_result.get("item_id", ""),
                    sections_service_url=tp_result.get("url", ""),
                    template_path=_xb_template,
                )
                logger.info("[%s] XB-app URL: %s", job_id, state.xb_url)
            except Exception as _xb_exc:
                logger.warning("[%s] XB-app oppretting feilet: %s", job_id, _xb_exc)
            _persist_agol_urls()

        if publish_bim:
            _update(state, 80, "Publiserer BIM som 3D GIS-lag…")
            try:
                bim_cmd = [
                    sys.executable, "-m", "src.arcpy_processor.bim_to_agol",
                    "--ifc", str(ifc_path),
                    "--name", f"{name}_bim",
                    "--folder", "",
                    "--token", access_token,
                    "--org-url", org_url,
                    "--output-wkid", str(bim_output_wkid),
                ]
                if bim_input_wkid:
                    bim_cmd += ["--input-wkid", str(bim_input_wkid)]
                bim_proc = subprocess.run(
                    bim_cmd,
                    check=True, capture_output=True, text=True,
                )
                bim_result = json.loads(bim_proc.stdout)
                state.bim_url = bim_result.get("url")
                logger.info("[%s] BIM stdout: %s", job_id, bim_proc.stdout.strip())
                logger.info("[%s] BIM stderr: %s", job_id, bim_proc.stderr.strip())
                _persist_agol_urls()
                _update(state, 100, f"Ferdig — {n_sections} profiler + BIM-lag publisert")
                state.status = "done"
            except subprocess.CalledProcessError as exc:
                logger.warning("[%s] BIM-publisering feilet: %s", job_id, exc.stderr)
                state.error = exc.stderr or f"BIM-subprocess feilet med kode {exc.returncode}"
                _update(state, 100, f"Ferdig — {n_sections} profiler publisert (BIM feilet)")
                state.status = "done_with_warnings"
            except Exception as exc:
                logger.warning("[%s] BIM-publisering feilet uventet: %s", job_id, exc)
                state.error = str(exc)
                _update(state, 100, f"Ferdig — {n_sections} stasjoner publisert (BIM feilet)")
                state.status = "done_with_warnings"
        else:
            done_labels = ", ".join(profile_labels)
            _update(state, 100, f"Ferdig — {n_sections} stasjoner · {done_labels}")
            state.status = "done"

    except subprocess.CalledProcessError as exc:
        state.status = "failed"
        state.error = exc.stderr or f"Subprocess feilet med kode {exc.returncode}"
        logger.error("[%s] Subprocess feilet: %s", job_id, state.error)
        _persist_state(state)
    except Exception as exc:
        state.status = "failed"
        state.error = str(exc)
        logger.error("[%s] Jobb feilet: %s", job_id, exc, exc_info=True)
        _persist_state(state)
