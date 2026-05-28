# tests/test_normal_section.py
import math
from src.ifc_processor.cross_section import CrossSection
from src.ifc_processor.normal_section import NormalSection, compute_normal_section


def _cs(**segs):
    return CrossSection(station=100.0, elevation=50.0, segments=segs)


def test_carriageway_width_from_kjørefelt():
    cs = _cs(kjørefelt=[
        ((-3.5, 0.0), (-0.1, 0.0)),
        ((0.1, 0.0), (3.5, 0.0)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_carriageway_width - 3.5) < 0.01
    assert abs(ns.right_carriageway_width - 3.5) < 0.01


def test_carriageway_width_falls_back_to_planum():
    cs = _cs(planum=[((-5.0, 0.0), (5.0, 0.0))])
    ns = compute_normal_section(cs)
    assert abs(ns.left_carriageway_width - 5.0) < 0.01
    assert abs(ns.right_carriageway_width - 5.0) < 0.01


def test_shoulder_width_is_additional_beyond_carriageway():
    cs = _cs(
        kjørefelt=[((-3.5, 0.0), (3.5, 0.0))],
        skulder=[((-5.5, -0.2), (-3.5, 0.0)), ((3.5, 0.0), (5.5, -0.2))],
    )
    ns = compute_normal_section(cs)
    assert abs(ns.left_shoulder_width - 2.0) < 0.01
    assert abs(ns.right_shoulder_width - 2.0) < 0.01


def test_cross_fall_pct():
    # 3.5m wide, drops 0.105m → 3%
    cs = _cs(kjørefelt=[
        ((-3.5, -0.105), (0.0, 0.0)),
        ((0.0, 0.0), (3.5, -0.105)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_cross_fall_pct - 3.0) < 0.2
    assert abs(ns.right_cross_fall_pct - 3.0) < 0.2


def test_slope_ratio_from_skjaering():
    # Δu=3.0, Δv=2.0 → ratio=1.5
    cs = _cs(skjaering=[
        ((-5.5, -0.2), (-8.5, -2.2)),
        ((5.5, -0.2), (8.5, -2.2)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_slope_ratio - 1.5) < 0.1
    assert abs(ns.right_slope_ratio - 1.5) < 0.1


def test_slope_ratio_from_fylling():
    cs = _cs(fylling=[
        ((-5.0, 0.0), (-8.0, -2.0)),
        ((5.0, 0.0), (8.0, -2.0)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_slope_ratio - 1.5) < 0.1
    assert abs(ns.right_slope_ratio - 1.5) < 0.1


def test_missing_class_gives_nan():
    cs = _cs()
    ns = compute_normal_section(cs)
    assert math.isnan(ns.left_carriageway_width)
    assert math.isnan(ns.left_shoulder_width)
    assert math.isnan(ns.left_ditch_depth)
    assert math.isnan(ns.left_slope_ratio)
    assert math.isnan(ns.left_cross_fall_pct)


def test_section_type_skjæring():
    cs = _cs(skjaering=[((5.0, 0.0), (8.0, -2.0))])
    assert compute_normal_section(cs).section_type == "skjæring"


def test_section_type_fylling():
    cs = _cs(fylling=[((5.0, 0.0), (8.0, -2.0))])
    assert compute_normal_section(cs).section_type == "fylling"


def test_section_type_kombinasjon():
    cs = _cs(
        skjaering=[((5.0, 0.0), (8.0, -2.0))],
        fylling=[((-5.0, 0.0), (-8.0, -2.0))],
    )
    assert compute_normal_section(cs).section_type == "kombinasjon"


def test_section_type_plan():
    cs = _cs(planum=[((-5.0, 0.0), (5.0, 0.0))])
    assert compute_normal_section(cs).section_type == "plan"


def test_ditch_depth():
    # grøft: fra v=-0.2 til v=-1.2 → dybde=1.0
    cs = _cs(groft=[
        ((-7.0, -1.2), (-5.5, -0.2)),
        ((5.5, -0.2), (7.0, -1.2)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_ditch_depth - 1.0) < 0.01
    assert abs(ns.right_ditch_depth - 1.0) < 0.01


def test_normal_section_is_dataclass():
    cs = _cs(planum=[((-3.5, 0.0), (3.5, 0.0))])
    ns = compute_normal_section(cs)
    assert isinstance(ns, NormalSection)
    assert ns.station == 100.0
    assert ns.elevation == 50.0


def test_cross_fall_ignores_non_road_segments():
    """kjørefelt-segmenter med uregelmessig vertikal komponent (rekkverk, kantstein,
    numerisk støy) skal filtreres ut så de ikke ødelegger tverrfall-resultatet."""
    cs = _cs(kjørefelt=[
        # Ekte kjørebane: 3.5 m, faller 0.105 m → 3 %
        ((-3.5, -0.105), (0.0, 0.0)),
        ((0.0, 0.0), (3.5, -0.105)),
        # Støy: kort segment med stort vertikalt utslag → 500 % slope
        ((3.5, -0.105), (3.51, -0.155)),
        ((-3.51, -0.155), (-3.5, -0.105)),
        # Ekstrem støy: nær-vertikalt → 55000 %
        ((3.50, -0.105), (3.5001, -0.155)),
    ])
    ns = compute_normal_section(cs)
    assert abs(ns.left_cross_fall_pct - 3.0) < 0.5, f"venstre var {ns.left_cross_fall_pct}"
    assert abs(ns.right_cross_fall_pct - 3.0) < 0.5, f"høyre var {ns.right_cross_fall_pct}"


def test_cross_fall_uses_median_for_robustness():
    """Hvis ett segment har avvikende (men ikke ekstrem) slope, skal medianen
    av de godkjente verdiene brukes, ikke middel."""
    cs = _cs(kjørefelt=[
        # 5 segmenter på høyre side: 4 stk ≈ 3 %, 1 stk ≈ 8 % (avvik men under 15 %-grensa)
        ((0.0, 0.0), (1.0, -0.03)),    # 3 %
        ((1.0, -0.03), (2.0, -0.06)),  # 3 %
        ((2.0, -0.06), (3.0, -0.09)),  # 3 %
        ((3.0, -0.09), (4.0, -0.17)),  # 8 % (avvik)
        ((4.0, -0.17), (5.0, -0.20)),  # 3 %
    ])
    ns = compute_normal_section(cs)
    # Middel = (3+3+3+8+3)/5 = 4.0, median = 3.0 → forventer ~3
    assert abs(ns.right_cross_fall_pct - 3.0) < 0.3


def test_cross_fall_segment_spanning_centreline():
    # IFC kan produsere kjørefelt-segment som krysser CL litt: midpoint avgjør siden
    cs = _cs(kjørefelt=[
        ((-3.5, -0.105), (0.1, 0.003)),  # midpoint u=-1.7 → venstre side
        ((0.0, 0.0), (3.5, -0.105)),
    ])
    ns = compute_normal_section(cs)
    assert not math.isnan(ns.left_cross_fall_pct)
    assert not math.isnan(ns.right_cross_fall_pct)
