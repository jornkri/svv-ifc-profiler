# tests/test_pipeline_stations_json.py
import json
import tempfile
from pathlib import Path
from unittest.mock import patch
import pytest
from src.ifc_processor.pipeline import run_pipeline
from src.ifc_processor.cross_section import CrossSection

SAMPLE_IFC = Path(__file__).parent.parent / "samples" / "UEH-32-A-55075_05 Vei Kleverud_IFC.ifc"


def _cl_geojson(tmp: Path) -> Path:
    cl = tmp / "cl.geojson"
    cl.write_text(json.dumps({
        "type": "FeatureCollection",
        "features": [{"type": "Feature",
                      "geometry": {"type": "LineString",
                                   "coordinates": [[10.0, 20.0, 100.0],
                                                   [60.0, 20.0, 101.0]]},
                      "properties": {}}],
    }))
    return cl


def test_stations_json_keys_with_mocks(tmp_path):
    """stations.json keys and format — no real IFC needed."""
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"), \
         patch("src.ifc_processor.pipeline.render_normal_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    assert "stations_json" in result
    stations = json.loads(Path(result["stations_json"]).read_text())
    assert isinstance(stations, list)
    assert len(stations) >= 1
    row = stations[0]
    for key in ("station_m", "profil_nr", "x", "y", "z"):
        assert key in row
    assert row["station_m"] == pytest.approx(0.0)
    assert row["profil_nr"] == "0000.00"    # f"{0.0:07.2f}"
    assert row["x"] == pytest.approx(10.0)  # first point of centerline
    assert row["y"] == pytest.approx(20.0)
    assert row["z"] == pytest.approx(100.0)


def test_stations_json_profil_nr_format(tmp_path):
    """profil_nr matches f'{station_m:07.2f}'."""
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"), \
         patch("src.ifc_processor.pipeline.render_normal_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    stations = json.loads(Path(result["stations_json"]).read_text())
    for row in stations:
        assert row["profil_nr"] == f"{row['station_m']:07.2f}"


def test_pipeline_svg_filenames_use_new_prefix(tmp_path):
    """SVGer skal hete tverrprofil_* og normalprofil_*, ikke station_*."""
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg") as mock_tp, \
         patch("src.ifc_processor.pipeline.render_normal_section_svg") as mock_np:
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    called_tp = mock_tp.call_args[0][1]
    assert "tverrprofil_" in called_tp.name
    assert "station_" not in called_tp.name

    called_np = mock_np.call_args[0][1]
    assert "normalprofil_" in called_np.name

    meta = json.loads((tmp_path / "out" / "metadata.json").read_text())
    assert "normal_svg" in meta["stations"][0]


def test_stations_json_rubric_fields(tmp_path):
    """gradient_pct, cross_fall_l, cross_fall_r skal finnes i stations.json."""
    from src.ifc_processor.normal_section import NormalSection
    fake_cs = CrossSection(station=0.0, elevation=100.0, segments={})
    fake_ns = NormalSection(
        station=0.0,
        elevation=100.0,
        left_carriageway_width=float("nan"),
        right_carriageway_width=float("nan"),
        left_shoulder_width=float("nan"),
        right_shoulder_width=float("nan"),
        left_ditch_depth=float("nan"),
        right_ditch_depth=float("nan"),
        left_cross_fall_pct=3.5,
        right_cross_fall_pct=-3.5,
        left_slope_ratio=float("nan"),
        right_slope_ratio=float("nan"),
        section_type="ukjent",
    )
    cl_path = _cl_geojson(tmp_path)
    fake_ifc = tmp_path / "fake.ifc"
    fake_ifc.write_text("")

    with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
         patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
         patch("src.ifc_processor.pipeline.compute_normal_section", return_value=fake_ns), \
         patch("src.ifc_processor.pipeline.render_cross_section_svg"), \
         patch("src.ifc_processor.pipeline.render_normal_section_svg"):
        result = run_pipeline(
            ifc_path=fake_ifc,
            centerline_path=cl_path,
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )

    stations = json.loads(Path(result["stations_json"]).read_text())
    assert len(stations) >= 2, "Trenger minst 2 stasjoner for å teste gradient"
    row0 = stations[0]
    for key in ("gradient_pct", "cross_fall_l", "cross_fall_r"):
        assert key in row0, f"Mangler felt: {key}"
    # gradient_pct på siste stasjon skal være None (ingen neste punkt)
    last_row = stations[-1]
    assert last_row["gradient_pct"] is None
    # cross_fall fra NormalSection mock
    assert row0["cross_fall_l"] == pytest.approx(3.5)
    assert row0["cross_fall_r"] == pytest.approx(-3.5)


@pytest.mark.skipif(not SAMPLE_IFC.exists(), reason="testfil mangler")
def test_stations_json_with_real_ifc():
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = run_pipeline(
            ifc_path=SAMPLE_IFC,
            centerline_path=_cl_geojson(tmp_path),
            output_dir=tmp_path / "out",
            interval_m=50.0,
        )
        assert "stations_json" in result
        stations = json.loads(Path(result["stations_json"]).read_text())
        assert len(stations) >= 1
