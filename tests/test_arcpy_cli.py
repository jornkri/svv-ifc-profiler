# tests/test_arcpy_cli.py
from __future__ import annotations
import json
import sys
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(scope="module", autouse=True)
def setup_mocks():
    """Mock arcpy og arcgis før import av arcpy_processor moduler."""
    # Mock arcpy før import av converter
    arcpy_mock = MagicMock()
    sys.modules.setdefault("arcpy", arcpy_mock)
    sys.modules.setdefault("arcpy.conversion", arcpy_mock.conversion)
    sys.modules.setdefault("arcpy.management", arcpy_mock.management)
    sys.modules.setdefault("arcpy.env", arcpy_mock.env)

    # Mock arcgis før import av publisher
    arcgis_mock = MagicMock()
    arcgis_gis_mock = MagicMock()
    arcgis_mock.gis = arcgis_gis_mock
    sys.modules.setdefault("arcgis", arcgis_mock)
    sys.modules.setdefault("arcgis.gis", arcgis_gis_mock)


def test_cli_exits_1_when_convert_bim_returns_empty(capsys):
    # Verifies the CRITICAL guard: if convert_bim() returns [], the CLI must emit
    # clean JSON (NO_FEATURES) rather than crashing with an unhandled IndexError.
    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim", return_value=[]), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.bim_to_agol import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV"])
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["code"] == "NO_FEATURES"


# bim_to_agol uses lazy imports inside main(), so patching the source module
# attribute is the correct target — the local name is bound at call time, not
# at import time. If imports are ever moved to module level, patch targets
# must change to src.arcpy_processor.bim_to_agol.<name>.
def test_cli_prints_json_on_success(capsys):
    mock_gis = MagicMock()
    success_meta = {
        "status": "ok",
        "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc123",
        "item_url": "https://www.arcgis.com/home/item.html?id=abc123",
        "layer_count": 14,
        "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect", return_value=mock_gis), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim", return_value=["fc1", "fc2"]), \
         patch("src.arcpy_processor.converter.delete_empty_fcs", return_value=["fc1", "fc2"]), \
         patch("src.arcpy_processor.bim_to_agol._gdb_path_from_fcs", return_value="/scratch/bim_temp.gdb"), \
         patch("src.arcpy_processor.publisher.upload_and_publish", return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.bim_to_agol import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV"])
        assert exc_info.value.code == 0

    captured = capsys.readouterr()
    result = json.loads(captured.out)
    assert result["status"] == "ok"
    assert result["item_id"] == "abc123"


def test_cli_exits_1_and_prints_error_json_on_failure(capsys):
    from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available",
               side_effect=ArcpyProcessorError(NAME_EXISTS, "Navn finnes allerede")), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.bim_to_agol import main

        with pytest.raises(SystemExit) as exc_info:
            main(["--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV"])
        assert exc_info.value.code == 1

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["status"] == "error"
    assert error["code"] == NAME_EXISTS


def test_cli_exits_1_when_ifc_not_found(capsys):
    with pytest.raises(SystemExit) as exc_info:
        from src.arcpy_processor.bim_to_agol import main
        main(["--ifc", "finnes_ikke.ifc", "--name", "X", "--folder", "Y"])
    assert exc_info.value.code == 1

    captured = capsys.readouterr()
    error = json.loads(captured.err)
    assert error["code"] == "IFC_NOT_FOUND"


def test_cli_passes_token_and_org_url_to_connect(capsys):
    mock_gis = MagicMock()
    success_meta = {"status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer"}

    with patch("src.arcpy_processor.auth.connect", return_value=mock_gis) as mock_connect, \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim", return_value=["fc1"]), \
         patch("src.arcpy_processor.converter.delete_empty_fcs", return_value=["fc1"]), \
         patch("src.arcpy_processor.bim_to_agol._gdb_path_from_fcs",
               return_value="/scratch/bim_temp.gdb"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("pathlib.Path.exists", return_value=True):

        from src.arcpy_processor.bim_to_agol import main

        with pytest.raises(SystemExit) as exc_info:
            main([
                "--ifc", "test.ifc", "--name", "TestLag", "--folder", "SVV",
                "--token", "mytoken123",
                "--org-url", "https://myorg.maps.arcgis.com",
            ])
        assert exc_info.value.code == 0

    mock_connect.assert_called_once_with(
        token="mytoken123",
        org_url="https://myorg.maps.arcgis.com",
    )
