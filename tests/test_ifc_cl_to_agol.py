# tests/test_ifc_cl_to_agol.py
from __future__ import annotations
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


SAMPLE = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"


def test_cli_parses_ifc_cl_and_calls_publisher(monkeypatch, capsys):
    """Verifiser at CLI leser IFC-CL og kaller publish_polyline_to_agol med riktige args."""
    if not SAMPLE.exists():
        pytest.skip("12200 IFC-CL-fixture mangler")

    import sys
    arcpy_mock = MagicMock()
    arcpy_mock.env.scratchFolder = "/tmp/scratch"
    arcpy_mock.management.GetCount.return_value = ["1"]
    arcpy_mock.Exists.return_value = False
    monkeypatch.setitem(sys.modules, "arcpy", arcpy_mock)
    monkeypatch.setitem(sys.modules, "arcpy.management", arcpy_mock.management)
    monkeypatch.setitem(sys.modules, "arcpy.da", arcpy_mock.da)
    monkeypatch.setitem(sys.modules, "arcpy.env", arcpy_mock.env)
    # publisher.py importerer arcgis.gis på modulnivå — stub
    arcgis_mock = MagicMock()
    monkeypatch.setitem(sys.modules, "arcgis", arcgis_mock)
    monkeypatch.setitem(sys.modules, "arcgis.gis", arcgis_mock.gis)

    with patch("src.arcpy_processor.ifc_cl_to_agol.connect") as mock_connect, \
         patch("src.arcpy_processor.ifc_cl_to_agol.publish_polyline_to_agol",
               return_value={"url": "https://x/0"}) as mock_publish:
        mock_connect.return_value = MagicMock()
        from src.arcpy_processor import ifc_cl_to_agol
        with pytest.raises(SystemExit) as exc_info:
            ifc_cl_to_agol.main([
                "--ifc-cl", str(SAMPLE),
                "--name", "test_service",
                "--folder", "",
            ])
        assert exc_info.value.code == 0

    # publish_polyline_to_agol skal være kalt én gang
    mock_publish.assert_called_once()
    kwargs = mock_publish.call_args.kwargs
    assert kwargs["service_name"] == "test_service"
    # 12200-CL er EUREF89 NTM sone 7 (EPSG:5107), lest fra IfcProjectedCRS
    assert kwargs["source_epsg"] == 5107
    # Punkter-dict skal ha én entry (alignment-navnet)
    assert len(kwargs["points_dict"]) == 1
    assert "n_hor_seg" in kwargs["extra_field_values"]
