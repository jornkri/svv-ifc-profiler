# tests/test_pipeline.py
import json
import tempfile
from pathlib import Path
import pytest
from src.ifc_processor.pipeline import run_pipeline

SAMPLE_IFC = Path(__file__).parent.parent / "samples" / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"


def _write_test_centerline(tmp: Path) -> Path:
    cl_path = tmp / "centerline.geojson"
    cl_path.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[0.0, 0.0, 100.0], [50.0, 0.0, 100.5], [100.0, 0.0, 101.0]]
            },
            "properties": {}
        }]
    }))
    return cl_path


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_pipeline_produces_output_files():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cl_path = _write_test_centerline(tmp_path)
        out_dir = tmp_path / "output"

        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=cl_path,
            output_dir=out_dir,
            interval_m=50.0,
        )

        assert Path(result["centerline"]).exists()
        assert Path(result["metadata"]).exists()
        assert len(result["svgs"]) >= 1
        for svg in result["svgs"]:
            assert Path(svg).exists()


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_pipeline_metadata_has_stations():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        cl_path = _write_test_centerline(tmp_path)
        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )
        meta = json.loads(Path(result["metadata"]).read_text())
        assert "stations" in meta
        assert len(meta["stations"]) >= 1


def test_pipeline_raises_without_centerline(tmp_path):
    fake_ifc = tmp_path / "empty.ifc"
    fake_ifc.write_text("")
    with pytest.raises(ValueError, match="Ingen senterlinje"):
        run_pipeline(ifc_path=fake_ifc, centerline_path=None, output_dir=tmp_path / "out")


def test_load_alignment_metadata_from_landxml():
    """Eksisterende LandXML-vei skal fortsatt fungere via ny metadata-helper."""
    from src.ifc_processor.pipeline import _load_alignment_metadata
    xml = Path(__file__).parent.parent / "samples" / "m_f_veg_70400_aligment.xml"
    meta = _load_alignment_metadata(xml)
    assert meta is not None
    assert len(meta.horizontal_segments) > 0
    # LandXML har ingen referenter
    assert meta.station_labels == []


def test_load_alignment_metadata_from_ifc():
    from src.ifc_processor.pipeline import _load_alignment_metadata
    ifc_cl = Path(__file__).parent.parent / "samples" / "m_f-veg_12200_CL.ifc"
    meta = _load_alignment_metadata(ifc_cl)
    assert meta is not None
    assert len(meta.horizontal_segments) == 67
    assert len(meta.vertical_pvi) >= 2
    assert len(meta.station_labels) > 50


def test_load_alignment_metadata_none_for_unknown():
    from src.ifc_processor.pipeline import _load_alignment_metadata
    assert _load_alignment_metadata(None) is None


def test_station_grid_starts_at_referent_offset():
    """Når IfcReferent finnes, skal stations starte ved første referent (modulo intervall)."""
    from src.ifc_processor.pipeline import _aligned_station_offset
    from src.ifc_processor.alignment_parser import StationLabel

    labels = [StationLabel(station=107.3, name="P 100", position=(0, 0, 0))]
    assert _aligned_station_offset(labels, interval_m=10.0) == pytest.approx(7.3)

    labels = [StationLabel(station=100.0, name="P 100", position=(0, 0, 0))]
    assert _aligned_station_offset(labels, interval_m=10.0) == pytest.approx(0.0)

    assert _aligned_station_offset([], interval_m=10.0) == pytest.approx(0.0)


def test_pipeline_aligns_grid_to_referent(tmp_path):
    """Run pipeline med 12200 IFC-CL og verifiser at stations starter ved referent-offset."""
    from src.ifc_processor.pipeline import run_pipeline
    import json
    samples = Path(__file__).parent.parent / "samples"
    ifc_path = samples / "m_f_veg_12200_Veg.ifc"
    cl_path = samples / "m_f-veg_12200_CL.ifc"
    if not ifc_path.exists() or not cl_path.exists():
        pytest.skip("12200-testfiler mangler")
    out = tmp_path / "out"
    result = run_pipeline(
        ifc_path=ifc_path,
        centerline_path=cl_path,
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_lengdeprofil=False,
    )
    stations = json.loads((out / "stations.json").read_text())
    if len(stations) > 1:
        first_two = stations[:2]
        delta = first_two[1]["station_m"] - first_two[0]["station_m"]
        assert abs(delta - 10.0) < 0.01


def test_station_rows_have_referent_name(tmp_path):
    """Stasjoner som matcher IfcReferent får referent_name-felt."""
    samples = Path(__file__).parent.parent / "samples"
    ifc_path = samples / "m_f_veg_12200_Veg.ifc"
    cl_path = samples / "m_f-veg_12200_CL.ifc"
    if not ifc_path.exists() or not cl_path.exists():
        pytest.skip("12200-testfiler mangler")
    out = tmp_path / "out"
    run_pipeline(
        ifc_path=ifc_path,
        centerline_path=cl_path,
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_tverrprofil=False,
        include_lengdeprofil=False,
    )
    stations = json.loads((out / "stations.json").read_text())
    with_ref = [s for s in stations if s.get("referent_name")]
    assert len(with_ref) >= 1


def test_station_labels_json_written(tmp_path):
    """station_labels.json skal skrives med alle IfcReferent."""
    samples = Path(__file__).parent.parent / "samples"
    ifc_path = samples / "m_f_veg_12200_Veg.ifc"
    cl_path = samples / "m_f-veg_12200_CL.ifc"
    if not ifc_path.exists() or not cl_path.exists():
        pytest.skip("12200-testfiler mangler")
    out = tmp_path / "out"
    run_pipeline(
        ifc_path=ifc_path,
        centerline_path=cl_path,
        output_dir=out,
        interval_m=10.0,
        include_terrain=False,
        include_tverrprofil=False,
        include_lengdeprofil=False,
    )
    labels = json.loads((out / "station_labels.json").read_text())
    assert len(labels) > 50
    assert "station" in labels[0]
    assert "name" in labels[0]
