# tests/test_landxml_to_agol.py
from __future__ import annotations
import json
import sys
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(scope="module", autouse=True)
def setup_mocks():
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.management.GetCount.return_value = [1]
    sys.modules.setdefault("arcpy", arcpy_mock)
    sys.modules.setdefault("arcpy.conversion", arcpy_mock.conversion)
    sys.modules.setdefault("arcpy.management", arcpy_mock.management)
    sys.modules.setdefault("arcpy.env", arcpy_mock.env)
    sys.modules.setdefault("arcpy.da", arcpy_mock.da)

    arcgis_mock = MagicMock()
    arcgis_gis_mock = MagicMock()
    arcgis_mock.gis = arcgis_gis_mock
    sys.modules.setdefault("arcgis", arcgis_mock)
    sys.modules.setdefault("arcgis.gis", arcgis_gis_mock)


def test_cli_prints_json_on_success(capsys):
    success_meta = {
        "status": "ok",
        "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc123",
        "item_url": "https://arcgis.com/home/item.html?id=abc123",
        "layer_count": 1,
        "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    # landxml_to_agol delegerer publisering til _polyline_publisher — patch der
    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor._polyline_publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               return_value=({"L530": [(86098.0, 1283548.0, 129.4)]}, 5111)), \
         patch("src.arcpy_processor._polyline_publisher._create_polyline_fc",
               return_value="C:/scratch/publish_temp.gdb/ds_centerline"), \
         patch("src.arcpy_processor._polyline_publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("arcpy.management.GetCount", return_value=[1]):

        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--xml", "test.xml", "--name", "TestLag", "--folder", "SVV",
                  "--features", "L530", "--source-epsg", "5111"])
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert result["source_epsg"] == 5111
    assert result["feature_count"] == 1


def test_cli_exits_1_when_xml_not_found(capsys):
    from src.arcpy_processor.landxml_to_agol import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--xml", "finnes_ikke.xml", "--name", "X", "--folder", "Y"])
    assert exc_info.value.code == 1
    error = json.loads(capsys.readouterr().err)
    assert error["code"] == "LANDXML_NOT_FOUND"


def test_cli_exits_1_on_parse_error(capsys):
    from src.arcpy_processor.errors import ArcpyProcessorError, LANDXML_PARSE_ERROR

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               side_effect=ArcpyProcessorError(LANDXML_PARSE_ERROR, "EPSG mangler")), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--xml", "test.xml", "--name", "X", "--folder", "Y"])
        assert exc_info.value.code == 1

    error = json.loads(capsys.readouterr().err)
    assert error["code"] == LANDXML_PARSE_ERROR


def test_reprojection_called_when_source_differs(capsys):
    """Verify arcpy.management.Project is called when source EPSG != 25833."""
    import sys
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.Project.reset_mock()

    success_meta = {
        "status": "ok",
        "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc123",
        "item_url": "https://arcgis.com/home/item.html?id=abc123",
        "layer_count": 1,
        "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor._polyline_publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               return_value=({"L530": [(86098.0, 1283548.0, 129.4)]}, 5111)), \
         patch("src.arcpy_processor._polyline_publisher._create_polyline_fc",
               return_value="C:/scratch/publish_temp.gdb/ds_centerline"), \
         patch("src.arcpy_processor._polyline_publisher.upload_and_publish",
               return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[1]), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit):
            main(["--xml", "test.xml", "--name", "TestLag", "--folder", "SVV",
                  "--source-epsg", "5111"])

    arcpy_mock.management.Project.assert_called_once()


def test_cli_passes_token_to_connect(capsys):
    """--token arg is forwarded to auth.connect()."""
    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect") as mock_connect, \
         patch("src.arcpy_processor._polyline_publisher.check_name_available"), \
         patch("src.arcpy_processor.landxml_parser.parse_landxml",
               return_value=({"L530": [(86098.0, 1283548.0, 129.4)]}, 25833)), \
         patch("src.arcpy_processor._polyline_publisher._create_polyline_fc",
               return_value="C:/scratch/publish_temp.gdb/ds_centerline"), \
         patch("src.arcpy_processor._polyline_publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("arcpy.management.GetCount", return_value=[1]):

        mock_connect.return_value = MagicMock()
        from src.arcpy_processor.landxml_to_agol import main
        with pytest.raises(SystemExit):
            main(["--xml", "test.xml", "--name", "TestLag", "--folder", "",
                  "--token", "mytoken123", "--org-url", "https://myorg.maps.arcgis.com"])

    mock_connect.assert_called_once_with(token="mytoken123", org_url="https://myorg.maps.arcgis.com")
