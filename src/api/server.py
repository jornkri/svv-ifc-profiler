"""FastAPI-server som tar imot IFC-opplastinger og leverer profilresultater.

Endepunkter (utkast):
    POST /api/upload                   → motta IFC, kjør prosessering, returner job_id
    GET  /api/jobs/{job_id}            → status (pending/running/done/failed)
    GET  /api/jobs/{job_id}/centerline → senterlinje som GeoJSON for kartvisning
    GET  /api/jobs/{job_id}/section?station={m}
                                       → tverrprofil som PNG eller SVG
    GET  /api/jobs/{job_id}/longitudinal
                                       → lengdeprofil som PNG eller SVG
"""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="SVV IFC Profiler API",
    description="Generer tverr- og lengdeprofiler fra IFC-modeller iht. R700.",
    version="0.1.0",
)

# CORS for lokal frontend-utvikling (Vite default port 5173)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory jobbregister (erstattes senere med Redis / SQLite / queue)
JOBS: dict[str, dict] = {}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/upload")
async def upload_ifc(file: UploadFile = File(...)) -> dict:
    """Motta en IFC-fil, lagre den, og opprett en jobb."""
    if not file.filename or not file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "Forventet en .ifc-fil")

    job_id = str(uuid.uuid4())
    target = UPLOAD_DIR / f"{job_id}.ifc"

    with target.open("wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    JOBS[job_id] = {
        "status": "pending",
        "ifc_path": str(target),
        "filename": file.filename,
    }

    # TODO: kø prosesseringsjobben (background task / Celery / RQ).
    return {"job_id": job_id, "status": "pending"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    if job_id not in JOBS:
        raise HTTPException(404, "Jobb ikke funnet")
    return JOBS[job_id]


@app.get("/api/jobs/{job_id}/centerline")
def get_centerline(job_id: str) -> dict:
    """Returner senterlinje som GeoJSON. TODO: implementer."""
    if job_id not in JOBS:
        raise HTTPException(404, "Jobb ikke funnet")
    raise HTTPException(501, "Ikke implementert ennå")


@app.get("/api/jobs/{job_id}/section")
def get_cross_section(job_id: str, station: float) -> dict:
    """Returner tverrprofil ved gitt stasjon (i meter). TODO: implementer."""
    if job_id not in JOBS:
        raise HTTPException(404, "Jobb ikke funnet")
    raise HTTPException(501, "Ikke implementert ennå")
