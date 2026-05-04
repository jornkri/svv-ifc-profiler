# tests/test_landxml_parser.py
from __future__ import annotations
from pathlib import Path
import pytest
from src.arcpy_processor.errors import ArcpyProcessorError, LANDXML_PARSE_ERROR
from src.arcpy_processor.landxml_parser import parse_landxml

SAMPLE = Path(__file__).parent.parent / "samples" / "FV229_Senterlinje.xml"


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
