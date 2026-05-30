# tests/test_bim_to_agol.py
from __future__ import annotations
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SAMPLE = Path(__file__).parent.parent / "samples" / "m_f_veg_12200_Veg.ifc"


def _stub_arcpy_arcgis(monkeypatch):
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    monkeypatch.setitem(sys.modules, "arcpy", arcpy_mock)
    monkeypatch.setitem(sys.modules, "arcpy.management", arcpy_mock.management)
    monkeypatch.setitem(sys.modules, "arcpy.da", arcpy_mock.da)
    monkeypatch.setitem(sys.modules, "arcpy.ddd", arcpy_mock.ddd)
    monkeypatch.setitem(sys.modules, "arcpy.env", arcpy_mock.env)
    arcgis_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "arcgis", arcgis_mock)
    monkeypatch.setitem(sys.modules, "arcgis.gis", arcgis_mock.gis)


@pytest.mark.slow
def test_main_publishes_3d_and_plan_as_separate_services(monkeypatch, capsys):
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")
    _stub_arcpy_arcgis(monkeypatch)

    from src.arcpy_processor import bim_to_agol

    def _upload(gis, gdb_path, name, folder, *, target_sr=25833):
        # Returner ulik metadata per GDB så vi kan skille 3D fra plan
        if gdb_path.endswith("bim_3d.gdb"):
            return {"status": "ok", "url": "https://x/3D/FeatureServer",
                    "item_id": "fl3d", "layer_count": 1}
        return {"status": "ok", "url": "https://x/PLAN/FeatureServer",
                "item_id": "flplan", "layer_count": 1}

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available") as m_chk, \
         patch("src.arcpy_processor.converter.convert_bim",
               return_value=["/s/bim_temp.gdb/ds/Courses"]) as m_conv, \
         patch("src.arcpy_processor.converter.merge_and_categorize",
               return_value=("/s/bim_3d.gdb", "/s/bim_plan.gdb")) as m_cat, \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               side_effect=_upload) as m_pub, \
         patch("src.arcpy_processor.publisher.publish_3d_object_layer",
               return_value={"scene_url": "https://x/SceneServer",
                             "scene_item_id": "scene1"}) as m_scene:
        with pytest.raises(SystemExit) as exc:
            bim_to_agol.main(["--ifc", str(SAMPLE), "--name", "svc", "--folder", ""])
        assert exc.value.code == 0

    m_conv.assert_called_once()
    m_cat.assert_called_once()
    # To separate publiseringer: bim_3d.gdb og bim_plan.gdb
    published_gdbs = {c.args[1] for c in m_pub.call_args_list}
    assert published_gdbs == {"/s/bim_3d.gdb", "/s/bim_plan.gdb"}
    # 3D-laget MÅ publiseres med target_sr=None (bevarer multipatch);
    # plan-laget reprosjekteres som normalt (default).
    by_gdb = {c.args[1]: c for c in m_pub.call_args_list}
    assert by_gdb["/s/bim_3d.gdb"].kwargs.get("target_sr") is None
    assert "target_sr" not in by_gdb["/s/bim_plan.gdb"].kwargs
    # 3D-feature-laget ble brukt som kilde for scene-publisering
    m_scene.assert_called_once()
    # Navn sjekket for både 3D-tjeneste og plan-tjeneste
    checked_names = {c.args[1] for c in m_chk.call_args_list}
    assert "svc" in checked_names and "svc_plan" in checked_names

    out = json.loads(capsys.readouterr().out)
    assert out["url"] == "https://x/SceneServer"          # scene foretrekkes
    assert out["bim_3d_url"] == "https://x/3D/FeatureServer"
    assert out["bim_scene_url"] == "https://x/SceneServer"
    assert out["bim_plan_url"] == "https://x/PLAN/FeatureServer"


@pytest.mark.slow
def test_main_degrades_when_scene_publish_fails(monkeypatch, capsys):
    """Scene-publisering feiler (None) → url faller tilbake til 3D-feature-laget."""
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")
    _stub_arcpy_arcgis(monkeypatch)

    from src.arcpy_processor import bim_to_agol

    def _upload(gis, gdb_path, name, folder, *, target_sr=25833):
        if gdb_path.endswith("bim_3d.gdb"):
            return {"status": "ok", "url": "https://x/3D/FeatureServer",
                    "item_id": "fl3d", "layer_count": 1}
        return {"status": "ok", "url": "https://x/PLAN/FeatureServer",
                "item_id": "flplan", "layer_count": 1}

    with patch("src.arcpy_processor.auth.connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim",
               return_value=["/s/bim_temp.gdb/ds/Courses"]), \
         patch("src.arcpy_processor.converter.merge_and_categorize",
               return_value=("/s/bim_3d.gdb", "/s/bim_plan.gdb")), \
         patch("src.arcpy_processor.publisher.upload_and_publish", side_effect=_upload), \
         patch("src.arcpy_processor.publisher.publish_3d_object_layer",
               return_value=None):
        with pytest.raises(SystemExit) as exc:
            bim_to_agol.main(["--ifc", str(SAMPLE), "--name", "svc", "--folder", ""])
        assert exc.value.code == 0

    out = json.loads(capsys.readouterr().out)
    assert out["url"] == "https://x/3D/FeatureServer"     # fallback
    assert out["bim_scene_url"] is None
