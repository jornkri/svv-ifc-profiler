# tests/test_renderer.py
import tempfile
from pathlib import Path
import pytest
from src.ifc_processor.cross_section import CrossSection
from src.ifc_processor.renderer import render_cross_section_svg


def _simple_cross_section(station=50.0, elevation=100.0) -> CrossSection:
    return CrossSection(
        station=station,
        elevation=elevation,
        segments={
            "planum": [((-5.0, 0.0), (5.0, 0.0))],
            "skjaering": [((5.0, 0.0), (10.0, -3.0))],
            "unknown": [((-15.0, 0.0), (-5.0, 0.0))],
        }
    )


def test_render_produces_svg_file():
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "station_050.0.svg"
        render_cross_section_svg(cs, out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_render_svg_contains_profile_number():
    cs = _simple_cross_section(station=1234.5)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert "1234" in content  # profilnummer


def test_render_svg_contains_elevation():
    cs = _simple_cross_section(elevation=98.75)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert "98" in content  # kotehøyde


def test_render_svg_is_valid_xml():
    import xml.etree.ElementTree as ET
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        ET.parse(str(out))  # kaster exception hvis ugyldig XML
