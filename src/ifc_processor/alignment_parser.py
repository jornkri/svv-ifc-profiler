# src/ifc_processor/alignment_parser.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

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
