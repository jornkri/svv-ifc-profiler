# tests/test_landxml_parser.py
from __future__ import annotations
from pathlib import Path
import pytest
from src.arcpy_processor.errors import ArcpyProcessorError, LANDXML_PARSE_ERROR
from src.arcpy_processor.landxml_parser import parse_landxml, parse_horizontal_alignment

SAMPLE = Path(__file__).parent.parent / "samples" / "FV229_Senterlinje.xml"
SAMPLE_ALIGNMENT = Path(__file__).parent.parent / "samples" / "m_f_veg_70400_aligment.xml"


def test_parses_epsg_from_file():
    _, epsg = parse_landxml(SAMPLE)
    assert epsg == 5111


def test_northing_easting_swap():
    points_dict, _ = parse_landxml(SAMPLE)
    name = next(iter(points_dict))
    first_pt = points_dict[name][0]
    assert first_pt[0] == pytest.approx(86098.615097)
    assert first_pt[1] == pytest.approx(1283548.213623)
    assert first_pt[2] == pytest.approx(129.432205)


def test_features_filter():
    points_dict, _ = parse_landxml(SAMPLE, features=["L530"])
    assert list(points_dict.keys()) == ["L530"]
    assert len(points_dict["L530"]) >= 2


def test_raises_for_unknown_feature():
    with pytest.raises(ArcpyProcessorError) as exc_info:
        parse_landxml(SAMPLE, features=["FINNESIKKE"])
    assert exc_info.value.code == LANDXML_PARSE_ERROR


def test_raises_when_epsg_missing_and_no_override(tmp_path):
    xml = tmp_path / "no_epsg.xml"
    xml.write_text(
        '<?xml version="1.0"?>\n'
        '<LandXML>\n'
        '  <CoordinateSystem/>\n'
        '  <PlanFeatures>\n'
        '    <PlanFeature name="A">\n'
        '      <CoordGeom>\n'
        '        <Line><Start>100.0 200.0 10.0</Start><End>101.0 201.0 11.0</End></Line>\n'
        '      </CoordGeom>\n'
        '    </PlanFeature>\n'
        '  </PlanFeatures>\n'
        '</LandXML>\n'
    )
    with pytest.raises(ArcpyProcessorError) as exc_info:
        parse_landxml(xml)
    assert exc_info.value.code == LANDXML_PARSE_ERROR


def test_parses_curve_line_segments_from_alignment():
    """parse_horizontal_alignment skal lese ut Curve+Line-segmenter fra Quadri-format."""
    segments = parse_horizontal_alignment(SAMPLE_ALIGNMENT)
    # Sample har: Curve, Line, Curve, Line, Curve, Line = 6 segmenter
    assert len(segments) == 6

    # Første Curve: radius=50, rot=cw (høyrekurve), staStart=0
    s0 = segments[0]
    assert s0["kind"] == "curve"
    assert s0["sta_start"] == pytest.approx(0.0)
    assert s0["sta_end"] == pytest.approx(12.768460)
    assert s0["radius"] == pytest.approx(50.0)
    assert s0["dir"] == -1  # cw = høyre

    # Andre segment: Line
    s1 = segments[1]
    assert s1["kind"] == "line"
    assert s1["sta_start"] == pytest.approx(12.768460)
    assert s1["sta_end"] == pytest.approx(57.540816)
    assert "radius" not in s1

    # Tredje: Curve venstre (rot=ccw → dir=+1)
    s2 = segments[2]
    assert s2["kind"] == "curve"
    assert s2["radius"] == pytest.approx(25.0)
    assert s2["dir"] == +1


def test_returns_empty_for_planfeature_only_file():
    """FV229_Senterlinje.xml har bare PlanFeatures, ingen Alignment — skal returnere []."""
    segments = parse_horizontal_alignment(SAMPLE)
    assert segments == []


def test_source_epsg_override(tmp_path):
    xml = tmp_path / "no_epsg.xml"
    xml.write_text(
        '<?xml version="1.0"?>\n'
        '<LandXML>\n'
        '  <CoordinateSystem/>\n'
        '  <PlanFeatures>\n'
        '    <PlanFeature name="A">\n'
        '      <CoordGeom>\n'
        '        <Line><Start>100.0 200.0 10.0</Start><End>101.0 201.0 11.0</End></Line>\n'
        '      </CoordGeom>\n'
        '    </PlanFeature>\n'
        '  </PlanFeatures>\n'
        '</LandXML>\n'
    )
    points_dict, epsg = parse_landxml(xml, source_epsg=25833)
    assert epsg == 25833
    assert "A" in points_dict
    assert len(points_dict["A"]) == 2
