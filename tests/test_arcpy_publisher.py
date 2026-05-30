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
    mock_fs = MagicMock()
    mock_fs.id = "abc123"
    mock_fs.url = "https://services.arcgis.com/xxx/FeatureServer"
    mock_fs.homepage = "https://www.arcgis.com/home/item.html?id=abc123"
    mock_fs.layers = [MagicMock(), MagicMock()]
    mock_item.publish.return_value = mock_fs
    gis.content.add.return_value = mock_item

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    with patch("src.arcpy_processor.publisher._zip_gdb"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):

        result = publisher.upload_and_publish(
            gis=gis,
            gdb_path="/scratch/bim_temp.gdb",
            name="Vei_Kleverud",
            folder="SVV",
        )

    assert result["status"] == "ok"
    assert result["item_id"] == "abc123"
    assert result["url"] == "https://services.arcgis.com/xxx/FeatureServer"
    assert result["layer_count"] == 2
    # Publisert item skal få ren tittel (uten "_gdb"-suffiks fra opplastingen)
    mock_fs.update.assert_called_once_with(item_properties={"title": "Vei_Kleverud"})


def test_publish_raises_publish_failed_on_error():
    gis = _make_gis()
    gis.content.add.side_effect = Exception("Upload feilet")

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    with patch("src.arcpy_processor.publisher._zip_gdb"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):

        with pytest.raises(ArcpyProcessorError) as exc_info:
            publisher.upload_and_publish(gis, "/scratch/bim_temp.gdb", "Vei_Kleverud", "SVV")
        assert exc_info.value.code == PUBLISH_FAILED


def test_publish_uses_etrs89_utm33_spatial_reference():
    """publish() skal sende targetSR wkid=25833 slik at AGOL lagrer i ETRS89/UTM33."""
    gis = _make_gis()
    mock_item = MagicMock()
    mock_fs = MagicMock()
    mock_fs.url = "https://services.arcgis.com/xxx/FeatureServer"
    mock_fs.layers = []
    mock_item.publish.return_value = mock_fs
    gis.content.add.return_value = mock_item

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    with patch("src.arcpy_processor.publisher._zip_gdb"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):

        publisher.upload_and_publish(gis, "/scratch/bim_temp.gdb", "Test", "SVV")

    call_kwargs = mock_item.publish.call_args
    params = call_kwargs[1].get("publish_parameters") or (
        call_kwargs[0][0] if call_kwargs[0] else None
    )
    assert params is not None, "publish() ble kalt uten publish_parameters"
    assert params.get("targetSR", {}).get("wkid") == 25833
    assert params.get("name") == "Test", "publish_parameters må inneholde name"


def test_publish_omits_targetsr_when_target_sr_none():
    """target_sr=None → INGEN targetSR i publish_parameters (bevarer multipatch/Z)."""
    gis = _make_gis()
    mock_item = MagicMock()
    mock_fs = MagicMock()
    mock_fs.url = "https://services.arcgis.com/xxx/FeatureServer"
    mock_fs.layers = []
    mock_item.publish.return_value = mock_fs
    gis.content.add.return_value = mock_item

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    with patch("src.arcpy_processor.publisher._zip_gdb"), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=True), \
         patch("src.arcpy_processor.publisher.os.remove"), \
         patch("src.arcpy_processor.publisher.os.path.getsize", return_value=1000000):

        publisher.upload_and_publish(gis, "/scratch/bim_3d.gdb", "Test3D", "SVV",
                                     target_sr=None)

    params = mock_item.publish.call_args.kwargs.get("publish_parameters")
    assert params is not None
    assert "targetSR" not in params, "targetSR skal IKKE sendes når target_sr=None"
    assert params.get("name") == "Test3D"


def test_publish_cleans_up_when_archive_fails():
    gis = _make_gis()

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    with patch("src.arcpy_processor.publisher._zip_gdb",
               side_effect=Exception("Disk full")), \
         patch("src.arcpy_processor.publisher.os.path.exists", return_value=False), \
         patch("src.arcpy_processor.publisher.os.remove") as mock_remove:

        with pytest.raises(ArcpyProcessorError) as exc_info:
            publisher.upload_and_publish(gis, "/scratch/bim_temp.gdb", "Test", "SVV")
        assert exc_info.value.code == PUBLISH_FAILED
        mock_remove.assert_not_called()  # zip finnes ikke, skal ikke forsøke slette


# ── publish_3d_object_layer (best-effort scene layer) ──

def _fs_item(item_id="fl1", owner="me"):
    it = MagicMock()
    it.id = item_id
    it.owner = owner
    return it


def test_publish_3d_object_layer_returns_scene_url_on_success():
    """Suksess: returnerer scene-URL + item-id og kaller publish_item med
    featureService→sceneService."""
    gis = MagicMock()
    gis._portal.publish_item.return_value = [{
        "type": "Scene Service",
        "serviceItemId": "scene99",
        "serviceurl": "https://tiles.arcgis.com/xxx/SceneServer",
    }]

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    res = publisher.publish_3d_object_layer(gis, _fs_item(), "Vei_3D", "SVV")

    assert res is not None
    assert res["scene_url"] == "https://tiles.arcgis.com/xxx/SceneServer"
    assert res["scene_item_id"] == "scene99"
    # Riktig kilde-type og output-type ble sendt
    kwargs = gis._portal.publish_item.call_args.kwargs
    assert kwargs.get("fileType") == "featureService"
    assert kwargs.get("outputType") == "sceneService"
    assert kwargs.get("itemid") == "fl1"
    # Scene-item får ren tittel ({name}_3D)
    gis.content.get.assert_called_with("scene99")
    gis.content.get.return_value.update.assert_called_once_with(
        item_properties={"title": "Vei_3D"})


def test_publish_3d_object_layer_returns_none_on_exception():
    """Myk degradering: feil i publish_item → None (ikke kast)."""
    gis = MagicMock()
    gis._portal.publish_item.side_effect = Exception("Not enabled on org")

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    assert publisher.publish_3d_object_layer(gis, _fs_item(), "Vei_3D", "SVV") is None


def test_publish_3d_object_layer_returns_none_when_service_unsuccessful():
    """publish_item kan returnere success=False uten å kaste → None."""
    gis = MagicMock()
    gis._portal.publish_item.return_value = [{"success": False, "error": "boom"}]

    from src.arcpy_processor import publisher
    import importlib; importlib.reload(publisher)

    assert publisher.publish_3d_object_layer(gis, _fs_item(), "Vei_3D", "SVV") is None
