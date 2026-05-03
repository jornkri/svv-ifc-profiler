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
