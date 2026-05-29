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

import json as _json
import os
import xml.etree.ElementTree as _ET
from pathlib import Path

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.requests import Request

try:
    from pyproj import Transformer as _ProjTransformer
    def _make_transformer(epsg: int):
        return _ProjTransformer.from_crs(f"EPSG:{epsg}", "EPSG:4326", always_xy=True)
except ImportError:
    def _make_transformer(epsg: int):  # type: ignore[misc]
        return None


def _get_landxml_epsg(xml_path: Path, fallback: int = 5111) -> int:
    """Read epsgCode attribute from the CoordinateSystem element of a LandXML file."""
    try:
        root = _ET.parse(xml_path).getroot()
        ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
        ns = {"lx": ns_uri} if ns_uri else {}
        cs = (root.find("lx:CoordinateSystem", ns) if ns_uri else root.find("CoordinateSystem"))
        if cs is not None and cs.get("epsgCode"):
            return int(cs.get("epsgCode"))
    except Exception:
        pass
    return fallback

load_dotenv()

from .auth_routes import router as auth_router, refresh_access_token
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
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:8080", "http://127.0.0.1:8080", "null"],
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
    cl_file: UploadFile = File(...),
    name: str = Form(...),
    interval: float = Form(10.0),
    publish_bim: bool = Form(False),
    bim_input_wkid: int | None = Form(None),
    bim_output_wkid: int = Form(25833),
    include_tverrprofil: bool = Form(True),
    include_lengdeprofil: bool = Form(True),
) -> dict:
    """Motta IFC + senterlinje (LandXML eller IFC4X3), start pipeline-jobb i bakgrunnen."""
    if "access_token" not in request.session:
        raise HTTPException(401, "Ikke innlogget — bruk /auth/login")
    if not ifc_file.filename or not ifc_file.filename.lower().endswith(".ifc"):
        raise HTTPException(400, "ifc_file må være en .ifc-fil")
    cl_name = (cl_file.filename or "").lower()
    if not (cl_name.endswith(".xml") or cl_name.endswith(".ifc")):
        raise HTTPException(400, "cl_file må være en .xml LandXML- eller .ifc IFC4X3-fil")
    if not (1 <= interval <= 100):
        raise HTTPException(400, "interval må være mellom 1 og 100 meter")

    fresh_token = refresh_access_token(request.session)

    job_id = job_runner.create_job()
    job_dir = UPLOAD_DIR / job_id
    job_dir.mkdir()

    ifc_path = job_dir / "model.ifc"
    cl_suffix = ".ifc" if cl_name.endswith(".ifc") else ".xml"
    cl_path = job_dir / f"centerline{cl_suffix}"

    with ifc_path.open("wb") as f:
        while chunk := await ifc_file.read(1024 * 1024):
            f.write(chunk)
    with cl_path.open("wb") as f:
        while chunk := await cl_file.read(1024 * 1024):
            f.write(chunk)

    background_tasks.add_task(
        job_runner.run_job,
        job_id=job_id,
        ifc_path=ifc_path,
        cl_path=cl_path,
        name=name,
        interval=interval,
        access_token=fresh_token,
        org_url=request.session.get("org_url", "https://www.arcgis.com"),
        output_dir=job_dir / "output",
        publish_bim=publish_bim,
        bim_input_wkid=bim_input_wkid,
        bim_output_wkid=bim_output_wkid,
        include_tverrprofil=include_tverrprofil,
        include_lengdeprofil=include_lengdeprofil,
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
        "xb_url": state.xb_url,
        "error": state.error,
    }


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    """Scan uploads/ and return jobs that have completed output (metadata.json)."""
    result: list[dict] = []
    try:
        dirs = sorted(UPLOAD_DIR.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        for d in dirs:
            if not d.is_dir():
                continue
            meta_file = d / "output" / "metadata.json"
            if not meta_file.exists():
                continue
            try:
                meta = _json.loads(meta_file.read_text(encoding="utf-8"))
                agol_urls_file = d / "output" / "agol_urls.json"
                agol_urls: dict = {}
                if agol_urls_file.exists():
                    agol_urls = _json.loads(agol_urls_file.read_text(encoding="utf-8"))
                result.append({
                    "job_id": d.name,
                    "n_stations": len(meta.get("stations", [])),
                    "modified": meta_file.stat().st_mtime,
                    "centerline_url": agol_urls.get("centerline_url"),
                    "sections_url": agol_urls.get("sections_url"),
                    "bim_url": agol_urls.get("bim_url"),
                    "xb_url": agol_urls.get("xb_url"),
                })
            except Exception:
                continue
            if len(result) >= 30:
                break
    except Exception:
        pass
    return result


@app.get("/api/jobs/{job_id}/geojson")
def get_job_geojson(job_id: str) -> dict:
    """Return a WGS84 GeoJSON FeatureCollection with the centerline and station points."""
    job_dir = UPLOAD_DIR / job_id
    if not job_dir.is_dir():
        raise HTTPException(404, "Jobb ikke funnet")

    meta_file = job_dir / "output" / "metadata.json"
    if not meta_file.exists():
        raise HTTPException(404, "Jobb har ingen output")

    meta = _json.loads(meta_file.read_text(encoding="utf-8"))
    meta_by_station = {s["station"]: s for s in meta.get("stations", [])}

    features: list[dict] = []

    # Prefer UTM33 data queried back from AGOL — convert 25833→4326 with pyproj
    stations_utm33_file = job_dir / "output" / "stations_utm33.json"
    cl_utm33_file = job_dir / "output" / "centerline_utm33.geojson"

    if stations_utm33_file.exists() and cl_utm33_file.exists():
        utm33_to_wgs84 = _make_transformer(25833)

        def _utm33_xy(x: float, y: float) -> tuple[float, float]:
            if utm33_to_wgs84:
                lon, lat = utm33_to_wgs84.transform(x, y)
                return round(lon, 8), round(lat, 8)
            return x, y

        def _reproject_coords(coords: list) -> list:
            """Reproject a nested coordinate list (LineString or ring) from UTM33 to WGS84."""
            if not coords:
                return coords
            if isinstance(coords[0], (int, float)):
                lon, lat = _utm33_xy(coords[0], coords[1])
                return [lon, lat] + (coords[2:] if len(coords) > 2 else [])
            return [_reproject_coords(c) for c in coords]

        cl_data = _json.loads(cl_utm33_file.read_text(encoding="utf-8"))
        for feat in cl_data.get("features", []):
            geom = feat.get("geometry", {})
            gtype = geom.get("type")
            if gtype in ("LineString", "MultiLineString"):
                reprojected = {
                    "type": gtype,
                    "coordinates": _reproject_coords(geom["coordinates"]),
                }
                features.append({
                    "type": "Feature",
                    "geometry": reprojected,
                    "properties": {"layer": "centerline"},
                })

        utm33_stations: list[dict] = _json.loads(
            stations_utm33_file.read_text(encoding="utf-8")
        )
        for s in utm33_stations:
            station_m: float = s["station_m"]
            m_info = meta_by_station.get(round(station_m, 3), {})
            svg_path = m_info.get("svg", "")
            svg_filename = Path(svg_path).name if svg_path else ""
            lon, lat = _utm33_xy(s["x"], s["y"])
            features.append({
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": {
                    "layer": "station",
                    "station_m": station_m,
                    "profil_nr": s.get("profil_nr", ""),
                    "elevation": m_info.get("elevation", 0),
                    "svg_filename": svg_filename,
                    "segment_classes": m_info.get("segment_classes", []),
                },
            })
        return {"type": "FeatureCollection", "features": features}

    # Fallback: transform from source CRS using pyproj
    stations_file = job_dir / "output" / "stations.json"
    cl_geojson_file = job_dir / "output" / "centerline.geojson"
    cl_xml_file = job_dir / "centerline.xml"
    cl_ifc_file = job_dir / "centerline.ifc"

    if cl_ifc_file.exists():
        epsg = 25833  # IFC4X3-senterlinje er i EUREF89 UTM33 (EPSG:25833)
    elif cl_xml_file.exists():
        epsg = _get_landxml_epsg(cl_xml_file)
    else:
        epsg = 5111
    transformer = _make_transformer(epsg)

    def _xy(x: float, y: float) -> tuple[float, float]:
        if transformer:
            lon, lat = transformer.transform(x, y)
            return round(lon, 8), round(lat, 8)
        return x, y

    stations_raw: list[dict] = (
        _json.loads(stations_file.read_text(encoding="utf-8")) if stations_file.exists() else []
    )

    if cl_geojson_file.exists():
        cl_data = _json.loads(cl_geojson_file.read_text(encoding="utf-8"))
        for feat in cl_data.get("features", []):
            geom = feat.get("geometry", {})
            if geom.get("type") == "LineString":
                coords = [
                    [*_xy(c[0], c[1]), round(c[2], 3) if len(c) > 2 else 0]
                    for c in geom["coordinates"]
                ]
                features.append({
                    "type": "Feature",
                    "geometry": {"type": "LineString", "coordinates": coords},
                    "properties": {"layer": "centerline"},
                })

    for s in stations_raw:
        lon, lat = _xy(s["x"], s["y"])
        station_m = s["station_m"]
        m_info = meta_by_station.get(station_m, {})
        svg_path = m_info.get("svg", "")
        svg_filename = Path(svg_path).name if svg_path else ""
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat, round(s.get("z", 0), 3)]},
            "properties": {
                "layer": "station",
                "station_m": station_m,
                "profil_nr": s.get("profil_nr", ""),
                "elevation": m_info.get("elevation", s.get("z", 0)),
                "svg_filename": svg_filename,
                "segment_classes": m_info.get("segment_classes", []),
            },
        })

    return {"type": "FeatureCollection", "features": features}


@app.get("/api/jobs/{job_id}/svg/{filename:path}")
def get_svg(job_id: str, filename: str) -> FileResponse:
    """Serve an SVG cross-section file from a job's output directory."""
    output_dir = (UPLOAD_DIR / job_id / "output").resolve()
    svg_path = (output_dir / filename).resolve()
    try:
        svg_path.relative_to(output_dir)
    except ValueError:
        raise HTTPException(403, "Ikke tillatt")
    if not svg_path.exists() or svg_path.suffix.lower() != ".svg":
        raise HTTPException(404, "SVG ikke funnet")
    return FileResponse(str(svg_path), media_type="image/svg+xml")


@app.get("/api/jobs/{job_id}/station-labels")
def get_station_labels(job_id: str) -> list[dict]:
    """Returner IfcReferent-stasjoneringsmerker for jobben (tom liste hvis ikke IFC-CL)."""
    path = UPLOAD_DIR / job_id / "output" / "station_labels.json"
    if not path.exists():
        return []
    try:
        return _json.loads(path.read_text(encoding="utf-8"))
    except (_json.JSONDecodeError, OSError):
        return []
