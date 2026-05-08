"""FastAPI-server for SVV IFC Profiler.

Endepunkter:
    GET  /api/health          → helsesjekk
    GET  /auth/login          → OAuth2 innlogging (redirect til AGOL)
    GET  /auth/callback       → OAuth2 callback (bytt code mot token)
    GET  /auth/me             → innlogget brukerinfo (fra session)
    POST /auth/logout         → logg ut (slett session)
    POST /api/jobs            → start ny pipeline-jobb
    GET  /api/jobs/{id}       → jobbstatus
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

load_dotenv()

from .auth_routes import router as auth_router
from . import job_runner

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(
    title="SVV IFC Profiler API",
    description="Generer tverr- og lengdeprofiler fra IFC-modeller iht. R700.",
    version="0.2.0",
)

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SECRET_KEY", "dev-secret-key-change-in-prod"),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth_router, prefix="/auth")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/jobs")
async def create_job(
    request: Request,
    background_tasks: BackgroundTasks,
    ifc_file: UploadFile = File(...),
    xml_file: UploadFile = File(...),
    name: str = Form(...),
    interval: float = Form(10.0),
    publish_bim: bool = Form(False),
) -> dict:
    """Motta IFC + LandXML, start pipeline-jobb i bakgrunnen."""
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget — bruk /auth/login")
    if not ifc_file.filename or not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "ifc_file må være en .ifc-fil")
    if not xml_file.filename or not xml_file.filename.lower().endswith(".xml"):
        raise HTTPException(400, "xml_file må være en .xml LandXML-fil")
    if not (1 <= interval <= 100):
        raise HTTPException(400, "interval må være mellom 1 og 100 meter")

    job_id = job_runner.create_job()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    ifc_path = job_dir / "model.ifc"
    xml_path = job_dir / "centerline.xml"

    with ifc_path.open("wb") as f:
        while chunk := await ifc_file.read(1024 * 1024):
            f.write(chunk)
    with xml_path.open("wb") as f:
        while chunk := await xml_file.read(1024 * 1024):
            f.write(chunk)

    background_tasks.add_task(
        job_runner.run_job,
        job_id=job_id,
        ifc_path=ifc_path,
        xml_path=xml_path,
        name=name,
        interval=interval,
        access_token=request.session["access_token"],
        org_url=request.session.get("org_url", "https://www.arcgis.com"),
        output_dir=job_dir / "output",
        publish_bim=publish_bim,
    )

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    state = job_runner.get_job(job_id)
    if state is None:
        raise HTTPException(404, "Jobb ikke funnet")
    return {
        "status": state.status,
        "progress_pct": state.progress_pct,
        "message": state.message,
        "centerline_url": state.centerline_url,
        "sections_url": state.sections_url,
        "bim_url": state.bim_url,
        "error": state.error,
    }
