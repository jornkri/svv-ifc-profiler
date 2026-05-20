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
    sys.modules.setdefault("arcgis.features", MagicMock())


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
    create_point_fc(stations, "C:/scratch/test.gdb", "myservice", source_epsg=25833)

    arcpy_mock.management.CreateFeatureclass.assert_called_once()
    insert_cursor_ctx = arcpy_mock.da.InsertCursor.return_value.__enter__.return_value
    assert insert_cursor_ctx.insertRow.call_count == 2


def test_create_point_fc_reprojects_to_25833_when_source_epsg_5111():
    """create_point_fc skal reprosjektere fra source_epsg til EPSG:25833 med pyproj."""
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.Point.reset_mock()

    stations = [{"station_m": 0.0, "profil_nr": "0000.00", "x": 86098.615, "y": 1283548.214, "z": 129.432}]

    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
    create_point_fc(stations, "C:/scratch/test.gdb", "myservice", source_epsg=5111)

    call_args = arcpy_mock.Point.call_args_list[0][0]
    x_arg, y_arg = call_args[0], call_args[1]
    # EPSG:5111 (E=86098.615, N=1283548.214) -> EPSG:25833 (E≈294178, N≈6717991)
    assert abs(x_arg - 294178) < 10, f"X feil: {x_arg} (forventet ~294178 i EPSG:25833)"
    assert abs(y_arg - 6717991) < 10, f"Y feil: {y_arg} (forventet ~6717991 i EPSG:25833)"


def test_create_point_fc_no_reprojection_when_source_is_25833():
    """create_point_fc skal ikke reprosjektere når source_epsg allerede er 25833."""
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.Point.reset_mock()

    stations = [{"station_m": 0.0, "profil_nr": "0000.00", "x": 294178.0, "y": 6717991.0, "z": 129.0}]

    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
    create_point_fc(stations, "C:/scratch/test.gdb", "myservice", source_epsg=25833)

    call_args = arcpy_mock.Point.call_args_list[0][0]
    x_arg, y_arg = call_args[0], call_args[1]
    assert abs(x_arg - 294178.0) < 0.01
    assert abs(y_arg - 6717991.0) < 0.01


def test_cli_no_arcpy_project_when_source_epsg_differs(tmp_path, capsys):
    """main() skal IKKE kalle arcpy.management.Project — reprosjeksjon skjer i Python."""
    stations_path = _stations_json(tmp_path)
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.Project.reset_mock()

    success_meta = {"status": "ok", "url": "https://x/FeatureServer",
                    "item_id": "i", "item_url": "https://x",
                    "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
                    "published_at": "2026-05-04T10:00:00+00:00"}

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/t.gdb/t_tverrprofiler"), \
         patch("src.arcpy_processor.publisher.upload_and_publish", return_value=success_meta), \
         patch("arcpy.management.GetCount", return_value=[2]), \
         patch("arcpy.Exists", return_value=False), \
         patch("arcpy.management.Delete"), \
         patch("arcpy.management.CreateFileGDB"):

        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "Test", "--folder", "",
                  "--source-epsg", "5111"])
        assert exc_info.value.code == 0

    arcpy_mock.management.Project.assert_not_called()


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


def test_create_point_fc_adds_svg_url_field():
    """create_point_fc must add a svg_url field so AGOL can store attachment URLs."""
    arcpy_mock = sys.modules["arcpy"]
    arcpy_mock.management.AddField.reset_mock()

    stations = [{"station_m": 0.0, "profil_nr": "0000.00", "x": 10.0, "y": 20.0, "z": 100.0}]

    arcpy_mock.da.InsertCursor.return_value.__enter__ = lambda s: s
    arcpy_mock.da.InsertCursor.return_value.__exit__ = MagicMock(return_value=False)
    arcpy_mock.da.InsertCursor.return_value.__iter__ = MagicMock(return_value=iter([]))
    arcpy_mock.da.SearchCursor.return_value.__enter__ = lambda s: s
    arcpy_mock.da.SearchCursor.return_value.__exit__ = MagicMock(return_value=False)
    arcpy_mock.da.SearchCursor.return_value.__iter__ = MagicMock(return_value=iter([]))

    from src.arcpy_processor.tverrprofil_to_agol import create_point_fc
    create_point_fc(stations, "C:/scratch/test.gdb", "vei")

    field_names = [
        call_args[0][1]
        for call_args in arcpy_mock.management.AddField.call_args_list
    ]
    assert "svg_url" in field_names, f"svg_url not in AddField calls: {field_names}"


def test_two_attachments_per_station(tmp_path):
    """Match-tabellen skal ha to rader per OID: tverrprofil og normalprofil."""
    stations_path = tmp_path / "stations.json"
    stations_path.write_text(json.dumps([
        {"station_m": 10.0, "profil_nr": "0010.00", "x": 100.0, "y": 200.0, "z": 50.0}
    ]))

    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    tp_svg = svgs_dir / "tverrprofil_00010.0.svg"
    np_svg = svgs_dir / "normalprofil_00010.0.svg"
    tp_svg.write_text("<svg/>")
    np_svg.write_text("<svg/>")

    inserted_rows: list = []

    arcpy_mock = sys.modules["arcpy"]

    # InsertCursor context manager that records insertRow calls
    ins_ctx = MagicMock()
    ins_ctx.insertRow = lambda row: inserted_rows.append(row)
    ins_cm = MagicMock()
    ins_cm.__enter__ = lambda s: ins_ctx
    ins_cm.__exit__ = MagicMock(return_value=False)

    # SearchCursor context manager that yields one (OID, station_m) pair
    search_ctx = iter([(1, 10.0)])
    search_cm = MagicMock()
    search_cm.__enter__ = lambda s: search_ctx
    search_cm.__exit__ = MagicMock(return_value=False)

    arcpy_mock.da.SearchCursor.return_value = search_cm
    arcpy_mock.da.InsertCursor.return_value = ins_cm

    success_meta = {
        "status": "ok", "url": "https://x/FeatureServer",
        "item_id": "i", "item_url": "https://x",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    with patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/t.gdb/t_tverrprofiler"), \
         patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta):

        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main([
                "--stations-json", str(stations_path),
                "--svgs-dir", str(svgs_dir),
                "--name", "test_profiler",
                "--folder", "",
            ])
        assert exc_info.value.code == 0

    svg_rows = [r for r in inserted_rows if isinstance(r, tuple) and len(r) == 2]
    assert len(svg_rows) == 2, f"Forventet 2 vedlegg, fikk {len(svg_rows)}: {svg_rows}"
    paths = [r[1] for r in svg_rows]
    assert any("tverrprofil" in p for p in paths)
    assert any("normalprofil" in p for p in paths)


def test_cli_calls_backfill_svg_urls_after_publish(tmp_path, capsys):
    stations_path = _stations_json(tmp_path)

    success_meta = {
        "status": "ok", "url": "https://services.arcgis.com/xxx/FeatureServer",
        "item_id": "abc", "item_url": "https://arcgis.com/home/item.html?id=abc",
        "layer_count": 1, "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
        "published_at": "2026-05-04T10:00:00+00:00",
    }

    mock_backfill = MagicMock(return_value=2)

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.create_point_fc",
               return_value="C:/scratch/test.gdb/test_tverrprofiler"), \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value=success_meta), \
         patch("src.arcpy_processor.experience_builder.backfill_svg_urls",
               mock_backfill):
        from src.arcpy_processor.tverrprofil_to_agol import main
        with pytest.raises(SystemExit) as exc_info:
            main(["--stations-json", str(stations_path),
                  "--svgs-dir", str(tmp_path),
                  "--name", "Test",
                  "--folder", "",
                  "--token", "tok123"])
        assert exc_info.value.code == 0

    mock_backfill.assert_called_once()
