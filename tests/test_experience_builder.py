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
