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

SAMPLES = Path(__file__).parent.parent / "samples"
CL_12200 = SAMPLES / "m_f-veg_12200_CL.ifc"
VEG_12200 = SAMPLES / "m_f_veg_12200_Veg.ifc"          # vegmodell, ikke alignment
KLEVERUD = SAMPLES / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"  # IFC2X3 — feil schema


def test_load_12200_returns_alignment_data():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert data.name == "12150"


def test_ifc4_schema_rejected():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    if not KLEVERUD.exists():
        pytest.skip("IFC4-eksempel ikke tilgjengelig")
    with pytest.raises(ValueError, match="IFC4X3"):
        load_alignment_from_ifc(KLEVERUD)


def test_missing_alignment_raises():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    with pytest.raises(ValueError, match="IfcAlignment"):
        load_alignment_from_ifc(VEG_12200)


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
