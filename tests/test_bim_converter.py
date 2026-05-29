# tests/test_bim_converter.py
from __future__ import annotations
import sys
from unittest.mock import MagicMock

# arcpy må stubbes før converter importeres (modulnivå-import)
sys.modules.setdefault("arcpy", MagicMock())
sys.modules.setdefault("arcpy.management", sys.modules["arcpy"].management)

from src.ifc_processor.bim_classifier import ClassifiedElement
from src.arcpy_processor.converter import _resolve_kategori


def test_resolve_kategori_found():
    cls = {"GUID1": ClassifiedElement("GUID1", "IfcKerb", "Kantstein 1", "Kantstein", "Vegbane")}
    assert _resolve_kategori("GUID1", cls) == ("Kantstein", "Vegbane", "IfcKerb", "Kantstein 1")


def test_resolve_kategori_missing():
    assert _resolve_kategori("UKJENT", {}) == ("Uklassifisert", "Annet", "", "")


# --- _find_guid_field ---
from unittest.mock import patch
from src.arcpy_processor.converter import _find_guid_field


def _fields(*names):
    out = []
    for n in names:
        f = MagicMock()
        f.name = n
        out.append(f)
    return out


def test_find_guid_field_matches_globalid():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "GlobalId", "Name")):
        assert _find_guid_field("fc") == "GlobalId"


def test_find_guid_field_matches_ifcguid_case_insensitive():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "IFCGUID", "Name")):
        assert _find_guid_field("fc") == "IFCGUID"


def test_find_guid_field_none_when_absent():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_fields("OBJECTID", "Name", "ObjectType")):
        assert _find_guid_field("fc") is None
