# tests/test_renderer.py
import tempfile
from pathlib import Path
import pytest
from src.ifc_processor.cross_section import CrossSection
from src.ifc_processor.renderer import _chain_segments, _upper_envelope_chain, render_cross_section_svg


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


def test_upper_envelope_collapses_stacked_layers():
    """Multiple near-identical layers (pavement structure) should reduce to one top surface."""
    # Simulate slitelag top, slitelag bottom, bærelag top, bærelag bottom
    segs = [
        ((-5.0, 0.00), (5.0, -0.20)),   # slitelag top (with crossfall)
        ((-5.0, -0.04), (5.0, -0.24)),  # slitelag bottom
        ((-5.0, -0.04), (5.0, -0.24)),  # bærelag top (same as slitelag bottom)
        ((-5.0, -0.14), (5.0, -0.34)),  # bærelag bottom
    ]
    result = _upper_envelope_chain(segs)
    assert len(result) >= 2
    # At u=0 the envelope should be at the slitelag top: v = lerp(0.0, -0.20, t=0.5) = -0.10
    vs_at_center = [v for u, v in result if abs(u) < 0.2]
    assert all(v > -0.15 for v in vs_at_center), "Envelope should trace the topmost surface"


def test_upper_envelope_single_segment():
    segs = [((-5.0, 0.0), (5.0, 0.0))]
    result = _upper_envelope_chain(segs)
    assert len(result) >= 2
    assert all(abs(v) < 1e-9 for _, v in result)


def test_upper_envelope_empty():
    assert _upper_envelope_chain([]) == []


def test_chain_segments_connects_adjacent():
    # Tre segmenter: A-B, B-C, C-D → én kjede med 4 punkter
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.0, 0.0), (2.0, 0.0)),
        ((2.0, 0.0), (3.0, 0.0)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 1
    assert len(chains[0]) == 4


def test_chain_segments_isolated():
    # To adskilte segmenter → to kjeder
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((5.0, 0.0), (6.0, 0.0)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 2


def test_chain_segments_empty():
    assert _chain_segments([]) == []


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


# --- R700-mangler (gap-analyse option A) ---

def test_snap_ref_elevation_floors_below_lowest_point():
    """_snap_ref_elevation skal returnere heltallsmeter under laveste absolute punkt."""
    from src.ifc_processor.renderer import _snap_ref_elevation
    # station_z=100, min_v=-3.7 → abs lowest = 96.3 → floor = 96
    assert _snap_ref_elevation(station_z=100.0, min_v=-3.7) == 96
    # station_z=100, min_v=0.5 → abs lowest = 100.5 → floor = 100
    assert _snap_ref_elevation(station_z=100.0, min_v=0.5) == 100
    # station_z=100, min_v=-4.0 → abs lowest = 96.0 → floor = 96
    assert _snap_ref_elevation(station_z=100.0, min_v=-4.0) == 96
    # station_z=50.3, min_v=-1.2 → abs lowest = 49.1 → floor = 49
    assert _snap_ref_elevation(station_z=50.3, min_v=-1.2) == 49


def test_kotehøyde_label_is_whole_metre():
    """Kotehøyde-etiketten i SVG skal være snappet helt meter (ikke desimal stasjonshøyde)."""
    cs = CrossSection(
        station=50.0,
        elevation=102.7,
        segments={
            "skjaering": [((5.0, -1.5), (10.0, -4.3))],  # min_v=-4.3, abs=98.4 → snap=98
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        assert "<!-- 98 -->" in content  # matplotlib SVG-kommentar for tekstinnhold


def test_svg_contains_scale_1_200():
    """SVG skal inneholde målestokken '1:200' i tittelfelt."""
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        assert "1:200" in out.read_text()


def test_svg_contains_centreline_mark():
    """SVG skal inneholde et vertikalt senterlinjemerke (u=0 er synlig i plottet)."""
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text()
        # matplotlib rendrer axvline som en linje — sjekk at renderer kaller axvline
        # ved å inspisere at "CL" eller "SL" tekst-merket finnes
        assert "SL" in content or "CL" in content


# ---------------------------------------------------------------------------
# Tests for render_normal_section_svg()
# ---------------------------------------------------------------------------

from src.ifc_processor.renderer import render_normal_section_svg  # noqa: E402


def _full_cross_section(station=100.0, elevation=50.0) -> CrossSection:
    """CrossSection med kjørefelt, skulder, skjæring og grøft på begge sider."""
    return CrossSection(
        station=station,
        elevation=elevation,
        segments={
            "kjørefelt": [
                ((-3.5, 0.0), (0.0, 0.0)),
                ((0.0, 0.0), (3.5, 0.0)),
            ],
            "skulder": [
                ((-3.5, 0.0), (-5.0, -0.105)),
                ((3.5, 0.0), (5.0, -0.105)),
            ],
            "groft": [
                ((-5.0, -0.105), (-6.0, -0.5)),
                ((5.0, -0.105), (6.0, -0.5)),
            ],
            "skjaering": [
                ((-6.0, -0.5), (-9.0, -2.5)),
                ((6.0, -0.5), (9.0, -2.5)),
            ],
        }
    )


def _minimal_cross_section(station=200.0, elevation=30.0) -> CrossSection:
    """CrossSection med kun planum — ingen skulder, skjæring eller grøft."""
    return CrossSection(
        station=station,
        elevation=elevation,
        segments={
            "planum": [
                ((-4.0, 0.0), (4.0, 0.0)),
            ],
        }
    )


def test_render_normal_section_svg_produces_file():
    """render_normal_section_svg skal skrive en fil som eksisterer og er ikke-tom."""
    cs = _full_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_100.svg"
        result = render_normal_section_svg(cs, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0


def test_render_normal_section_svg_is_valid_xml():
    """Output fra render_normal_section_svg skal parse som gyldig XML."""
    import xml.etree.ElementTree as ET
    cs = _full_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_100.svg"
        render_normal_section_svg(cs, out)
        ET.parse(str(out))  # kaster exception hvis ugyldig XML


def test_render_normal_section_svg_contains_scale_1_50():
    """SVG skal inneholde målestokken '1:50' i tittelfelt."""
    cs = _full_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_100.svg"
        render_normal_section_svg(cs, out)
        assert "1:50" in out.read_text()


def test_render_normal_section_svg_contains_normalprofil_title():
    """SVG skal inneholde tittelen 'Normalprofil' og profilnummeret."""
    cs = _full_cross_section(station=123.45)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_123.svg"
        render_normal_section_svg(cs, out)
        content = out.read_text()
        assert "Normalprofil" in content
        assert "123" in content  # profilnummer i tittel eller tittelfelt


def test_render_normal_section_svg_nan_safe():
    """CrossSection med kun planum skal rendre uten feil (NaN-annotasjoner hoppes over)."""
    cs = _minimal_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_200.svg"
        render_normal_section_svg(cs, out)  # skal ikke kaste exception
        assert out.exists()
        assert out.stat().st_size > 0


def test_svg_contains_data_cs_gids():
    """SVG-en skal inneholde gid-tagger for kjørefelt og terreng."""
    cs = CrossSection(
        station=50.0,
        elevation=100.0,
        segments={
            "planum": [((-4.5, 0.0), (4.5, 0.0))],
            "terreng": [((-10.0, -2.0), (10.0, -2.0))],
            "skjaering": [((4.5, 0.0), (8.0, -3.0))],
        }
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
        assert 'id="cs:kjørefelt"' in content
        assert 'id="cs:terreng"' in content
        assert 'id="cs:skjaering"' in content
