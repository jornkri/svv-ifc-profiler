# tests/test_longitudinal_profile.py
import math
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
import pytest

from src.ifc_processor.centerline import Centerline
from src.ifc_processor.longitudinal_profile import (
    LongitudinalProfile,
    _compute_curve_points,
    generate_longitudinal_profile,
)
from src.ifc_processor.renderer import render_longitudinal_profile_svg


def _straight_centerline(length_m: float = 500.0, z_start: float = 100.0, grade_pct: float = 2.0) -> Centerline:
    """Rett senterlinje med jevn stigning."""
    n = int(length_m / 10) + 1
    xs = np.linspace(0, length_m, n)
    ys = np.zeros(n)
    zs = z_start + xs * grade_pct / 100
    pts = np.column_stack([xs, ys, zs])
    return Centerline.from_points(pts)


def _curved_centerline() -> Centerline:
    """Senterlinje med tydelig retningsendring midt på strekningen."""
    pts = np.array([
        [0.0, 0.0, 100.0],
        [100.0, 0.0, 101.0],
        [200.0, 0.0, 102.0],
        [250.0, 50.0, 102.5],   # kurve her
        [300.0, 100.0, 103.0],
        [400.0, 100.0, 104.0],
    ])
    return Centerline.from_points(pts)


# ---------------------------------------------------------------------------
# _compute_curve_points
# ---------------------------------------------------------------------------

def test_compute_curve_points_straight_returns_empty():
    cl = _straight_centerline()
    assert _compute_curve_points(cl) == []


def test_compute_curve_points_detects_bend():
    cl = _curved_centerline()
    cps = _compute_curve_points(cl)
    assert len(cps) >= 1
    # Alle kurvepunkter skal ha stasjon innenfor strekkens lengde
    total = float(cl.stations[-1])
    for s, delta in cps:
        assert 0 <= s <= total
        assert isinstance(delta, float)


def test_compute_curve_points_min_angle_threshold():
    cl = _curved_centerline()
    # Ved høy terskel: ingen kurvepunkter
    assert _compute_curve_points(cl, min_angle_deg=90.0) == []
    # Ved lav terskel: minst ett
    assert len(_compute_curve_points(cl, min_angle_deg=0.5)) >= 1


# ---------------------------------------------------------------------------
# generate_longitudinal_profile
# ---------------------------------------------------------------------------

def test_generate_basic_structure():
    cl = _straight_centerline(length_m=300.0)
    lp = generate_longitudinal_profile(cl)

    assert len(lp.stations) == len(cl.stations)
    assert "vegoverflate" in lp.surfaces
    assert len(lp.surfaces["vegoverflate"]) == len(lp.stations)
    assert len(lp.cross_falls) == len(lp.stations)


def test_generate_with_terrain():
    cl = _straight_centerline(length_m=200.0)
    n = len(cl.stations)
    terrain = [95.0 + i * 0.1 for i in range(n)]

    lp = generate_longitudinal_profile(cl, terrain_elevations=terrain)

    assert "terreng" in lp.surfaces
    assert len(lp.surfaces["terreng"]) == n
    assert lp.surfaces["terreng"][0] == pytest.approx(95.0)


def test_generate_terrain_length_mismatch_ignored():
    cl = _straight_centerline(length_m=200.0)
    wrong_len_terrain = [95.0, 96.0]  # feil lengde

    lp = generate_longitudinal_profile(cl, terrain_elevations=wrong_len_terrain)

    assert "terreng" not in lp.surfaces


def test_generate_cross_falls_stored():
    cl = _straight_centerline(length_m=200.0)
    n = len(cl.stations)
    cfs = [(3.0, 3.0)] * n

    lp = generate_longitudinal_profile(cl, cross_falls=cfs)

    assert lp.cross_falls[0] == (3.0, 3.0)


def test_generate_cross_falls_none_gives_nan():
    cl = _straight_centerline(length_m=100.0)
    lp = generate_longitudinal_profile(cl)

    for left, right in lp.cross_falls:
        assert math.isnan(left)
        assert math.isnan(right)


def test_generate_design_z_matches_centerline():
    cl = _straight_centerline(length_m=100.0, z_start=50.0, grade_pct=5.0)
    lp = generate_longitudinal_profile(cl)

    for z_lp, z_cl in zip(lp.surfaces["vegoverflate"], cl.points[:, 2]):
        assert z_lp == pytest.approx(float(z_cl))


# ---------------------------------------------------------------------------
# render_longitudinal_profile_svg
# ---------------------------------------------------------------------------

def _simple_profile(length_m: float = 400.0) -> LongitudinalProfile:
    cl = _straight_centerline(length_m=length_m, z_start=100.0, grade_pct=2.0)
    n = len(cl.stations)
    terrain = [99.0 + i * (length_m / 1000) for i in range(n)]
    cfs = [(3.0, 3.0)] * n
    return generate_longitudinal_profile(cl, terrain_elevations=terrain, cross_falls=cfs)


def test_render_produces_svg_file():
    lp = _simple_profile()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        result = render_longitudinal_profile_svg(lp, out)
        assert result == out
        assert out.exists()
        assert out.stat().st_size > 0


def test_render_is_valid_xml():
    lp = _simple_profile()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        render_longitudinal_profile_svg(lp, out)
        ET.parse(str(out))  # kaster exception hvis ugyldig XML


def test_render_contains_title():
    lp = _simple_profile()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        render_longitudinal_profile_svg(lp, out)
        content = out.read_text()
        assert "Lengdeprofil" in content


def test_render_contains_scale_annotation():
    lp = _simple_profile()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        render_longitudinal_profile_svg(lp, out)
        content = out.read_text()
        assert "1:1000" in content
        assert "1:100" in content


def test_render_contains_rubric_row_labels():
    lp = _simple_profile()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        render_longitudinal_profile_svg(lp, out)
        content = out.read_text(encoding="utf-8")
        assert "Profilnummer" in content
        assert "Tverrfall" in content
        assert "Profilh" in content      # "Profilhøyde" — unngår cp1252/utf-8-mismatch i assertion
        assert "Terrengh" in content     # "Terrenghøyde"


def test_render_no_terrain_still_works():
    cl = _straight_centerline(length_m=300.0)
    lp = generate_longitudinal_profile(cl)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil_no_terrain.svg"
        render_longitudinal_profile_svg(lp, out)
        assert out.exists()


def test_render_with_curve_points():
    cl = _curved_centerline()
    lp = generate_longitudinal_profile(cl)
    assert len(lp.curve_points) >= 1
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil_curved.svg"
        render_longitudinal_profile_svg(lp, out)
        assert out.exists()


def test_render_gradient_label_in_output():
    """SVG skal inneholde stigningsetikett mellom profilpunkter (+-x.x %)."""
    lp = _simple_profile(length_m=300.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "lengdeprofil.svg"
        render_longitudinal_profile_svg(lp, out)
        content = out.read_text()
        # 2 % stigning skal vises et sted som "+2.0 %"
        assert "%" in content
