# Normalprofil per tverrprofil-stasjon — implementasjonsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generer en R700-normalprofil SVG (1:50, dimensjonert snitt med bredder, tverrfall, skråningsforhold og etiketter) per tverrprofil-stasjon, og publiser den som eget vedlegg på tilhørende AGOL-punkt ved siden av tverrprofil-SVGen.

**Architecture:** Ny modul `normal_section.py` beregner `NormalSection`-dimensjoner fra eksisterende `CrossSection`. Ny funksjon `render_normal_section_svg()` i `renderer.py` tegner normalprofilen. `pipeline.py` kaller begge render-funksjoner per stasjon og lagrer begge stier i metadata. `tverrprofil_to_agol.py` legger ved to SVGer per punkt via match-tabell.

**Tech Stack:** Python 3.13, matplotlib, dataclasses, pytest

---

## Fil-oversikt

| Fil | Status | Ansvar |
|---|---|---|
| `src/ifc_processor/normal_section.py` | NY | `NormalSection` dataclass + `compute_normal_section()` |
| `src/ifc_processor/renderer.py` | ENDRE | Legg til `render_normal_section_svg()` + `_draw_dim_line()` |
| `src/ifc_processor/pipeline.py` | ENDRE | Gi SVGer nytt filnavn, generer normalprofil per stasjon |
| `src/arcpy_processor/tverrprofil_to_agol.py` | ENDRE | To vedlegg per punkt i match-tabellen |
| `tests/test_normal_section.py` | NY | Unit-tester for compute_normal_section |
| `tests/test_renderer.py` | ENDRE | Test at render_normal_section_svg produserer gyldig SVG med 1:50 |
| `tests/test_pipeline_stations_json.py` | ENDRE | Mock render_normal_section_svg, ny normal_svg-nøkkel |
| `tests/test_tverrprofil_to_agol.py` | ENDRE | To vedlegg per OID i match-tabell |

---

## Task 1: NormalSection dataclass + compute_normal_section()

**Files:**
- Create: `src/ifc_processor/normal_section.py`
- Create: `tests/test_normal_section.py`

- [ ] **Step 1: Skriv failing tester**

Opprett `tests/test_normal_section.py`:

```python
# tests/test_normal_section.py
import math
import pytest
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
```

- [ ] **Step 2: Kjør tester for å verifisere at de feiler**

```
pytest tests/test_normal_section.py -v
```

Forventet: `ImportError: cannot import name 'NormalSection' from 'src.ifc_processor.normal_section'`

- [ ] **Step 3: Implementer normal_section.py**

Opprett `src/ifc_processor/normal_section.py`:

```python
# src/ifc_processor/normal_section.py
from __future__ import annotations

import math
from dataclasses import dataclass

from .cross_section import CrossSection


@dataclass
class NormalSection:
    station: float
    elevation: float
    left_carriageway_width: float   # m fra CL til yttergrense kjørefelt
    right_carriageway_width: float
    left_shoulder_width: float      # m ekstra bredde utover kjørefelt, NaN hvis ingen
    right_shoulder_width: float
    left_ditch_depth: float         # vertikal dybde grøft, NaN hvis ingen
    right_ditch_depth: float
    left_slope_ratio: float         # 1:x for skjæring/fylling, NaN hvis ingen
    right_slope_ratio: float
    left_cross_fall_pct: float      # % fall på kjørebanens venstre side
    right_cross_fall_pct: float
    section_type: str               # "skjæring" | "fylling" | "plan" | "kombinasjon"


def _outer_u(segs: list, left: bool) -> float:
    """Returnerer max |u| for segmenter på angitt side, NaN hvis ingen."""
    pts = []
    for (u1, v1), (u2, v2) in segs:
        for u, _ in [(u1, v1), (u2, v2)]:
            if left and u < 0:
                pts.append(abs(u))
            elif not left and u > 0:
                pts.append(u)
    return max(pts) if pts else float("nan")


def _cross_fall(segs: list, left: bool) -> float:
    """Beregner gjennomsnittlig tverrfall i % fra segmenter på angitt side."""
    slopes = []
    for (u1, v1), (u2, v2) in segs:
        if left and max(u1, u2) > 0:
            continue
        if not left and min(u1, u2) < 0:
            continue
        du = abs(u2 - u1)
        dv = abs(v2 - v1)
        if du > 1e-6:
            slopes.append(dv / du * 100)
    return sum(slopes) / len(slopes) if slopes else float("nan")


def _slope_ratio(segs: list, left: bool) -> float:
    """Beregner gjennomsnittlig 1:x skråningsforhold fra segmenter på angitt side."""
    ratios = []
    for (u1, v1), (u2, v2) in segs:
        if left and max(u1, u2) > 0:
            continue
        if not left and min(u1, u2) < 0:
            continue
        du = abs(u2 - u1)
        dv = abs(v2 - v1)
        if dv > 1e-6:
            ratios.append(du / dv)
    return sum(ratios) / len(ratios) if ratios else float("nan")


def _ditch_depth(segs: list, left: bool) -> float:
    """Returnerer vertikal dybde (max_v - min_v) for grøftsegmenter på angitt side."""
    vs = []
    for (u1, v1), (u2, v2) in segs:
        for u, v in [(u1, v1), (u2, v2)]:
            if left and u < 0:
                vs.append(v)
            elif not left and u > 0:
                vs.append(v)
    if len(vs) < 2:
        return float("nan")
    return max(vs) - min(vs)


def compute_normal_section(cs: CrossSection) -> NormalSection:
    """Beregn R700-dimensjoner fra et målt tverrprofil."""
    nan = float("nan")
    segs = cs.segments

    cw_cls = "kjørefelt" if "kjørefelt" in segs else "planum"
    cw_segs = segs.get(cw_cls, [])
    sk_segs = segs.get("skulder", [])

    left_cw = _outer_u(cw_segs, left=True)
    right_cw = _outer_u(cw_segs, left=False)
    left_sk = _outer_u(sk_segs, left=True)
    right_sk = _outer_u(sk_segs, left=False)

    def sh_width(sk: float, cw: float) -> float:
        if math.isnan(sk) or math.isnan(cw):
            return nan
        return max(0.0, sk - cw)

    cut_segs = segs.get("skjaering", [])
    fill_segs = segs.get("fylling", [])

    def slope_side(left: bool) -> float:
        r = _slope_ratio(cut_segs, left)
        if math.isnan(r):
            r = _slope_ratio(fill_segs, left)
        return r

    has_cut = bool(cut_segs)
    has_fill = bool(fill_segs)
    if has_cut and has_fill:
        stype = "kombinasjon"
    elif has_cut:
        stype = "skjæring"
    elif has_fill:
        stype = "fylling"
    else:
        stype = "plan"

    return NormalSection(
        station=cs.station,
        elevation=cs.elevation,
        left_carriageway_width=left_cw,
        right_carriageway_width=right_cw,
        left_shoulder_width=sh_width(left_sk, left_cw),
        right_shoulder_width=sh_width(right_sk, right_cw),
        left_ditch_depth=_ditch_depth(segs.get("groft", []), left=True),
        right_ditch_depth=_ditch_depth(segs.get("groft", []), left=False),
        left_slope_ratio=slope_side(left=True),
        right_slope_ratio=slope_side(left=False),
        left_cross_fall_pct=_cross_fall(cw_segs, left=True),
        right_cross_fall_pct=_cross_fall(cw_segs, left=False),
        section_type=stype,
    )
```

- [ ] **Step 4: Kjør tester for å verifisere at de passerer**

```
pytest tests/test_normal_section.py -v
```

Forventet: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/normal_section.py tests/test_normal_section.py
git commit -m "feat: add NormalSection dataclass and compute_normal_section()"
```

---

## Task 2: render_normal_section_svg()

**Files:**
- Modify: `src/ifc_processor/renderer.py`
- Modify: `tests/test_renderer.py`

- [ ] **Step 1: Skriv failing tester**

Legg til i `tests/test_renderer.py`:

```python
def test_render_normal_section_produces_svg():
    from src.ifc_processor.renderer import render_normal_section_svg
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "normalprofil_050.0.svg"
        render_normal_section_svg(cs, out)
        assert out.exists()
        assert out.stat().st_size > 0


def test_render_normal_section_contains_scale_1_50():
    from src.ifc_processor.renderer import render_normal_section_svg
    cs = _simple_cross_section(station=4920.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_normal_section_svg(cs, out)
        assert "1:50" in out.read_text()


def test_render_normal_section_contains_profile_number():
    from src.ifc_processor.renderer import render_normal_section_svg
    cs = _simple_cross_section(station=4920.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_normal_section_svg(cs, out)
        assert "4920" in out.read_text()


def test_render_normal_section_is_valid_xml():
    import xml.etree.ElementTree as ET
    from src.ifc_processor.renderer import render_normal_section_svg
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_normal_section_svg(cs, out)
        ET.parse(str(out))
```

- [ ] **Step 2: Kjør tester for å verifisere at de feiler**

```
pytest tests/test_renderer.py::test_render_normal_section_produces_svg tests/test_renderer.py::test_render_normal_section_contains_scale_1_50 tests/test_renderer.py::test_render_normal_section_contains_profile_number tests/test_renderer.py::test_render_normal_section_is_valid_xml -v
```

Forventet: `ImportError: cannot import name 'render_normal_section_svg'`

- [ ] **Step 3: Implementer render_normal_section_svg() og _draw_dim_line() i renderer.py**

Legg til etter den eksisterende `_snap_ref_elevation`-funksjonen og før `_chain_segments`:

```python
def _draw_dim_line(
    ax,
    u1: float,
    u2: float,
    v: float,
    label: str,
    color: str,
) -> None:
    """Tegn horisontal dimensjonslinje med piler mellom u1 og u2 på høyde v."""
    ax.annotate(
        "", xy=(u2, v), xytext=(u1, v),
        arrowprops=dict(arrowstyle="<->", color=color, lw=0.8),
    )
    ax.text(
        (u1 + u2) / 2, v + 0.3, label,
        ha="center", va="bottom", fontsize=6, color=color,
    )
```

Legg til ny funksjon etter `render_cross_section_svg`:

```python
def render_normal_section_svg(cross_section: CrossSection, output_path: Path) -> Path:
    """Render normalprofil med R700-annotasjoner (1:50) til SVG.

    Viser dimensjonslinjer for bredder (rød), tverrfall (grå),
    skråningsforhold (grønn) og komponentetiketter.

    Returns:
        Path til produsert SVG-fil.
    """
    from .normal_section import compute_normal_section

    ns = compute_normal_section(cross_section)
    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    all_u: list[float] = []
    all_v: list[float] = []
    for segs in cross_section.segments.values():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])

    if not all_u:
        ax.set_title(
            f"Normalprofil {cross_section.station:.2f} (tomt snitt)",
            fontsize=9, fontweight="bold", pad=6, loc="left",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fig.savefig(str(output_path), format="svg")
        finally:
            plt.close(fig)
        return output_path

    u_margin = max(5.0, (max(all_u) - min(all_u)) * 0.15)
    v_margin = max(3.0, (max(all_v) - min(all_v)) * 0.15)
    ax.set_xlim(min(all_u) - u_margin, max(all_u) + u_margin)
    ax.set_ylim(min(all_v) - v_margin, max(all_v) + v_margin)

    ax.xaxis.set_major_locator(MultipleLocator(5.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#aaaaaa", linewidth=0.5, linestyle="-")
    ax.grid(which="minor", color="#dddddd", linewidth=0.25, linestyle="-")

    ref_elev_abs = _snap_ref_elevation(cross_section.elevation, min(all_v))
    ref_line_v = ref_elev_abs - cross_section.elevation
    ax.axhline(y=ref_line_v, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8, ref_line_v, f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    ax.axvline(x=0.0, color="black", linewidth=0.5, linestyle=":", zorder=1)
    ax.text(
        0.0, max(all_v) + v_margin * 0.5, "SL",
        ha="center", va="bottom", fontsize=6, color="#333333",
    )

    for road_class, segs in cross_section.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for chain in _chain_segments(segs):
            us = [p[0] for p in chain]
            vs = [p[1] for p in chain]
            ax.plot(us, vs, **style)

    # Dimensjonslinjer og annotasjoner
    v_top = max(all_v)
    v_dim_cw = v_top + v_margin * 0.25
    v_dim_sh = v_top + v_margin * 0.55

    nan = float("nan")

    # Kjørefelt-bredde (rød)
    if not math.isnan(ns.left_carriageway_width):
        _draw_dim_line(ax, -ns.left_carriageway_width, 0.0, v_dim_cw,
                       f"{ns.left_carriageway_width:.2f}", "#cc0000")
    if not math.isnan(ns.right_carriageway_width):
        _draw_dim_line(ax, 0.0, ns.right_carriageway_width, v_dim_cw,
                       f"{ns.right_carriageway_width:.2f}", "#cc0000")

    # Skulder-bredde (blå)
    if not math.isnan(ns.left_shoulder_width) and ns.left_shoulder_width > 0.01:
        u_sk = ns.left_carriageway_width + ns.left_shoulder_width
        _draw_dim_line(ax, -u_sk, -ns.left_carriageway_width, v_dim_sh,
                       f"{ns.left_shoulder_width:.2f}", "#0000cc")
    if not math.isnan(ns.right_shoulder_width) and ns.right_shoulder_width > 0.01:
        u_sk = ns.right_carriageway_width + ns.right_shoulder_width
        _draw_dim_line(ax, ns.right_carriageway_width, u_sk, v_dim_sh,
                       f"{ns.right_shoulder_width:.2f}", "#0000cc")

    # Tverrfall % (mørkegrå)
    if not math.isnan(ns.left_cross_fall_pct):
        ax.text(-ns.left_carriageway_width * 0.5, v_top * 0.6,
                f"{ns.left_cross_fall_pct:.1f}%",
                ha="center", va="center", fontsize=7, color="#555555")
    if not math.isnan(ns.right_cross_fall_pct):
        ax.text(ns.right_carriageway_width * 0.5, v_top * 0.6,
                f"{ns.right_cross_fall_pct:.1f}%",
                ha="center", va="center", fontsize=7, color="#555555")

    # Skråningsforhold (grønn) — plasser langs skjæring/fylling
    for left, ratio_val in [(True, ns.left_slope_ratio), (False, ns.right_slope_ratio)]:
        if math.isnan(ratio_val):
            continue
        slope_cls = "skjaering" if cross_section.segments.get("skjaering") else "fylling"
        slope_pts = [
            (u, v)
            for (u1, v1), (u2, v2) in cross_section.segments.get(slope_cls, [])
            for u, v in [(u1, v1), (u2, v2)]
            if (left and u < 0) or (not left and u > 0)
        ]
        if slope_pts:
            mid_u = sum(p[0] for p in slope_pts) / len(slope_pts)
            mid_v = sum(p[1] for p in slope_pts) / len(slope_pts)
            offset = -1.5 if left else 1.5
            ax.text(mid_u + offset, mid_v, f"1:{ratio_val:.1f}",
                    ha="right" if left else "left", va="center",
                    fontsize=6.5, color="#006600")

    # Komponentetiketter
    _labels = [
        ("kjørefelt", "kjørefelt" in cross_section.segments),
        ("skulder", "skulder" in cross_section.segments),
        ("grøft", "groft" in cross_section.segments),
        ("skjæring", "skjaering" in cross_section.segments),
        ("fylling", "fylling" in cross_section.segments),
    ]
    label_y = min(all_v) - v_margin * 0.5
    label_x = min(all_u) + u_margin * 0.5
    for i, (lbl, present) in enumerate(_labels):
        if present:
            ax.text(label_x + i * 8, label_y, lbl,
                    ha="left", va="top", fontsize=5.5, color="#333333")

    ax.set_title(
        f"Normalprofil {cross_section.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel("Høyde (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:50 · Stasjon {cross_section.station:.2f} m",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    # Tegnforklaring
    from matplotlib.lines import Line2D
    ax.legend(
        handles=[
            Line2D([0], [0], color="black", lw=1.5, label="Prosjektert geometri"),
            Line2D([0], [0], color="black", lw=0.8, linestyle="--", label="Eksisterende terreng"),
        ],
        loc="lower left", fontsize=6, framealpha=0.8,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output_path
```

Legg også til `import math` øverst i `renderer.py` (er allerede lagt til i forrige task, sjekk at det er der).

- [ ] **Step 4: Kjør tester**

```
pytest tests/test_renderer.py -v
```

Forventet: alle 15 tester passerer

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "feat: add render_normal_section_svg with R700 annotations"
```

---

## Task 3: Pipeline-endringer (filnavn + normalprofil-generering)

**Files:**
- Modify: `src/ifc_processor/pipeline.py`
- Modify: `tests/test_pipeline_stations_json.py`

- [ ] **Step 1: Skriv failing test for nytt filnavn og normal_svg-nøkkel**

Legg til i `tests/test_pipeline_stations_json.py`:

```python
def test_pipeline_svg_filenames_use_new_prefix(tmp_path):
    """SVGer skal hete tverrprofil_* og normalprofil_*, ikke station_*."""
    from unittest.mock import patch, MagicMock
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

    # Tverrprofil-SVG bruker nytt prefix
    called_tp = mock_tp.call_args[0][1]
    assert "tverrprofil_" in called_tp.name
    assert "station_" not in called_tp.name

    # Normalprofil-SVG kalles
    called_np = mock_np.call_args[0][1]
    assert "normalprofil_" in called_np.name

    # metadata inneholder normal_svg-nøkkel
    import json
    meta = json.loads((tmp_path / "out" / "metadata.json").read_text())
    assert "normal_svg" in meta["stations"][0]
```

- [ ] **Step 2: Kjør test for å verifisere at den feiler**

```
pytest tests/test_pipeline_stations_json.py::test_pipeline_svg_filenames_use_new_prefix -v
```

Forventet: `AssertionError` — enten `render_normal_section_svg` ikke finnes i pipeline, eller filnavn feil.

- [ ] **Step 3: Oppdater pipeline.py**

Endre `src/ifc_processor/pipeline.py`:

1. Legg til import øverst (etter eksisterende renderer-import):
```python
from .renderer import render_cross_section_svg, render_normal_section_svg
```

2. I `run_pipeline()`-løkken, erstatt:
```python
svg_path = output_dir / f"station_{s.distance:07.1f}.svg"
render_cross_section_svg(cs, svg_path)
```
med:
```python
svg_path = output_dir / f"tverrprofil_{s.distance:07.1f}.svg"
normal_svg_path = output_dir / f"normalprofil_{s.distance:07.1f}.svg"
render_cross_section_svg(cs, svg_path)
render_normal_section_svg(cs, normal_svg_path)
```

3. Legg til `normal_svg_paths` parallelt med `svg_paths`:
```python
svg_paths: list[str] = []
normal_svg_paths: list[str] = []
```

4. Etter begge render-kall, legg til:
```python
svg_paths.append(str(svg_path))
normal_svg_paths.append(str(normal_svg_path))
```

5. Utvid `metadata_rows`:
```python
metadata_rows.append({
    "station": round(s.distance, 3),
    "elevation": round(cs.elevation, 3),
    "svg": str(svg_path),
    "normal_svg": str(normal_svg_path),
    "segment_classes": list(cs.segments.keys()),
})
```

6. Oppdater return-dict:
```python
return {
    "svgs": svg_paths,
    "normal_svgs": normal_svg_paths,
    "centerline": str(cl_path),
    "metadata": str(meta_path),
    "stations_json": str(stations_json_path),
}
```

- [ ] **Step 4: Oppdater eksisterende mocks i test_pipeline_stations_json.py**

De to eksisterende testene (`test_stations_json_keys_with_mocks` og `test_stations_json_profil_nr_format`) bruker `patch("src.ifc_processor.pipeline.render_cross_section_svg")` uten å patche `render_normal_section_svg`. Legg til mock for den nye funksjonen i begge:

```python
# I test_stations_json_keys_with_mocks:
with patch("src.ifc_processor.pipeline.read_ifc_tins", return_value=[]), \
     patch("src.ifc_processor.pipeline.cut_cross_section", return_value=fake_cs), \
     patch("src.ifc_processor.pipeline.render_cross_section_svg"), \
     patch("src.ifc_processor.pipeline.render_normal_section_svg"):
    ...

# I test_stations_json_profil_nr_format: samme endring
```

- [ ] **Step 5: Kjør alle pipeline-tester**

```
pytest tests/test_pipeline_stations_json.py tests/test_pipeline.py -v
```

Forventet: alle passer

- [ ] **Step 6: Commit**

```bash
git add src/ifc_processor/pipeline.py tests/test_pipeline_stations_json.py
git commit -m "feat: rename SVGs to tverrprofil_/normalprofil_, generate normalprofil per station"
```

---

## Task 4: tverrprofil_to_agol.py — to vedlegg per punkt

**Files:**
- Modify: `src/arcpy_processor/tverrprofil_to_agol.py`
- Modify: `tests/test_tverrprofil_to_agol.py`

- [ ] **Step 1: Sjekk eksisterende test**

Les `tests/test_tverrprofil_to_agol.py` for å forstå hva som allerede testes for attachment-logikken.

- [ ] **Step 2: Legg til failing test for to vedlegg**

Finn test-funksjonen som verifiserer attachment-kall i `tests/test_tverrprofil_to_agol.py`. Legg til (eller oppdater) en test som verifiserer at match-tabellen får TO rader per OID:

```python
def test_two_attachments_per_station(tmp_path):
    """Match-tabellen skal ha én rad for tverrprofil og én for normalprofil per punkt."""
    import json
    from unittest.mock import patch, MagicMock, call

    stations = [{"station_m": 10.0, "profil_nr": "0010.00",
                 "x": 100.0, "y": 200.0, "z": 50.0}]
    stations_json = tmp_path / "stations.json"
    stations_json.write_text(json.dumps(stations))

    svgs_dir = tmp_path / "svgs"
    svgs_dir.mkdir()
    tp_svg = svgs_dir / "tverrprofil_00010.0.svg"
    np_svg = svgs_dir / "normalprofil_00010.0.svg"
    tp_svg.write_text("<svg/>")
    np_svg.write_text("<svg/>")

    inserted_rows = []

    mock_ins_cursor = MagicMock()
    mock_ins_cursor.__enter__ = lambda s: s
    mock_ins_cursor.__exit__ = MagicMock(return_value=False)
    mock_ins_cursor.insertRow = lambda row: inserted_rows.append(row)

    mock_search_cursor = MagicMock()
    mock_search_cursor.__enter__ = lambda s: iter([(1, 10.0)])
    mock_search_cursor.__exit__ = MagicMock(return_value=False)

    import arcpy  # noqa - mocked below
    with patch("src.arcpy_processor.tverrprofil_to_agol.arcpy") as mock_arcpy, \
         patch("src.arcpy_processor.tverrprofil_to_agol.connect"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.check_name_available"), \
         patch("src.arcpy_processor.tverrprofil_to_agol.upload_and_publish",
               return_value={"url": "http://test"}):
        mock_arcpy.da.InsertCursor.return_value = mock_ins_cursor
        mock_arcpy.da.SearchCursor.return_value = mock_search_cursor
        mock_arcpy.env.scratchFolder = str(tmp_path)
        mock_arcpy.env.scratchGDB = str(tmp_path)
        mock_arcpy.Exists.return_value = False
        mock_arcpy.management.GetCount.return_value = [1]

        from src.arcpy_processor.tverrprofil_to_agol import main
        main([
            "--stations-json", str(stations_json),
            "--svgs-dir", str(svgs_dir),
            "--name", "test_profiler",
        ])

    # Finn radene som ble satt inn i match-tabellen (InsertCursor med fc_oid, svg_path)
    svg_rows = [r for r in inserted_rows if isinstance(r, tuple) and len(r) == 2
                and isinstance(r[1], str) and r[1].endswith(".svg")]
    assert len(svg_rows) == 2, f"Forventet 2 vedlegg, fikk {len(svg_rows)}: {svg_rows}"
    paths = [r[1] for r in svg_rows]
    assert any("tverrprofil" in p for p in paths)
    assert any("normalprofil" in p for p in paths)
```

- [ ] **Step 3: Kjør test for å verifisere at den feiler**

```
pytest tests/test_tverrprofil_to_agol.py::test_two_attachments_per_station -v
```

Forventet: `AssertionError: Forventet 2 vedlegg, fikk 1`

- [ ] **Step 4: Oppdater tverrprofil_to_agol.py**

Finn blokken i `main()` (linje ~162–170) som legger inn SVG-stier i match-tabellen:

```python
# GAMMEL kode:
for oid, station_m in cur:
    svg = svgs_dir / f"station_{station_m:07.1f}.svg"
    if svg.exists():
        ins.insertRow((oid, str(svg)))
        rows_added += 1
    else:
        logger.warning("SVG ikke funnet for stasjon %.1f m: %s", station_m, svg)
```

Erstatt med:

```python
# NY kode:
for oid, station_m in cur:
    tp_svg = svgs_dir / f"tverrprofil_{station_m:07.1f}.svg"
    np_svg = svgs_dir / f"normalprofil_{station_m:07.1f}.svg"
    for svg in (tp_svg, np_svg):
        if svg.exists():
            ins.insertRow((oid, str(svg)))
            rows_added += 1
        else:
            logger.warning("SVG ikke funnet: %s", svg)
```

- [ ] **Step 5: Kjør alle tverrprofil-tester**

```
pytest tests/test_tverrprofil_to_agol.py -v
```

Forventet: alle passer

- [ ] **Step 6: Commit**

```bash
git add src/arcpy_processor/tverrprofil_to_agol.py tests/test_tverrprofil_to_agol.py
git commit -m "feat: attach tverrprofil and normalprofil SVG per AGOL point"
```

---

## Task 5: Verifiser full testsuite

- [ ] **Step 1: Kjør alle tester (unntatt arcpy-integrasjon)**

```
pytest --ignore=tests/test_arcpy_converter.py --ignore=tests/test_arcpy_publisher.py --ignore=tests/test_arcpy_cli.py --ignore=tests/test_tverrprofil_to_agol.py --ignore=tests/test_landxml_to_agol.py -v
```

Forventet: alle passer, ingen warnings om uventede feil

- [ ] **Step 2: Kjør renderer-tester isolert for å verifisere**

```
pytest tests/test_renderer.py tests/test_normal_section.py -v
```

Forventet: alle passer

- [ ] **Step 3: Final commit med opprydding av testfiler**

Slett midlertidige testfiler fra rotmappen:

```bash
git rm --cached test_profil_4920.svg test_profil_*.png test_profil_viewer.html brainstorm_normalprofil.html brainstorm_shot.png 2>/dev/null; true
git add -A
git commit -m "chore: remove temp brainstorm and test plot files"
```
