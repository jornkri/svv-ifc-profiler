# src/ifc_processor/cross_section.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field

import numpy as np

from .centerline import Centerline
from .ifc_reader import TINLayer

logger = logging.getLogger(__name__)


@dataclass
class Station:
    distance: float       # meter fra start
    position: np.ndarray  # shape (3,): XYZ
    tangent: np.ndarray   # shape (3,): normalisert retningsvektor


@dataclass
class CrossSection:
    station: float
    elevation: float      # z-koordinat til senterlinjen
    # road_class → liste av linjestykker i 2D snittplan
    # hvert linjestykke: ((u1, v1), (u2, v2)) der u=horisontal, v=vertikal
    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = field(
        default_factory=dict
    )


def sample_stations(centerline: Centerline, interval_m: float = 10.0) -> list[Station]:
    pts = centerline.points
    sts = centerline.stations
    total = sts[-1]

    target_distances = np.arange(0.0, total + 1e-9, interval_m)
    stations: list[Station] = []

    for d in target_distances:
        idx = np.searchsorted(sts, d)
        idx = np.clip(idx, 1, len(sts) - 1)

        t = (d - sts[idx - 1]) / max(sts[idx] - sts[idx - 1], 1e-12)
        pos = pts[idx - 1] + t * (pts[idx] - pts[idx - 1])

        tang = pts[idx] - pts[idx - 1]
        norm = np.linalg.norm(tang)
        tang = tang / norm if norm > 1e-9 else np.array([1.0, 0.0, 0.0])

        stations.append(Station(distance=float(d), position=pos, tangent=tang))

    return stations


def _intersect_triangle_plane(
    tri: np.ndarray,
    plane_point: np.ndarray,
    plane_normal: np.ndarray,
) -> list[np.ndarray]:
    """Returner 0 eller 2 skjæringspunkter der triangelet krysser planet."""
    d = (tri - plane_point) @ plane_normal  # signed distances, shape (3,)
    signs = np.sign(d)

    # Triangelet er helt på én side (inkludert ren tangering langs én kant)
    if np.all(signs >= 0) or np.all(signs <= 0):
        return []

    pts: list[np.ndarray] = []
    for i in range(3):
        j = (i + 1) % 3
        si, sj = signs[i], signs[j]
        if si == 0:
            # Hjørne i ligger eksakt i planet — legg til én gang (når vi kommer fra siden j!=0)
            # Legg til bare hvis nabohjørnet ikke også er i planet (unngå dobbel telling)
            pts.append(tri[i].copy())
        elif si * sj < 0:
            # Kant krysser planet mellom i og j
            t = d[i] / (d[i] - d[j])
            pts.append(tri[i] + t * (tri[j] - tri[i]))

    # Fjern duplikater (kan skje hvis to kanter møtes i et hjørne på planet)
    unique: list[np.ndarray] = []
    for p in pts:
        if not any(np.allclose(p, q, atol=1e-9) for q in unique):
            unique.append(p)

    return unique if len(unique) == 2 else []


def _project_to_2d(
    p: np.ndarray,
    plane_point: np.ndarray,
    tangent: np.ndarray,
) -> tuple[float, float]:
    """Projiser 3D-punkt til 2D i snittplanets koordinatsystem."""
    u = np.cross(tangent, np.array([0.0, 0.0, 1.0]))
    u_norm = np.linalg.norm(u)
    u = u / u_norm if u_norm > 1e-9 else np.array([0.0, 1.0, 0.0])
    delta = p - plane_point
    return float(delta @ u), float(delta[2])


def cut_cross_section(tins: list[TINLayer], station: Station) -> CrossSection:
    """Snitt alle TINer med et plan vinkelrett på tangenten ved stasjonen."""
    plane_point = station.position
    plane_normal = station.tangent

    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}

    for tin in tins:
        cls = tin.road_class
        tin_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []

        for tri in tin.triangles:
            pts_3d = _intersect_triangle_plane(tri, plane_point, plane_normal)
            if len(pts_3d) == 2:
                uv1 = _project_to_2d(pts_3d[0], plane_point, plane_normal)
                uv2 = _project_to_2d(pts_3d[1], plane_point, plane_normal)
                tin_segs.append((uv1, uv2))

        if tin_segs:
            segments.setdefault(cls, []).extend(tin_segs)

    if not segments:
        logger.warning("Tomt snitt ved stasjon %.1f m — hopper over", station.distance)

    return CrossSection(
        station=station.distance,
        elevation=float(station.position[2]),
        segments=segments,
    )


def generate_cross_sections(
    centerline: Centerline,
    tins: list[TINLayer],
    interval_m: float = 10.0,
) -> list[CrossSection]:
    stations = sample_stations(centerline, interval_m)
    result = []
    for s in stations:
        cs = cut_cross_section(tins, s)
        result.append(cs)
    return result
