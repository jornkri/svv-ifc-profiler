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
