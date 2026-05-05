# tests/test_tverrprofil_to_agol.py
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest


@pytest.fixture(scope="module", autouse=True)
def setup_arcpy_mock():
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.management.GetCount.return_value = [3]
    arcpy_mock.management.CreateFeatureclass.return_value = ["C:/scratch/test.gdb/test_tverrprofiler"]
    sys.modules.setdefault("arcpy", arcpy_mock)
    sys.modules.setdefault("arcpy.management", arcpy_mock.management)
    sys.modules.setdefault("arcpy.da", arcpy_mock.da)

    arcgis_mock = MagicMock()
    sys.modules.setdefault("arcgis", arcgis_mock)
    sys.modules.setdefault("arcgis.gis", MagicMock())


def _stations_json(tmp: Path) -> Path:
    p = tmp / "stations.json"
    p.write_text(json.dumps([
        {"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0},
        {"station_m": 50.0, "profil_nr": "0050.00", "x": 60.0, "y": 20.0, "z": 101.0},
    ]))
    return p


def test_cli_exits_1_when_stations_json_not_found(capsys):
    from src.arcpy_processor.tverrprofil_to_agol import main
    with pytest.raises(SystemExit) as exc_info:
        main(["--stations-json", "nonexistent.json",
              "--svgs-dir", ".",
              "--name", "Test",
              "--folder", ""])
    assert exc_info.value.code == 1
    err = json.loads(capsys.readouterr().err)
    assert err["code"] == "LANDXML_NOT_FOUND"


def test_cli_prints_json_on_success(tmp_path, capsys):
    stations_path = _stations_json(tmp_path)

    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/test.gdb/test_tverrprofiler"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[2]):

        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "TestTverrprofil",
                  "--folder", "",
                  "--token", "mytoken"])
        assert exc_info.value.code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["status"] == "ok"
    assert out["feature_count"] == 2


def test_create_point_fc_calls_insert_cursor(tmp_path):
    """create_point_fc inserts one row per station."""
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.CreateFeatureclass.reset_mock()

    stations = [
        {"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0},
        {"station_m": 10.0, "profil_nr": "0010.00", "x": 15.0, "y": 20.0, "z": 100.5},
    ]

    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
    create_point_fc(stations, "C:/scratch/test.gdb", "myservice")

    arcpy_mock.management.CreateFeatureclass.assert_called_once()
    insert_cursor_ctx = arcpy_mock.da.InsertCursor.return_value.__enter__.return_value
    assert insert_cursor_ctx.insertRow.call_count == 2


def test_cli_passes_token_to_connect(tmp_path):
    stations_path = _stations_json(tmp_path)
    success_meta = {"status": "ok", "url": "https://x/FeatureServer",
                    "item_id": "i", "item_url": "https://x",
                    "layer_count": 1, "spatial_reference": "x",
                    "published_at": "2026-05-04T10:00:00+00:00"}

    with patch("src.arcpy_processor.auth.connect") as mock_connect, \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/t.gdb/t"), \
         patch("src.arcpy_processor.publisher.upload_and_publish", return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[1]):

        mock_connect.return_value = MagicMock()
        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit):
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "X", "--folder", "",
                  "--token", "tok999", "--org-url", "https://myorg.arcgis.com"])

    mock_connect.assert_called_once_with(token="tok999", org_url="https://myorg.arcgis.com")
