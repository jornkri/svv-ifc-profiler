# src/ifc_processor/pipeline.py
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from .centerline import Centerline, load_centerline
from .cross_section import cut_cross_section, sample_stations
from .ifc_reader import TINLayer, read_ifc_tins
from .renderer import render_cross_section_svg

logger = logging.getLogger(__name__)


def _clip_centerline_to_tins(
    centerline: Centerline,
    tins: list[TINLayer],
    buffer_m: float = 50.0,
) -> Centerline:
    """Klipp senterlinjen til bounding-boksen til TINene + buffer.

    Brukes når senterlinjen er hentet fra en ekstern fil (LandXML/GeoJSON) som
    kan dekke et mye lengre vegstrekk enn IFC-modellen.
    Dersom under 2 punkter faller innenfor boksen, returneres originallinjen.
    """
    if not tins:
        return centerline

    # Bruk kun vegflate-TINer for å finne IFC-modellens faktiske strekningsutstrekning.
    # "Vegkropp og kryss"-TINer kan dekke et mye lengre strekk enn selve detaljmodellen.
    _SURFACE_CLASSES = {"planum", "kjørefelt", "skulder", "skjaering", "fylling"}
    surface_tins = [t for t in tins if t.road_class in _SURFACE_CLASSES]
    ref_tins = surface_tins if surface_tins else tins

    all_verts = np.vstack([t.triangles.reshape(-1, 3) for t in ref_tins])
    xy_min = all_verts[:, :2].min(axis=0) - buffer_m
    xy_max = all_verts[:, :2].max(axis=0) + buffer_m

    pts = centerline.points
    mask = (
        (pts[:, 0] >= xy_min[0]) & (pts[:, 0] <= xy_max[0]) &
        (pts[:, 1] >= xy_min[1]) & (pts[:, 1] <= xy_max[1])
    )
    n_in = int(mask.sum())

    if n_in == len(pts):
        return centerline  # Allerede innenfor

    if n_in < 2:
        logger.warning(
            "Senterlinje og IFC-modell overlapper ikke — bruker full senterlinje"
        )
        return centerline

    clipped = Centerline.from_points(pts[mask])
    logger.info(
        "Senterlinje klippet fra %.1f m (%d pt) til %.1f m (%d pt) "
        "(IFC-bbox + %.0f m buffer)",
        centerline.total_length, len(pts),
        clipped.total_length, n_in, buffer_m,
    )
    return clipped


def _save_centerline_geojson(centerline, path: Path) -> None:
    coords = [[float(p[0]), float(p[1]), float(p[2])] for p in centerline.points]
    path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {"note": "IFC lokalt koordinatsystem — ikke georeferert"}
        }]
    }, indent=2))


def run_pipeline(
    ifc_path: Path,
    centerline_path: Path | None = None,
    output_dir: Path = Path("output"),
    interval_m: float = 10.0,
) -> dict:
    """Kjør full pipeline: IFC → tverrprofil-SVGer + metadata.

    Args:
        ifc_path:        Sti til .ifc-fil.
        centerline_path: Sti til senterlinje (GeoJSON eller CSV). Hvis None,
                         forsøker IfcAlignment, deretter medialakse-fallback.
        output_dir:      Katalog for SVG-er og metadata.
        interval_m:      Stasjoneringsintervall i meter (default 10).

    Returns:
        Dict med nøklene "svgs", "centerline", "metadata".

    Raises:
        ValueError: Hvis ingen senterlinje kan bestemmes.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Leser TINer fra %s", ifc_path)
    try:
        tins = read_ifc_tins(ifc_path)
        logger.info("Leste %d TINer", len(tins))
    except Exception as exc:
        logger.warning("Kan ikke lese TINer (senterlinjeklipping deaktivert): %s", exc)
        tins = []

    centerline = load_centerline(source=centerline_path, ifc_path=ifc_path)
    centerline = _clip_centerline_to_tins(centerline, tins)
    logger.info("Senterlinje: %.1f m lang, %d punkter", centerline.total_length, len(centerline.points))

    stations = sample_stations(centerline, interval_m)
    logger.info("Genererer %d tverrprofiler (intervall: %.1f m)", len(stations), interval_m)

    svg_paths: list[str] = []
    metadata_rows: list[dict] = []
    station_rows: list[dict] = []

    for s in stations:
        try:
            cs = cut_cross_section(tins, s)
            svg_path = output_dir / f"station_{s.distance:07.1f}.svg"
            render_cross_section_svg(cs, svg_path)
        except Exception as exc:
            logger.warning("Hopper over stasjon %.1f m: %s", s.distance, exc)
            continue

        svg_paths.append(str(svg_path))
        metadata_rows.append({
            "station": round(s.distance, 3),
            "elevation": round(cs.elevation, 3),
            "svg": str(svg_path),
            "segment_classes": list(cs.segments.keys()),
        })
        station_rows.append({
            "station_m": round(s.distance, 3),
            "profil_nr": f"{s.distance:07.2f}",
            "x": round(float(s.position[0]), 3),
            "y": round(float(s.position[1]), 3),
            "z": round(float(s.position[2]), 3),
        })

    cl_path = output_dir / "centerline.geojson"
    _save_centerline_geojson(centerline, cl_path)

    stations_json_path = output_dir / "stations.json"
    stations_json_path.write_text(json.dumps(station_rows, indent=2))

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps({"stations": metadata_rows}, indent=2))

    logger.info("Pipeline ferdig. %d SVGer → %s", len(svg_paths), output_dir)
    return {
        "svgs": svg_paths,
        "centerline": str(cl_path),
        "metadata": str(meta_path),
        "stations_json": str(stations_json_path),
    }
