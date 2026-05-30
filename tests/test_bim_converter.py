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


def _typed_fields(*pairs):
    """pairs: (name, type) tuples."""
    out = []
    for name, ftype in pairs:
        f = MagicMock()
        f.name = name
        f.type = ftype
        out.append(f)
    return out


def test_find_guid_field_skips_arcgis_uuid_globalid():
    # ArcGIS UUID GlobalID (type 'GlobalID') must be skipped in favour of the IFC text guid
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_typed_fields(("OBJECTID", "OID"), ("GlobalID", "GlobalID"),
                                          ("IfcGUID", "String"))):
        assert _find_guid_field("fc") == "IfcGUID"


def test_find_guid_field_none_when_only_arcgis_uuid():
    with patch("src.arcpy_processor.converter.arcpy.ListFields",
               return_value=_typed_fields(("OBJECTID", "OID"), ("GlobalID", "GlobalID"))):
        assert _find_guid_field("fc") is None


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


# --- merge_and_categorize ---
import pytest
import src.arcpy_processor.converter as conv


def test_merge_and_categorize_orchestration(monkeypatch):
    calls = {"merge": None, "footprint": None, "joinfield": None, "rows": []}

    arcpy = conv.arcpy
    arcpy.reset_mock()

    # CreateFileGDB / Exists
    arcpy.Exists.return_value = False

    # Merge registrerer kall
    def _merge(inputs, output):
        calls["merge"] = (list(inputs), output)
    arcpy.management.Merge.side_effect = _merge

    # ListFields → guid-felt finnes
    gf = MagicMock(); gf.name = "GlobalId"
    monkeypatch.setattr(conv, "_find_guid_field", lambda fc: "GlobalId")

    # UpdateCursor: én rad med GlobalId "G1"
    row = ["G1", None, None, None, None]
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter([row])
        def updateRow(self, r): calls["rows"].append(list(r))
    arcpy.da.UpdateCursor.return_value = _Cur()

    def _footprint(in_fc, out_fc, **kw):
        calls["footprint"] = (in_fc, out_fc, kw)
    arcpy.ddd.MultiPatchFootprint.side_effect = _footprint

    def _joinfield(*a, **kw):
        calls["joinfield"] = (a, kw)
    arcpy.management.JoinField.side_effect = _joinfield

    from src.ifc_processor.bim_classifier import ClassifiedElement
    classification = {"G1": ClassifiedElement("G1", "IfcKerb", "Kantstein 1", "Kantstein", "Vegbane")}

    gdb = conv.merge_and_categorize(
        ["/scratch/bim_temp.gdb/ds/Courses", "/scratch/bim_temp.gdb/ds/Kerbs"],
        classification,
        scratch="/scratch",
    )

    assert gdb.endswith("bim_out.gdb")
    # Begge kilde-FC-ene ble merget
    assert len(calls["merge"][0]) == 2
    # Kategori ble skrevet til raden (kategori, fag_gruppe, ifc_klasse, navn)
    assert calls["rows"][0][1:] == ["Kantstein", "Vegbane", "IfcKerb", "Kantstein 1"]
    # Fотavtrykk laget og kategori join-et tilbake
    assert calls["footprint"] is not None
    assert calls["joinfield"] is not None


def test_merge_and_categorize_raises_when_no_guid_matches(monkeypatch):
    from src.arcpy_processor.errors import ArcpyProcessorError
    arcpy = conv.arcpy
    arcpy.reset_mock()
    arcpy.Exists.return_value = False
    arcpy.management.Merge.side_effect = None
    monkeypatch.setattr(conv, "_find_guid_field", lambda fc: "GlobalId")

    row = ["UNMATCHED_GUID", None, None, None, None]
    class _Cur:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def __iter__(self): return iter([row])
        def updateRow(self, r): pass
    arcpy.da.UpdateCursor.return_value = _Cur()

    from src.ifc_processor.bim_classifier import ClassifiedElement
    classification = {"G1": ClassifiedElement("G1", "IfcKerb", "K", "Kantstein", "Vegbane")}

    with pytest.raises(ArcpyProcessorError):
        conv.merge_and_categorize(["/s/bim_temp.gdb/ds/Kerbs"], classification, scratch="/scratch")
