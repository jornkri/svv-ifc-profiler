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


def test_horizontal_segments_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.horizontal_segments) == 67
    starts = [s.start_station for s in data.horizontal_segments]
    assert starts == sorted(starts)
    assert starts[0] == 0.0


def test_horizontal_segment_types_present():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    types = {s.segment_type for s in data.horizontal_segments}
    assert "LINE" in types
    assert types <= {"LINE", "CIRCULARARC", "CLOTHOID"}


def test_circular_arc_has_radius():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    arcs = [s for s in data.horizontal_segments if s.segment_type == "CIRCULARARC"]
    if arcs:
        assert arcs[0].start_radius is not None
        assert arcs[0].start_radius > 0
        assert arcs[0].is_ccw in (True, False)


def test_vertical_segments_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.vertical_segments) == 50
    starts = [s.start_station for s in data.vertical_segments]
    assert starts == sorted(starts)


def test_vertical_segment_types():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    types = {s.segment_type for s in data.vertical_segments}
    assert types <= {"CONSTANTGRADIENT", "PARABOLICARC", "CIRCULARARC"}
    assert "CONSTANTGRADIENT" in types


def test_parabolic_radius_signed():
    """Parabel som krummer ned (topp) → negativ radius; krummer opp (dal) → positiv."""
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    parabols = [s for s in data.vertical_segments if s.segment_type == "PARABOLICARC"]
    if parabols:
        for p in parabols:
            assert p.radius is not None
            assert p.radius != 0.0


def test_points_3d_sampled():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert data.points_3d.shape[0] >= 100
    assert data.points_3d.shape[1] == 3
    assert data.stations.shape[0] == data.points_3d.shape[0]
    # Z-verdier er meningsfulle (ikke alle 0)
    assert np.abs(data.points_3d[:, 2]).max() > 1.0
    # Stasjonene er monotone
    assert np.all(np.diff(data.stations) >= 0)


def test_total_length_matches_horizontal_sum():
    """Total samplet lengde skal være ~lik sum av horisontalsegmenter."""
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    sum_h = sum(s.length for s in data.horizontal_segments)
    sampled_len = float(data.stations[-1])
    assert abs(sampled_len - sum_h) < 5.0


def test_station_labels_extracted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    assert len(data.station_labels) > 50  # 12200 har 99 referenter
    sl = data.station_labels[0]
    assert sl.name != ""
    assert sl.station >= 0.0


def test_station_labels_sorted():
    from src.ifc_processor.alignment_parser import load_alignment_from_ifc
    data = load_alignment_from_ifc(CL_12200)
    stations = [sl.station for sl in data.station_labels]
    assert stations == sorted(stations)
