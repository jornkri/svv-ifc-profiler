# src/ifc_processor/pipeline.py
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from .centerline import Centerline, _stations_from_points, load_centerline, load_vertical_profile
from .cross_section import cut_cross_section, recenter_on_pavement, sample_stations, stitch_cross_section_gaps
from .ifc_reader import TINLayer, read_ifc_tins
from .longitudinal_profile import generate_longitudinal_profile
from .normal_section import compute_normal_section
from .renderer import render_cross_section_svg, render_longitudinal_profile_svg, render_normal_section_svg
from .terrain_sampler import fetch_terrain_profile, terrain_to_segments

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

    clipped = Centerline(
        points=pts[mask],
        stations=_stations_from_points(pts[mask]),
        source_epsg=centerline.source_epsg,
    )
    logger.info(
        "Senterlinje klippet fra %.1f m (%d pt) til %.1f m (%d pt) "
        "(IFC-bbox + %.0f m buffer)",
        centerline.total_length, len(pts),
        clipped.total_length, n_in, buffer_m,
    )
    return clipped


def _sample_tin_z_at_xy(
    xy: np.ndarray,
    tins: list[TINLayer],
) -> float | None:
    """Interpolate the highest road-surface Z at a given XY using barycentric coordinates."""
    best_z: float | None = None
    for tin in tins:
        tris = tin.triangles  # (N, 3, 3)
        a = tris[:, 0, :2]
        b = tris[:, 1, :2]
        c = tris[:, 2, :2]
        v0 = c - a
        v1 = b - a
        v2 = xy - a
        dot00 = (v0 * v0).sum(1)
        dot01 = (v0 * v1).sum(1)
        dot02 = (v0 * v2).sum(1)
        dot11 = (v1 * v1).sum(1)
        dot12 = (v1 * v2).sum(1)
        denom = dot00 * dot11 - dot01 ** 2
        valid = np.abs(denom) > 1e-12
        if not valid.any():
            continue
        inv = np.where(valid, 1.0 / np.where(valid, denom, 1.0), 0.0)
        u_b = (dot11 * dot02 - dot01 * dot12) * inv
        v_b = (dot00 * dot12 - dot01 * dot02) * inv
        inside = valid & (u_b >= -0.01) & (v_b >= -0.01) & (u_b + v_b <= 1.01)
        if not inside.any():
            continue
        z_vals = tris[:, 0, 2] + u_b * (tris[:, 2, 2] - tris[:, 0, 2]) + v_b * (tris[:, 1, 2] - tris[:, 0, 2])
        z_max = float(z_vals[inside].max())
        if best_z is None or z_max > best_z:
            best_z = z_max
    return best_z


def _elevate_centerline_from_tins(
    centerline: Centerline,
    tins: list[TINLayer],
) -> Centerline:
    """Set Z from road-surface TINs when the centerline has no elevation (Z≈0).

    LandXML horizontal alignments provide Z=0 for all points. This samples the
    highest road-surface Z from IFC TINs at each XY position so that cross-section
    v-coordinates become relative to the road surface rather than an arbitrary datum.
    """
    zs = centerline.points[:, 2]
    if np.abs(zs).max() > 5.0:
        return centerline  # already has meaningful elevation

    _ROAD_CLASSES = frozenset({"planum", "kjørefelt", "skulder"})
    road_tins = [t for t in tins if t.road_class in _ROAD_CLASSES] or tins
    if not road_tins:
        return centerline

    new_z = np.zeros(len(centerline.points))
    sampled = np.zeros(len(centerline.points), dtype=bool)
    for i, pt in enumerate(centerline.points):
        z = _sample_tin_z_at_xy(pt[:2], road_tins)
        if z is not None:
            new_z[i] = z
            sampled[i] = True

    n_sampled = int(sampled.sum())
    if n_sampled == 0:
        logger.warning("Ingen TIN-treff for senterlinjehøyde — beholder Z=0")
        return centerline

    # Interpolate gaps linearly
    xs = np.where(sampled)[0]
    new_z = np.interp(np.arange(len(new_z)), xs, new_z[xs])

    new_points = centerline.points.copy()
    new_points[:, 2] = new_z
    logger.info("Senterlinjehøyde samplet fra TINer: %d/%d punkter, Z=[%.2f..%.2f]",
                n_sampled, len(centerline.points), new_z.min(), new_z.max())
    return Centerline(
        points=new_points,
        stations=_stations_from_points(new_points),
        source_epsg=centerline.source_epsg,
    )


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
    include_terrain: bool = True,
    include_tverrprofil: bool = True,
    include_lengdeprofil: bool = True,
) -> dict:
    """Kjør full pipeline: IFC → tverrprofil-SVGer + metadata.

    Args:
        ifc_path:        Sti til .ifc-fil.
        centerline_path: Sti til senterlinje (GeoJSON eller CSV). Hvis None,
                         forsøker IfcAlignment, deretter medialakse-fallback.
        output_dir:      Katalog for SVG-er og metadata.
        interval_m:           Stasjoneringsintervall i meter (default 10).
        include_terrain:      Hent eksisterende terreng fra Kartverkets DTM1-API.
        include_tverrprofil:  Generer tverrprofil-SVGer.
        include_lengdeprofil: Generer lengdeprofil-SVG.

    Returns:
        Dict med nøklene "svgs", "centerline", "metadata", "stations_json".

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
    centerline = _elevate_centerline_from_tins(centerline, tins)
    logger.info("Senterlinje: %.1f m lang, %d punkter", centerline.total_length, len(centerline.points))

    terrain_tins = [t for t in tins if t.road_class == "terreng"]
    if terrain_tins:
        logger.info("Fant %d terreng-TINer i IFC — brukes til terrenghøyde i lengdeprofil", len(terrain_tins))

    # Vertikalprofil fra LandXML: brukes til riktig kotehøyde i stations.json/AGOL
    _vert_profile: list[tuple[float, float]] | None = None
    if centerline_path is not None:
        _vert_profile = load_vertical_profile(centerline_path)
    _vp_sta = np.array([p[0] for p in _vert_profile]) if _vert_profile else None
    _vp_elev = np.array([p[1] for p in _vert_profile]) if _vert_profile else None

    def _z_from_profile(station_m: float) -> float | None:
        if _vp_sta is None:
            return None
        return float(np.interp(station_m, _vp_sta, _vp_elev,
                               left=float(_vp_elev[0]), right=float(_vp_elev[-1])))

    stations = sample_stations(centerline, interval_m)
    logger.info("Genererer %d tverrprofiler (intervall: %.1f m)", len(stations), interval_m)

    svg_paths: list[str] = []
    metadata_rows: list[dict] = []
    station_rows: list[dict] = []

    # Samler data for lengdeprofil under stasjon-løkken
    lp_positions: list[np.ndarray] = []
    lp_terrain_z: list[float] = []
    lp_cross_falls: list[tuple[float, float]] = []

    if include_terrain:
        logger.info("Terrengsampling aktivert (Kartverket DTM1)")

    for s in stations:
        svg_path_str: str | None = None
        normal_svg_path_str: str | None = None
        terrain_z_cl = float("nan")
        terrain_z_ifc: float | None = None
        ns = None

        try:
            cs = cut_cross_section(tins, s)
            cs = stitch_cross_section_gaps(cs, tol=0.5)
            cs = recenter_on_pavement(cs)

            # Terrain fra IFC (rask, fra BIM — ingen HTTP-kall)
            if terrain_tins:
                terrain_z_ifc = _sample_tin_z_at_xy(s.position[:2], terrain_tins)
                if terrain_z_ifc is not None:
                    terrain_z_cl = terrain_z_ifc

            if include_terrain:
                # Kartverket DTM1 — overstyrer IFC-terreng, mer nøyaktig men treg
                terrain_pts = fetch_terrain_profile(
                    s.position, s.tangent, source_epsg=centerline.source_epsg
                )
                if terrain_pts:
                    if include_tverrprofil:
                        cs.segments["terreng"] = terrain_to_segments(terrain_pts)
                    if include_lengdeprofil:
                        u0 = min(terrain_pts, key=lambda p: abs(p[0]))
                        terrain_z_cl = float(s.position[2]) + u0[1]
                        terrain_z_ifc = terrain_z_cl

            ns = compute_normal_section(cs)

            if include_tverrprofil:
                _p = output_dir / f"tverrprofil_{s.distance:07.1f}.svg"
                render_cross_section_svg(cs, _p)
                svg_path_str = str(_p)
                svg_paths.append(svg_path_str)

            _np = output_dir / f"normalprofil_{s.distance:07.1f}.svg"
            render_normal_section_svg(cs, _np)
            normal_svg_path_str = str(_np)

        except Exception as exc:
            logger.warning("Hopper over stasjon %.1f m: %s", s.distance, exc)
            continue

        row: dict = {
            "station": round(s.distance, 3),
            "elevation": round(cs.elevation, 3),
            "segment_classes": list(cs.segments.keys()),
        }
        if svg_path_str:
            row["svg"] = svg_path_str
        if normal_svg_path_str:
            row["normal_svg"] = normal_svg_path_str
        metadata_rows.append(row)

        z_moh = _z_from_profile(s.distance)
        _cf_l = ns.left_cross_fall_pct if ns is not None and not (isinstance(ns.left_cross_fall_pct, float) and ns.left_cross_fall_pct != ns.left_cross_fall_pct) else None
        _cf_r = ns.right_cross_fall_pct if ns is not None and not (isinstance(ns.right_cross_fall_pct, float) and ns.right_cross_fall_pct != ns.right_cross_fall_pct) else None
        station_rows.append({
            "station_m": round(s.distance, 3),
            "profil_nr": f"{s.distance:07.2f}",
            "x": round(float(s.position[0]), 3),
            "y": round(float(s.position[1]), 3),
            "z": round(z_moh if z_moh is not None else float(s.position[2]), 3),
            "z_terreng": round(terrain_z_ifc, 3) if terrain_z_ifc is not None else None,
            "gradient_pct": None,   # fylles ut i neste pass nedenfor
            "cross_fall_l": round(_cf_l, 3) if _cf_l is not None else None,
            "cross_fall_r": round(_cf_r, 3) if _cf_r is not None else None,
        })

        if include_lengdeprofil:
            pos = s.position.copy()
            if z_moh is not None:
                pos[2] = z_moh
            lp_positions.append(pos)
            lp_terrain_z.append(terrain_z_cl)
            cf = (ns.left_cross_fall_pct, ns.right_cross_fall_pct) if ns else (float("nan"), float("nan"))
            lp_cross_falls.append(cf)

    cl_path = output_dir / "centerline.geojson"
    _save_centerline_geojson(centerline, cl_path)

    # Gradient-beregning: (z[i+1] - z[i]) / (station[i+1] - station[i]) * 100
    for i in range(len(station_rows) - 1):
        dz = station_rows[i + 1]["z"] - station_rows[i]["z"]
        ds = station_rows[i + 1]["station_m"] - station_rows[i]["station_m"]
        station_rows[i]["gradient_pct"] = round(dz / ds * 100, 2) if ds > 1e-6 else None
    # Siste stasjon har ingen neste — beholder None

    stations_json_path = output_dir / "stations.json"
    stations_json_path.write_text(json.dumps(station_rows, indent=2))

    meta_path = output_dir / "metadata.json"
    meta_path.write_text(json.dumps({"stations": metadata_rows}, indent=2))

    # Lengdeprofil: bygg mini-senterlinje fra de vellykede stasjonspunktene
    lp_svg_path: str | None = None
    if include_lengdeprofil and len(lp_positions) >= 2:
        try:
            mini_cl = Centerline.from_points(np.array(lp_positions))
            terrain_arg = (
                lp_terrain_z
                if any(not (isinstance(z, float) and z != z) for z in lp_terrain_z)
                else None
            )
            lp = generate_longitudinal_profile(
                centerline=mini_cl,
                terrain_elevations=terrain_arg,
                cross_falls=lp_cross_falls,
            )
            lp_path = output_dir / "lengdeprofil.svg"
            render_longitudinal_profile_svg(lp, lp_path)
            lp_svg_path = str(lp_path)
            logger.info("Lengdeprofil generert → %s", lp_path)
        except Exception as exc:
            logger.warning("Lengdeprofil feilet: %s", exc)

    logger.info("Pipeline ferdig. %d SVGer → %s", len(svg_paths), output_dir)
    return {
        "svgs": svg_paths,
        "centerline": str(cl_path),
        "metadata": str(meta_path),
        "stations_json": str(stations_json_path),
        "lengdeprofil": lp_svg_path,
    }
