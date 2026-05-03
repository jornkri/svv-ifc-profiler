# src/ifc_processor/pipeline.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from .centerline import load_centerline
from .cross_section import cut_cross_section, sample_stations
from .ifc_reader import read_ifc_tins
from .renderer import render_cross_section_svg

logger = logging.getLogger(__name__)


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

    centerline = load_centerline(source=centerline_path, ifc_path=ifc_path)
    logger.info("Senterlinje: %.1f m lang, %d punkter", centerline.total_length, len(centerline.points))

    logger.info("Leser TINer fra %s", ifc_path)
    tins = read_ifc_tins(ifc_path)
    logger.info("Leste %d TINer", len(tins))

    stations = sample_stations(centerline, interval_m)
    logger.info("Genererer %d tverrprofiler (intervall: %.1f m)", len(stations), interval_m)

    svg_paths: list[str] = []
    metadata_rows: list[dict] = []

    for s in stations:
        try:
            cs = cut_cross_section(tins, s)
        except Exception as exc:
            logger.warning("Hopper over stasjon %.1f m: %s", s.distance, exc)
            continue

        svg_path = output_dir / f"station_{s.distance:07.1f}.svg"
        render_cross_section_svg(cs, svg_path)
        svg_paths.append(str(svg_path))
        metadata_rows.append({
            "station": round(s.distance, 3),
            "elevation": round(cs.elevation, 3),
            "svg": str(svg_path),
            "segment_classes": list(cs.segments.keys()),
        })

    cl_path = output_dir / "centerline.geojson"
    _save_centerline_geojson(centerline, cl_path)

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps({"stations": metadata_rows}, indent=2))

    logger.info("Pipeline ferdig. %d SVGer → %s", len(svg_paths), output_dir)
    return {
        "svgs": svg_paths,
        "centerline": str(cl_path),
        "metadata": str(meta_path),
    }
