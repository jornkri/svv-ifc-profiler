# src/ifc_processor/normal_section.py
from __future__ import annotations

import math
from dataclasses import dataclass

from .cross_section import CrossSection


@dataclass
class NormalSection:
    station: float
    elevation: float
    left_carriageway_width: float   # m fra CL til yttergrense kjørefelt
    right_carriageway_width: float
    left_shoulder_width: float      # m ekstra bredde utover kjørefelt, NaN hvis ingen
    right_shoulder_width: float
    left_ditch_depth: float         # vertikal dybde grøft, NaN hvis ingen
    right_ditch_depth: float
    left_slope_ratio: float         # 1:x for skjæring/fylling, NaN hvis ingen
    right_slope_ratio: float
    left_cross_fall_pct: float      # % fall på kjørebanens venstre side
    right_cross_fall_pct: float
    section_type: str               # "skjæring" | "fylling" | "plan" | "kombinasjon"


def _outer_u(segs: list, left: bool) -> float:
    """Returnerer max |u| for segmenter på angitt side, NaN hvis ingen."""
    pts = []
    for (u1, v1), (u2, v2) in segs:
        for u, _ in [(u1, v1), (u2, v2)]:
            if left and u < 0:
                pts.append(abs(u))
            elif not left and u > 0:
                pts.append(u)
    return max(pts) if pts else float("nan")


def _cross_fall(segs: list, left: bool) -> float:
    """Beregner tverrfall (%) som median av segmentene på angitt side.

    Filtrerer ut segmenter med |slope| > 15 % — disse er ikke kjørebane (typisk
    rekkverk-kant, kantstein, eller numerisk støy der du≈0). Median er mer
    robust enn middel mot enkeltavvik.

    Fortegnet bevares: tverrfallet er den signerte transversal-gradienten
    dv/du (regnet i retning økende u, dvs. fra venstre mot høyre). Uttrykket er
    uavhengig av segmentets punktrekkefølge fordi teller og nevner snur fortegn
    sammen. For takfall gir dette motsatt fortegn på venstre (+) og høyre (−)
    side; ved overhøyde/ensidig fall får begge sider samme fortegn. Det lar
    lengdeprofilen skille takfall fra banket (jf. cross_fall_l/-r i stations.json).
    """
    slopes = []
    for (u1, v1), (u2, v2) in segs:
        mid_u = (u1 + u2) / 2
        if left and mid_u > 0:
            continue
        if not left and mid_u < 0:
            continue
        du = u2 - u1
        if abs(du) < 1e-6:
            continue
        pct = (v2 - v1) / du * 100  # signert gradient i retning økende u
        if abs(pct) > 15:  # ikke kjørebane
            continue
        slopes.append(pct)
    if not slopes:
        return float("nan")
    slopes.sort()
    n = len(slopes)
    return slopes[n // 2] if n % 2 else (slopes[n // 2 - 1] + slopes[n // 2]) / 2


def _slope_ratio(segs: list, left: bool) -> float:
    """Beregner gjennomsnittlig 1:x skråningsforhold fra segmenter på angitt side."""
    ratios = []
    for (u1, v1), (u2, v2) in segs:
        mid_u = (u1 + u2) / 2
        if left and mid_u > 0:
            continue
        if not left and mid_u < 0:
            continue
        du = abs(u2 - u1)
        dv = abs(v2 - v1)
        if dv > 1e-6:
            ratios.append(du / dv)
    return sum(ratios) / len(ratios) if ratios else float("nan")


def _ditch_depth(segs: list, left: bool) -> float:
    """Returnerer vertikal dybde (max_v - min_v) for grøftsegmenter på angitt side."""
    vs = []
    for (u1, v1), (u2, v2) in segs:
        for u, v in [(u1, v1), (u2, v2)]:
            if left and u < 0:
                vs.append(v)
            elif not left and u > 0:
                vs.append(v)
    if len(vs) < 2:
        return float("nan")
    return max(vs) - min(vs)


def compute_normal_section(cs: CrossSection) -> NormalSection:
    """Beregn R700-dimensjoner fra et målt tverrprofil."""
    nan = float("nan")
    segs = cs.segments

    cw_cls = "kjørefelt" if "kjørefelt" in segs else "planum"
    cw_segs = segs.get(cw_cls, [])
    sk_segs = segs.get("skulder", [])

    left_cw = _outer_u(cw_segs, left=True)
    right_cw = _outer_u(cw_segs, left=False)
    left_sk = _outer_u(sk_segs, left=True)
    right_sk = _outer_u(sk_segs, left=False)

    def sh_width(sk: float, cw: float) -> float:
        if math.isnan(sk) or math.isnan(cw):
            return nan
        return max(0.0, sk - cw)

    cut_segs = segs.get("skjaering", [])
    fill_segs = segs.get("fylling", [])

    def slope_side(left: bool) -> float:
        r = _slope_ratio(cut_segs, left)
        if math.isnan(r):
            r = _slope_ratio(fill_segs, left)
        return r

    has_cut = bool(cut_segs)
    has_fill = bool(fill_segs)
    if has_cut and has_fill:
        stype = "kombinasjon"
    elif has_cut:
        stype = "skjæring"
    elif has_fill:
        stype = "fylling"
    else:
        stype = "plan"

    return NormalSection(
        station=cs.station,
        elevation=cs.elevation,
        left_carriageway_width=left_cw,
        right_carriageway_width=right_cw,
        left_shoulder_width=sh_width(left_sk, left_cw),
        right_shoulder_width=sh_width(right_sk, right_cw),
        left_ditch_depth=_ditch_depth(segs.get("groft", []), left=True),
        right_ditch_depth=_ditch_depth(segs.get("groft", []), left=False),
        left_slope_ratio=slope_side(left=True),
        right_slope_ratio=slope_side(left=False),
        left_cross_fall_pct=_cross_fall(cw_segs, left=True),
        right_cross_fall_pct=_cross_fall(cw_segs, left=False),
        section_type=stype,
    )
