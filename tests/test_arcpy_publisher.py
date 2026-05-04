# tests/test_arcpy_publisher.py
from __future__ import annotations
import json
import sys
from unittest.mock import MagicMock, patch
import pytest

# Mock arcgis før import av publisher
arcgis_mock = MagicMock()
arcgis_gis_mock = MagicMock()
arcgis_mock.gis = arcgis_gis_mock
sys.modules.setdefault("arcgis", arcgis_mock)
sys.modules.setdefault("arcgis.gis", arcgis_gis_mock)

from src.arcpy_processor.errors import ArcpyProcessorError, NAME_EXISTS, PUBLISH_FAILED


def _make_gis(existing_titles: list[str] = []) -> MagicMock:
    gis = MagicMock()
    items = [MagicMock(title=t) for t in existing_titles]
    gis.content.search.return_value = items
    return gis


def test_check_name_raises_name_exists():
    gis = _make_gis(existing_titles=["Vei_Kleverud"])
    from src.arcpy_processor.publisher import check_name_available
    with pytest.raises(ArcpyProcessorError) as exc_info:
        check_name_available(gis, "Vei_Kleverud", "SVV")
    assert exc_info.value.code == NAME_EXISTS


def test_check_name_passes_when_free():
    gis = _make_gis(existing_titles=["AnnetNavn"])
    from src.arcpy_processor.publisher import check_name_available
    check_name_available(gis, "Vei_Kleverud", "SVV")  # skal ikke kaste


def test_publish_returns_metadata():
    gis = _make_gis()
    mock_item = MagicMock()
    mock_item.id = "abc123"
    mock_item.homepage = "https://www.arcgis.com/home/item.html?id=abc123"
    mock_fs = MagicMock()
    mock_fs.url = "https://services.arcgis.com/xxx/FeatureServer"
    mock_fs.layers = [MagicMock(), MagicMock()]
    mock_item.publish.return_value = mock_fs
    gis.content.add.return_value = mock_item

    with patch("src.arcpy_processor.publisher.shutil.make_archive", return_value="/tmp/bim.zip"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):
        from src.arcpy_processor import publisher
        import importlib; importlib.reload(publisher)

        result = publisher.upload_and_publish(
            gis=gis,
            gdb_path="/scratch/bim_temp.gdb",
            name="Vei_Kleverud",
            folder="SVV",
        )

    assert result["status"] == "ok"
    assert result["item_id"] == "abc123"
    assert result["url"] == "https://services.arcgis.com/xxx/FeatureServer"
    assert result["feature_count"] == 2


def test_publish_raises_publish_failed_on_error():
    gis = _make_gis()
    gis.content.add.side_effect = Exception("Upload feilet")

    with patch("src.arcpy_processor.publisher.shutil.make_archive", return_value="/tmp/bim.zip"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):
        from src.arcpy_processor import publisher
        import importlib; importlib.reload(publisher)

        with pytest.raises(ArcpyProcessorError) as exc_info:
            publisher.upload_and_publish(gis, "/scratch/bim_temp.gdb", "Vei_Kleverud", "SVV")
        assert exc_info.value.code == PUBLISH_FAILED
