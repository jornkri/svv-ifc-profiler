# tests/test_bim_to_agol.py
from __future__ import annotations
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SAMPLE = Path(__file__).parent.parent / "samples" / "m_f_veg_12200_Veg.ifc"


def test_main_classifies_and_publishes_two_layers(monkeypatch):
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-sample mangler")

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

    from src.arcpy_processor import bim_to_agol

    with patch.object(bim_to_agol, "connect", return_value=MagicMock()), \
         patch("src.arcpy_processor.publisher.check_name_available"), \
         patch("src.arcpy_processor.converter.convert_bim",
               return_value=["/s/bim_temp.gdb/ds/Courses"]) as m_conv, \
         patch("src.arcpy_processor.converter.merge_and_categorize",
               return_value="/s/bim_out.gdb") as m_cat, \
         patch("src.arcpy_processor.publisher.upload_and_publish",
               return_value={"status": "ok", "layer_count": 2}) as m_pub:
        with pytest.raises(SystemExit) as exc:
            bim_to_agol.main([
                "--ifc", str(SAMPLE), "--name", "svc", "--folder", "",
            ])
        assert exc.value.code == 0

    m_conv.assert_called_once()
    m_cat.assert_called_once()
    # publiserer GDB-en fra merge_and_categorize, ikke kilde-GDB
    assert m_pub.call_args.args[1] == "/s/bim_out.gdb"
