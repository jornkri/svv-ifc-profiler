# tests/test_alignment_parser.py
from __future__ import annotations
from pathlib import Path
import numpy as np
import pytest

from src.ifc_processor.alignment_parser import (
    HorizontalSegment,
    VerticalSegment,
    StationLabel,
    IfcAlignmentData,
)


def test_dataclasses_constructible():
    hs = HorizontalSegment(
        start_station=0.0,
        length=10.0,
        start_point=(100.0, 200.0),
        start_direction=0.0,
        segment_type="LINE",
    )
    assert hs.start_radius is None
    assert hs.is_ccw is None

    vs = VerticalSegment(
        start_station=0.0,
        length=10.0,
        start_height=50.0,
        start_gradient=0.01,
        segment_type="CONSTANTGRADIENT",
    )
    assert vs.radius is None

    sl = StationLabel(station=100.0, name="P 100", position=(100.0, 200.0, 50.0))
    assert sl.name == "P 100"

    data = IfcAlignmentData(
        name="test",
        points_3d=np.array([[0.0, 0.0, 0.0], [10.0, 0.0, 1.0]]),
        stations=np.array([0.0, 10.0]),
        horizontal_segments=[hs],
        vertical_segments=[vs],
        station_labels=[sl],
    )
    assert data.source_epsg == 25833
    assert data.name == "test"
