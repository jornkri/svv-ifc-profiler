# tests/test_arcpy_converter.py
from __future__ import annotations
import sys
from unittest.mock import MagicMock
import pytest

# Mock arcpy før import av converter
arcpy_mock = MagicMock()
sys.modules.setdefault("arcpy", arcpy_mock)
sys.modules.setdefault("arcpy.conversion", arcpy_mock.conversion)
sys.modules.setdefault("arcpy.management", arcpy_mock.management)
sys.modules.setdefault("arcpy.env", arcpy_mock.env)

from src.arcpy_processor.errors import ArcpyProcessorError, BIM_CONVERSION_FAILED, NO_FEATURES


def test_convert_bim_calls_bimfile_to_geodatabase():
    arcpy_mock.env.scratchFolder = "C:/scratch"
    arcpy_mock.Exists.return_value = False  # ingen stale GDB
    arcpy_mock.management.CreateFileGDB.return_value = None
    arcpy_mock.conversion.BIMFileToGeodatabase.return_value = None
    arcpy_mock.env.workspace = ""
    arcpy_mock.ListFeatureClasses.return_value = ["Planum", "Skjaering"]
    arcpy_mock.SpatialReference.return_value = MagicMock()

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    fcs = converter.convert_bim("test.ifc", "test_dataset", wkid=25833)
    arcpy_mock.conversion.BIMFileToGeodatabase.assert_called_once()
    assert len(fcs) == 2
    assert "Planum" in fcs[0]
    assert "Skjaering" in fcs[1]


def test_delete_empty_fcs_removes_zero_count():
    arcpy_mock.management.GetCount.side_effect = lambda fc: [0] if fc == "Empty" else [5]
    arcpy_mock.management.Delete.reset_mock()
    arcpy_mock.management.Delete.return_value = None

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    remaining = converter.delete_empty_fcs(["Planum", "Empty"], "C:/scratch/bim.gdb/ds")
    assert remaining == ["Planum"]
    arcpy_mock.management.Delete.assert_called_once()


def test_delete_empty_fcs_raises_no_features_when_all_empty():
    arcpy_mock.management.GetCount.side_effect = None
    arcpy_mock.management.GetCount.return_value = [0]
    arcpy_mock.management.Delete.return_value = None

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    with pytest.raises(ArcpyProcessorError) as exc_info:
        converter.delete_empty_fcs(["A", "B"], "C:/scratch/bim.gdb/ds")
    assert exc_info.value.code == NO_FEATURES


def test_convert_bim_raises_on_arcpy_error():
    arcpy_mock.management.CreateFileGDB.return_value = None
    arcpy_mock.conversion.BIMFileToGeodatabase.side_effect = Exception("Ugyldig IFC")

    from src.arcpy_processor import converter
    import importlib; importlib.reload(converter)

    with pytest.raises(ArcpyProcessorError) as exc_info:
        converter.convert_bim("bad.ifc", "ds", wkid=25833)
    assert exc_info.value.code == BIM_CONVERSION_FAILED
