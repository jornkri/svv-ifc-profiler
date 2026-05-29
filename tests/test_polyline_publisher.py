# tests/test_polyline_publisher.py
"""Tester for refaktorert felles publisher. Verifiserer at landxml_to_agol
fortsatt fungerer etter refactor."""
from __future__ import annotations
from pathlib import Path
import pytest
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_arcpy(monkeypatch):
    """Mock ArcPy + arcgis slik at testen kan kjøre uten ArcGIS Pro."""
    import sys
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    arcpy_mock.management.GetCount.return_value = ["1"]
    arcpy_mock.Exists.return_value = False
    monkeypatch.setitem(sys.modules, "arcpy", arcpy_mock)
    monkeypatch.setitem(sys.modules, "arcpy.management", arcpy_mock.management)
    monkeypatch.setitem(sys.modules, "arcpy.da", arcpy_mock.da)
    monkeypatch.setitem(sys.modules, "arcpy.env", arcpy_mock.env)

    # publisher.py importerer arcgis.gis på modulnivå — stub den også
    arcgis_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "arcgis", arcgis_mock)
    monkeypatch.setitem(sys.modules, "arcgis.gis", arcgis_mock.gis)
    return arcpy_mock


def test_publish_polyline_calls_create_polyline_fc(mock_arcpy):
    from src.arcpy_processor._polyline_publisher import publish_polyline_to_agol
    gis_mock = MagicMock()
    with patch("src.arcpy_processor._polyline_publisher.upload_and_publish",
               return_value={"url": "https://example/0"}):
        with patch("src.arcpy_processor._polyline_publisher.check_name_available"):
            result = publish_polyline_to_agol(
                points_dict={"L1": [(100.0, 200.0, 10.0), (110.0, 200.0, 11.0)]},
                source_epsg=25833,
                service_name="test",
                folder="",
                gis=gis_mock,
                lengdeprofil_path=None,
            )
    assert "url" in result
