from __future__ import annotations

from src.ifc_processor.alignment_parser import VerticalSegment
from src.ifc_processor.vertical_tangents import constant_grade_tangents


def test_ifc_segments_only_constantgradient():
    """Rene CONSTANTGRADIENT-tangenter → én rad per segment, gradient i prosent, 1 desimal."""
    segs = [
        VerticalSegment(0.0, 240.0, 100.0, 0.025, "CONSTANTGRADIENT"),
        VerticalSegment(240.0, 40.0, 106.0, 0.0, "PARABOLICARC", radius=2000.0),
        VerticalSegment(280.0, 230.0, 106.0, -0.018, "CONSTANTGRADIENT"),
    ]
    out = constant_grade_tangents(vertical_segments=segs, pvi=[])
    assert out == [
        {"sta_start": 0.0, "sta_end": 240.0, "gradient_pct": 2.5},
        {"sta_start": 280.0, "sta_end": 510.0, "gradient_pct": -1.8},
    ]


def test_ifc_fallback_to_pvi_when_no_constantgradient():
    """Modell uten CONSTANTGRADIENT-segmenter faller tilbake til PVI-utledning."""
    segs = [
        VerticalSegment(0.0, 100.0, 50.0, 0.02, "PARABOLICARC", radius=1500.0),
    ]
    pvi = [(0.0, 50.0), (100.0, 52.0), (300.0, 48.0)]
    out = constant_grade_tangents(vertical_segments=segs, pvi=pvi)
    assert out == [
        {"sta_start": 0.0, "sta_end": 100.0, "gradient_pct": 2.0},
        {"sta_start": 100.0, "sta_end": 300.0, "gradient_pct": -2.0},
    ]


def test_landxml_pvi_only():
    """Tom vertical_segments + PVI-liste (LandXML) → fall mellom nabo-PVI-er."""
    pvi = [(0.0, 100.0), (240.0, 106.0), (510.0, 101.16)]
    out = constant_grade_tangents(vertical_segments=[], pvi=pvi)
    assert out == [
        {"sta_start": 0.0, "sta_end": 240.0, "gradient_pct": 2.5},
        {"sta_start": 240.0, "sta_end": 510.0, "gradient_pct": -1.8},
    ]


def test_empty_inputs_give_empty_list():
    assert constant_grade_tangents(vertical_segments=[], pvi=[]) == []


def test_pvi_single_point_gives_empty_list():
    assert constant_grade_tangents(vertical_segments=[], pvi=[(0.0, 100.0)]) == []


def test_zero_length_pvi_segment_skipped():
    """Degenerert PVI-par (samme stasjon) hoppes over uten å dele på null."""
    pvi = [(0.0, 100.0), (0.0, 100.0), (200.0, 96.0)]
    out = constant_grade_tangents(vertical_segments=[], pvi=pvi)
    assert out == [{"sta_start": 0.0, "sta_end": 200.0, "gradient_pct": -2.0}]
