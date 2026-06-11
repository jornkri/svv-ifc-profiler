# src/ifc_processor/cross_section.py
from __future__ import annotations

import logging
import math
from collections import defaultdict
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


def _chain_segments(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    tol: float = 0.02,
) -> list[list[tuple[float, float]]]:
    """Kjed sammen segmenter hvis endepunkter ligger innenfor `tol` meter.

    Bruker romlig hash (cellestørrelse = tol) slik at endepunkter som ikke er
    eksakt like likevel matches: målte gap mellom IFC-elementer er typisk
    9–340 mm, langt over den gamle 1 mm-avrundingsnøkkelen. Kjedene beholder
    de faktiske segment-endepunktene — hopp <= tol er usynlige i 1:200.
    """
    if not segs:
        return []

    inv = 1.0 / tol
    cell_nodes: dict[tuple[int, int], list[int]] = defaultdict(list)
    node_pts: list[tuple[float, float]] = []

    def node_for(p: tuple[float, float]) -> int:
        """Finn nærmeste eksisterende node innenfor tol, ellers opprett ny."""
        cx, cy = int(math.floor(p[0] * inv)), int(math.floor(p[1] * inv))
        best: int | None = None
        best_d = tol
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ni in cell_nodes.get((cx + dx, cy + dy), ()):
                    q = node_pts[ni]
                    d = math.hypot(p[0] - q[0], p[1] - q[1])
                    if d <= best_d:
                        best, best_d = ni, d
        if best is not None:
            return best
        ni = len(node_pts)
        node_pts.append(p)
        cell_nodes[(cx, cy)].append(ni)
        return ni

    # node -> [(nabo-node, segment-indeks)]
    adj: dict[int, list[tuple[int, int]]] = defaultdict(list)
    seg_nodes: list[tuple[int, int]] = []
    for idx, (p1, p2) in enumerate(segs):
        n1, n2 = node_for(p1), node_for(p2)
        seg_nodes.append((n1, n2))
        adj[n1].append((n2, idx))
        adj[n2].append((n1, idx))

    used: set[int] = set()
    chains: list[list[tuple[float, float]]] = []

    # Start fra grad-1-noder (kjedeender) for lengst mulig kjeder; ellers alle.
    starts = [n for n in adj if len(adj[n]) == 1] or list(adj)

    for start in starts:
        while any(si not in used for _other, si in adj[start]):
            chain_pts: list[tuple[float, float]] = []
            node = start
            while True:
                cand = [(other, si) for other, si in adj[node] if si not in used]
                if not cand:
                    break
                other, si = cand[0]
                used.add(si)
                p1, p2 = segs[si]
                n1, _n2 = seg_nodes[si]
                a, b = (p1, p2) if n1 == node else (p2, p1)
                if not chain_pts:
                    chain_pts.append(a)
                chain_pts.append(b)
                node = other
            if len(chain_pts) >= 2:
                chains.append(chain_pts)

    # Segmenter som aldri ble nådd (f.eks. lukkede sykluser uten grad-1-node)
    for idx, (p1, p2) in enumerate(segs):
        if idx not in used:
            chains.append([p1, p2])

    return chains


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


# Bro-segmenter legges i klassen med lavest prioritet, slik at broer ikke
# forstyrrer øvre-envelope-renderingen av vegdekkeklassene.
_PRIO = {
    "planum": 5, "kjørefelt": 5, "skulder": 4, "kantstein": 4, "gang_sykkel": 4,
    "groft": 3, "skjaering": 3, "fylling": 3, "terreng": 2, "unknown": 1,
}


def stitch_cross_section_gaps(
    cs: CrossSection,
    tol: float = 0.40,
) -> CrossSection:
    """Tett modelleringsgap mellom tilstøtende IFC-elementer med bro-segmenter.

    IFC-vegmodeller lagrer planum, fylling, skulder etc. som separate
    TIN-objekter. Disse møtes geometrisk, men har gap på 9–340 mm ved kantene.
    Strategi: kjed segmentene per klasse og se kun på KJEDE-endepunkter (ikke
    alle rå segment-endepunkter). Bro legges kun mellom gjensidig nærmeste
    endepunkt-par fra ulike kjeder, og hvert endepunkt brukes maks én gang.
    Det hindrer stjerne-artefakter strukturelt, slik at toleransen kan være
    høy nok (0,40 m) til å dekke reelle gap — også innen samme klasse.

    Terreng broes aldri: naturlige terrengbrudd skal forbli åpne.
    """
    # (u, v, klasse, kjede-id) for begge ender av hver kjede
    endpoints: list[tuple[float, float, str, int]] = []
    chain_id = 0
    for cls, segs in cs.segments.items():
        if cls == "terreng":
            continue
        for chain in _chain_segments(segs):
            if len(chain) < 2:
                continue
            endpoints.append((chain[0][0], chain[0][1], cls, chain_id))
            endpoints.append((chain[-1][0], chain[-1][1], cls, chain_id))
            chain_id += 1

    def nearest(i: int) -> int | None:
        """Nærmeste endepunkt fra en ANNEN kjede, innenfor tol."""
        u1, v1, _c1, ch1 = endpoints[i]
        best: int | None = None
        best_d = tol
        for j, (u2, v2, _c2, ch2) in enumerate(endpoints):
            if ch2 == ch1:
                continue
            d = math.hypot(u2 - u1, v2 - v1)
            if 1e-9 < d <= best_d:
                best, best_d = j, d
        return best

    new_segs: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {
        k: list(v) for k, v in cs.segments.items()
    }
    bridged: set[int] = set()
    for i in range(len(endpoints)):
        if i in bridged:
            continue
        j = nearest(i)
        if j is None or j in bridged:
            continue
        if nearest(j) != i:
            continue  # ikke gjensidig nærmeste — dropp
        u1, v1, c1, _ = endpoints[i]
        u2, v2, c2, _ = endpoints[j]
        bridged.add(i)
        bridged.add(j)
        bridge_cls = c1 if _PRIO.get(c1, 0) <= _PRIO.get(c2, 0) else c2
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
