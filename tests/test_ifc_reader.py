# tests/test_ifc_reader.py
from pathlib import Path
import numpy as np
import pytest
from src.ifc_processor.ifc_reader import TINLayer, classify_layer, read_ifc_tins

SAMPLE_IFC = Path(__file__).parent.parent / "samples" / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"

def test_classify_layer_planum():
    assert classify_layer("3D_D_Planum_ColGreyS") == "planum"

def test_classify_layer_skjaering():
    assert classify_layer("3D_D_Skjæring_Grass01") == "skjaering"

def test_classify_layer_fylling():
    assert classify_layer("3D_D_Fylling_Grass01") == "fylling"

def test_classify_layer_groft():
    assert classify_layer("3D_D_Grøfteskråning_Grass01") == "groft"

def test_classify_layer_kjorefelt():
    assert classify_layer("3D_D_Kjørefelt_Asphalt01") == "kjørefelt"

def test_classify_layer_skulder():
    assert classify_layer("3D_D_Skulder_Gravel01") == "skulder"

def test_classify_layer_groeftebunn():
    assert classify_layer("3D_D__Grøftebunn_Gravel03") == "groft"

def test_classify_layer_sykkelveg():
    assert classify_layer("3D_D__GangSykkelveg_Asphalt02") == "gang_sykkel"

def test_classify_layer_kantstein():
    assert classify_layer("3D_D_Kantstein_Stone01") == "kantstein"

def test_classify_layer_berghylle():
    assert classify_layer("3D_D__Berghylle_Rock01") == "skjaering"

def test_classify_layer_vegkropp():
    assert classify_layer("Vegkropp og kryss") == "planum"

def test_classify_layer_unknown():
    assert classify_layer("UkjentLag") == "unknown"

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_count():
    tins = read_ifc_tins(SAMPLE_IFC)
    assert len(tins) == 28

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_has_planum():
    tins = read_ifc_tins(SAMPLE_IFC)
    classes = {t.road_class for t in tins}
    assert "planum" in classes

@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_read_ifc_tins_triangles_shape():
    tins = read_ifc_tins(SAMPLE_IFC)
    for tin in tins:
        assert tin.triangles.ndim == 3
        assert tin.triangles.shape[0] > 0   # N triangles
        assert tin.triangles.shape[1] == 3  # 3 vertices
        assert tin.triangles.shape[2] == 3  # XYZ
