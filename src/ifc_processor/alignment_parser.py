# src/ifc_processor/alignment_parser.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class HorizontalSegment:
    start_station: float
    length: float
    start_point: tuple[float, float]
    start_direction: float                 # radianer
    segment_type: str                      # "LINE" | "CIRCULARARC" | "CLOTHOID"
    start_radius: float | None = None
    end_radius: float | None = None
    is_ccw: bool | None = None


@dataclass
class VerticalSegment:
    start_station: float
    length: float
    start_height: float
    start_gradient: float                  # m/m
    segment_type: str                      # "CONSTANTGRADIENT" | "PARABOLICARC" | "CIRCULARARC"
    radius: float | None = None            # signert: + dal, − topp


@dataclass
class StationLabel:
    station: float
    name: str
    position: tuple[float, float, float]


@dataclass
class IfcAlignmentData:
    name: str
    points_3d: np.ndarray                  # (M, 3)
    stations: np.ndarray                   # (M,)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    vertical_segments: list[VerticalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833


# ---------------------------------------------------------------------------
# IFC loading helpers
# ---------------------------------------------------------------------------

_VALID_SCHEMAS = {"IFC4X3", "IFC4X3_ADD1", "IFC4X3_ADD2", "IFC4X3_TC1"}


def _find_horizontal(alignment):
    """Return the IfcAlignmentHorizontal nested under *alignment*, or None."""
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentHorizontal"):
                return obj
    return None


def _find_vertical(alignment):
    """Return the IfcAlignmentVertical nested under *alignment*, or None."""
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentVertical"):
                return obj
    return None


def _select_alignment(ifc):
    """Pick the single IfcAlignment in *ifc*, or the longest if multiple exist.

    Raises ValueError if none are found.
    """
    alignments = ifc.by_type("IfcAlignment")
    if not alignments:
        types = sorted({e.is_a() for e in ifc})
        raise ValueError(
            f"Ingen IfcAlignment funnet — er dette en vegmodell-IFC? "
            f"Topp-typer i filen: {types[:10]}{'...' if len(types) > 10 else ''}"
        )
    if len(alignments) == 1:
        return alignments[0]

    def total_len(al):
        h = _find_horizontal(al)
        if h is None:
            return 0.0
        return sum(
            (seg.DesignParameters.SegmentLength or 0.0)
            for rel in h.IsNestedBy
            for seg in rel.RelatedObjects
            if seg.is_a("IfcAlignmentSegment") and seg.DesignParameters is not None
        )

    chosen = max(alignments, key=total_len)
    logger.info(
        "Flere IfcAlignment i fil — valgte '%s'. Andre: %s",
        chosen.Name,
        [a.Name for a in alignments if a is not chosen],
    )
    return chosen


def load_alignment_from_ifc(ifc_path: Path) -> IfcAlignmentData:
    """Les IFC4X3 IfcAlignment og returner felles datakontrakt.

    Raises:
        ValueError: filen er ikke IFC4X3, mangler IfcAlignment, eller alignment er tom.
    """
    ifc = ifcopenshell.open(str(ifc_path))
    if ifc.schema not in _VALID_SCHEMAS:
        raise ValueError(
            f"IFC4X3 kreves for senterlinje-IFC. Fil-schema: {ifc.schema}. "
            "Bruk LandXML-senterlinje for IFC4-modeller."
        )

    alignment = _select_alignment(ifc)
    name = alignment.Name or "<ukjent>"

    return IfcAlignmentData(
        name=name,
        points_3d=np.zeros((0, 3)),
        stations=np.zeros(0),
    )
