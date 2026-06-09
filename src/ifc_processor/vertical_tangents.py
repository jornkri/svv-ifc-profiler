"""Reduser vertikalgeometri til konstant-fall-strekk (tangenter) for R700-påskrift.

Kilde-agnostisk: tar enten IFC-VerticalSegment-liste (foretrukket, eksakt gradient)
eller en PVI-liste [(stasjon, høyde)] (LandXML, eller IFC-fallback uten
CONSTANTGRADIENT-segmenter). Returnerer [{sta_start, sta_end, gradient_pct}] med
gradient i prosent, avrundet til 1 desimal (R700-presisjon).
"""
from __future__ import annotations

from .alignment_parser import VerticalSegment


def _from_constantgradient(segments: list[VerticalSegment]) -> list[dict]:
    rows: list[dict] = []
    for seg in segments:
        if seg.segment_type != "CONSTANTGRADIENT":
            continue
        rows.append({
            "sta_start": round(seg.start_station, 3),
            "sta_end": round(seg.start_station + seg.length, 3),
            "gradient_pct": round(seg.start_gradient * 100, 1),
        })
    return rows


def _from_pvi(pvi: list[tuple[float, float]]) -> list[dict]:
    rows: list[dict] = []
    for (s0, z0), (s1, z1) in zip(pvi, pvi[1:]):
        ds = s1 - s0
        if ds <= 1e-6:
            continue
        rows.append({
            "sta_start": round(s0, 3),
            "sta_end": round(s1, 3),
            "gradient_pct": round((z1 - z0) / ds * 100, 1),
        })
    return rows


def constant_grade_tangents(
    *,
    vertical_segments: list[VerticalSegment],
    pvi: list[tuple[float, float]],
) -> list[dict]:
    """Bygg liste konstant-fall-strekk.

    Prioritet:
      1. IFC CONSTANTGRADIENT-segmenter (eksakt gradient).
      2. Hvis ingen slike finnes: PVI-utledning (LandXML, eller IFC uten tangent-segmenter).
    """
    rows = _from_constantgradient(vertical_segments)
    if rows:
        return rows
    return _from_pvi(pvi)
