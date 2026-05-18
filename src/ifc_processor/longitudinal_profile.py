"""Generer lengdeprofil langs vegens senterlinje (R700 C-tegning)."""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

from .centerline import Centerline

logger = logging.getLogger(__name__)


@dataclass
class LongitudinalProfile:
    """Lengdeprofil: stasjon → høyde for ulike linjer + rubrikk-data."""

    stations: list[float]
    surfaces: dict[str, list[float]]        # "vegoverflate": [...], "terreng": [...]
    cross_falls: list[tuple[float, float]]  # (left_pct, right_pct) per stasjon
    curve_points: list[tuple[float, float]] # (stasjon_m, delta_deg) horisontalkurvatur
    annotations: list[dict] = field(default_factory=list)


def _compute_curve_points(
    centerline: Centerline,
    min_angle_deg: float = 1.0,
) -> list[tuple[float, float]]:
    """Beregn horisontale kurvepunkter fra retningsendring i senterlinjen.

    Returns:
        Liste av (stasjon_m, delta_grader) der |delta| >= min_angle_deg.
        delta > 0: sving mot venstre (stigning i compass); delta < 0: høyre.
    """
    pts = centerline.points
    stations = centerline.stations
    if len(pts) < 3:
        return []

    bearings: list[float] = []
    for i in range(len(pts) - 1):
        dx = float(pts[i + 1, 0] - pts[i, 0])
        dy = float(pts[i + 1, 1] - pts[i, 1])
        bearings.append(math.degrees(math.atan2(dy, dx)))

    curve_pts: list[tuple[float, float]] = []
    for i in range(1, len(bearings)):
        delta = bearings[i] - bearings[i - 1]
        delta = (delta + 180) % 360 - 180   # normaliser til [-180, 180]
        if abs(delta) >= min_angle_deg:
            curve_pts.append((float(stations[i]), round(delta, 2)))

    return curve_pts


def generate_longitudinal_profile(
    centerline: Centerline,
    terrain_elevations: list[float] | None = None,
    cross_falls: list[tuple[float, float]] | None = None,
) -> LongitudinalProfile:
    """Generer lengdeprofil fra senterlinje og valgfri terreng/tverrfalldata.

    Args:
        centerline:          Senterlinjeobjekt med 3D-punkter og stasjonsarray.
        terrain_elevations:  Absolutt høyde (m) eksisterende terreng per stasjonspunkt.
                             Samme lengde som centerline.points. None = ikke tilgjengelig.
        cross_falls:         (left_pct, right_pct) per stasjonspunkt.
                             None = ikke tilgjengelig.

    Returns:
        LongitudinalProfile-objekt klar for rendering.
    """
    n = len(centerline.stations)
    stations = [float(s) for s in centerline.stations]
    design_z = [float(z) for z in centerline.points[:, 2]]

    surfaces: dict[str, list[float]] = {"vegoverflate": design_z}
    if terrain_elevations is not None and len(terrain_elevations) == n:
        surfaces["terreng"] = [float(z) for z in terrain_elevations]

    nan = float("nan")
    cf: list[tuple[float, float]] = (
        list(cross_falls)
        if cross_falls is not None and len(cross_falls) == n
        else [(nan, nan)] * n
    )

    return LongitudinalProfile(
        stations=stations,
        surfaces=surfaces,
        cross_falls=cf,
        curve_points=_compute_curve_points(centerline),
    )
