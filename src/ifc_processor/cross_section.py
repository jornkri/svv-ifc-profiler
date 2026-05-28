# src/ifc_processor/cross_section.py
from __future__ import annotations

import logging
import math
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
    # IFC Name-label → liste av linjestykker (f.eks. "Bindlag 1", "V. Grøft 2")
    named_segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = field(
        default_factory=dict
    )


def sample_stations(centerline: Centerline, interval_m: float = 10.0, start_offset: float = 0.0) -> list[Station]:
    pts = centerline.points
    sts = centerline.stations
    total = sts[-1]

    target_distances = np.arange(start_offset, total + 1e-9, interval_m)
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

    # Triangelet er helt på én side — men la gjennom hvis nøyaktig 2 hjørner
    # ligger i planet (kant-interseksjon). DitchBottomSurface-triangler har
    # ofte kanter vinkelrett på vegen som faller eksakt i skjæreplanet.
    if np.all(signs >= 0) or np.all(signs <= 0):
        if np.sum(signs == 0) != 2:
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

    # Fjern duplikater (kan skje hvis to kanter møtes i et hjørne på planet).
    # np.allclose med standard rtol=1e-5 gir ~10 m toleranse for UTM-koordinater (~10^6) —
    # bruk absolutt euklidsk avstand i stedet.
    unique: list[np.ndarray] = []
    for p in pts:
        if not any(np.linalg.norm(p - q) < 1e-3 for q in unique):
            unique.append(p)

    return unique if len(unique) == 2 else []


def _project_to_2d(
    p: np.ndarray,
    plane_point: np.ndarray,
    tangent: np.ndarray,
) -> tuple[float, float]:
    """Projiser 3D-punkt til 2D i snittplanets koordinatsystem."""
    horiz = np.array([tangent[0], tangent[1], 0.0])
    horiz_norm = np.linalg.norm(horiz)
    if horiz_norm > 1e-9:
        horiz /= horiz_norm
        u = np.cross(horiz, np.array([0.0, 0.0, 1.0]))
    else:
        logger.warning("Tangent er nær vertikal — bruker fallback u-akse")
        u = np.array([0.0, 1.0, 0.0])
    delta = p - plane_point
    return float(delta @ u), float(delta[2])


def cut_cross_section(tins: list[TINLayer], station: Station) -> CrossSection:
    """Snitt alle TINer med et plan vinkelrett på tangenten ved stasjonen."""
    plane_point = station.position
    plane_normal = station.tangent

    segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    named_segs: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}

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
            label = tin.label or tin.name or cls
            named_segs.setdefault(label, []).extend(tin_segs)

    if not segments:
        logger.warning("Tomt snitt ved stasjon %.1f m — hopper over", station.distance)

    return CrossSection(
        station=station.distance,
        elevation=float(station.position[2]),
        segments=segments,
        named_segments=named_segs,
    )


def stitch_cross_section_gaps(
    cs: CrossSection,
    tol: float = 0.02,
) -> CrossSection:
    """Tett modelleringsgap mellom tilstøtende IFC-elementer.

    IFC-vegmodeller lagrer planum, fylling, skulder etc. som separate TIN-objekter.
    Disse møtes geometrisk, men kan ha sub-centimeter gap ved kantene. Etter snitting
    gir dette isolerte segmenter fra hvert element. Denne funksjonen legger til
    korte bro-segmenter mellom endepunkter fra ulike lag som er innenfor `tol` meter
    fra hverandre, slik at tverrprofilet blir visuelt sammenhengende.

    tol=0.02 m: bro bare for ekte modelleringsgap (< 2 cm). Større avstand betyr
    separate fysiske elementer — kobling der ville skapt stjerne-artefakter i rendering.
    """
    # Bygg liste av alle (u, v, road_class) for endepunkter i alle kjeder
    # Kjeden-endepunkter finner vi ved å bruke samme chaining-logikk.
    # Enklere: bruk råsegmentenes endepunkter direkte.
    endpoints: list[tuple[float, float, str]] = []
    for cls, segs in cs.segments.items():
        for (u1, v1), (u2, v2) in segs:
            endpoints.append((u1, v1, cls))
            endpoints.append((u2, v2, cls))

    new_segs: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {
        k: list(v) for k, v in cs.segments.items()
    }
    seen: set[tuple] = set()

    for i in range(len(endpoints)):
        u1, v1, cls1 = endpoints[i]
        for j in range(i + 1, len(endpoints)):
            u2, v2, cls2 = endpoints[j]
            if cls1 == cls2:
                continue
            dist = math.hypot(u2 - u1, v2 - v1)
            if 0 < dist <= tol:
                key = (round(u1, 4), round(v1, 4), round(u2, 4), round(v2, 4))
                rkey = (round(u2, 4), round(v2, 4), round(u1, 4), round(v1, 4))
                if key not in seen and rkey not in seen:
                    seen.add(key)
                    # Bro-segmentet legges alltid i det LAVERE-prioritets laget.
                    # Vegdekkeklassene (planum, kjørefelt, skulder) bruker øvre-envelope
                    # rendering — broer inn i dem forstyrrer envelopen og gir feil profil.
                    _PRIO = {
                        "planum": 5, "kjørefelt": 5, "skulder": 4, "groft": 3,
                        "skjaering": 3, "fylling": 3, "terreng": 2, "unknown": 1,
                    }
                    bridge_cls = cls1 if _PRIO.get(cls1, 0) <= _PRIO.get(cls2, 0) else cls2
                    new_segs.setdefault(bridge_cls, []).append(((u1, v1), (u2, v2)))

    return CrossSection(
        station=cs.station,
        elevation=cs.elevation,
        segments=new_segs,
        named_segments=cs.named_segments,
    )


def recenter_on_pavement(cs: CrossSection) -> CrossSection:
    """Flytt u=0 til midtpunktet av vegdekket.

    LandXML-alignment kan representere en kantlinje eller en linje som ikke er
    veggeometrisk senterlinje. Denne funksjonen beregner midtpunktet av
    kjørefelt/planum-geometrien i u-retningen og trekker det fra alle u-verdier,
    slik at u=0 alltid ligger i vegmidten.
    """
    _PAVEMENT = ("planum", "kjørefelt", "skulder")
    pav_u: list[float] = []
    for cls in _PAVEMENT:
        for (u1, _), (u2, _) in cs.segments.get(cls, []):
            pav_u.extend([u1, u2])
    if not pav_u:
        return cs

    u_offset = (min(pav_u) + max(pav_u)) / 2.0
    if abs(u_offset) < 0.3:          # allerede sentrert nok
        return cs

    new_segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for cls, segs in cs.segments.items():
        new_segments[cls] = [
            ((u1 - u_offset, v1), (u2 - u_offset, v2))
            for (u1, v1), (u2, v2) in segs
        ]
    new_named: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    for label, segs in cs.named_segments.items():
        new_named[label] = [
            ((u1 - u_offset, v1), (u2 - u_offset, v2))
            for (u1, v1), (u2, v2) in segs
        ]
    return CrossSection(station=cs.station, elevation=cs.elevation, segments=new_segments, named_segments=new_named)


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
