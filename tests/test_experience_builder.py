# tests/test_experience_builder.py
from __future__ import annotations
import sys
from unittest.mock import MagicMock
import pytest

# Mock arcgis at module level before any imports
_arcgis_mock = MagicMock()
sys.modules.setdefault("arcgis", _arcgis_mock)
sys.modules.setdefault("arcgis.features", _arcgis_mock.features)
sys.modules.setdefault("arcgis.gis", _arcgis_mock.gis)
sys.modules.setdefault("arcgis.apps", _arcgis_mock.apps)
sys.modules.setdefault("arcgis.apps.expbuilder", _arcgis_mock.apps.expbuilder)


def _make_layer(oids_with_attachments: dict) -> MagicMock:
    layer = MagicMock()
    layer.url = "https://services.arcgis.com/xxx/FeatureServer/0"
    features = []
    for oid in oids_with_attachments:
        feat = MagicMock()
        feat.attributes = {"OBJECTID": oid}
        features.append(feat)
    layer.query.return_value.features = features
    layer.attachments.search.side_effect = list(oids_with_attachments.values())
    return layer


def test_attachment_url_format():
    from src.arcpy_processor.experience_builder import _attachment_url
    result = _attachment_url("https://services.arcgis.com/xxx/FeatureServer/0", 42, 101)
    assert result == "https://services.arcgis.com/xxx/FeatureServer/0/42/attachments/101"


def test_backfill_returns_count():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({
        1: [{"id": 101, "name": "tverrprofil_0000.0.svg"}],
        2: [{"id": 102, "name": "tverrprofil_0050.0.svg"}],
    })
    assert backfill_svg_urls(layer) == 2


def test_backfill_calls_edit_features_once():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({1: [{"id": 101, "name": "station.svg"}]})
    backfill_svg_urls(layer)
    layer.edit_features.assert_called_once()
    call = layer.edit_features.call_args
    updates = call.kwargs.get("updates") or call.args[0]
    assert len(updates) == 1


def test_backfill_skips_non_svg_attachments():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({
        1: [{"id": 201, "name": "photo.png"}],   # not SVG — skip
        2: [{"id": 102, "name": "tverrprofil.svg"}],
    })
    assert backfill_svg_urls(layer) == 1


def test_backfill_no_attachments_does_not_call_edit_features():
    from src.arcpy_processor.experience_builder import backfill_svg_urls
    layer = _make_layer({1: [], 2: []})
    assert backfill_svg_urls(layer) == 0
    layer.edit_features.assert_not_called()


def test_create_experience_when_none_exists(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text(
        '{"cl": "__CENTERLINE_ITEM_ID__", "sec": "__SECTIONS_ITEM_ID__", "url": "__SERVICE_URL__"}'
    )

    gis = MagicMock()
    gis.content.search.return_value = []

    mock_exp = MagicMock()
    mock_exp.item.homepage = "https://experience.arcgis.com/builder/?id=new123"
    _arcgis_mock.apps.expbuilder.WebExperience.return_value = mock_exp

    url = create_or_update_experience(
        gis=gis,
        name="Profilutforsker",
        centerline_item_id="CL_ID",
        sections_item_id="SEC_ID",
        sections_service_url="https://services/FS",
        template_path=template,
    )

    mock_exp.create.assert_called_once()
    assert url == "https://experience.arcgis.com/builder/?id=new123"


def test_update_experience_when_exists(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text('{"sec": "__SECTIONS_ITEM_ID__"}')

    existing = MagicMock()
    existing.title = "Profilutforsker"
    existing.id = "existing456"
    existing.homepage = "https://experience.arcgis.com/builder/?id=existing456"

    gis = MagicMock()
    gis.content.search.return_value = [existing]

    url = create_or_update_experience(
        gis=gis,
        name="Profilutforsker",
        centerline_item_id="CL",
        sections_item_id="SEC",
        sections_service_url="https://svc/FS",
        template_path=template,
    )

    existing.update.assert_called_once()
    data_arg = (
        existing.update.call_args.kwargs.get("data")
        or existing.update.call_args.args[0]
    )
    assert "SEC" in data_arg
    assert "__SECTIONS_ITEM_ID__" not in data_arg
    assert url == "https://experience.arcgis.com/builder/?id=existing456"


def test_config_placeholders_all_substituted(tmp_path):
    from src.arcpy_processor.experience_builder import create_or_update_experience

    template = tmp_path / "template.json"
    template.write_text(
        '{"a":"__CENTERLINE_ITEM_ID__","b":"__SECTIONS_ITEM_ID__","c":"__SERVICE_URL__"}'
    )

    gis = MagicMock()
    gis.content.search.return_value = []
    mock_exp = MagicMock()
    mock_exp.item.homepage = "https://arcgis.com/apps/exp"
    _arcgis_mock.apps.expbuilder.WebExperience.return_value = mock_exp

    create_or_update_experience(
        gis=gis,
        name="Test",
        centerline_item_id="AAA",
        sections_item_id="BBB",
        sections_service_url="https://CCC",
        template_path=template,
    )

    data_arg = (
        mock_exp.item.update.call_args.kwargs.get("data")
        or mock_exp.item.update.call_args.args[0]
    )
    assert "AAA" in data_arg
    assert "BBB" in data_arg
    assert "https://CCC" in data_arg
    assert "__CENTERLINE_ITEM_ID__" not in data_arg
    assert "__SECTIONS_ITEM_ID__" not in data_arg
    assert "__SERVICE_URL__" not in data_arg
