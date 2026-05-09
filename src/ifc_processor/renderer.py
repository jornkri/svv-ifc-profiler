# src/ifc_processor/renderer.py
from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import MultipleLocator

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile
from .normal_section import compute_normal_section

logger = logging.getLogger(__name__)

# R700 line styles per road component
_STYLE: dict[str, dict] = {
    "planum":      {"color": "black",   "linewidth": 2.0, "linestyle": "-",  "zorder": 5},
    "kjørefelt":   {"color": "#111111", "linewidth": 1.5, "linestyle": "-",  "zorder": 4},
    "skulder":     {"color": "#333333", "linewidth": 1.0, "linestyle": "-",  "zorder": 4},
    "kantstein":   {"color": "black",   "linewidth": 1.5, "linestyle": "-",  "zorder": 4},
    "gang_sykkel": {"color": "#444444", "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "skjaering":   {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "fylling":     {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "groft":       {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "terreng":     {"color": "black",   "linewidth": 0.8, "linestyle": "--", "zorder": 2},
    "unknown":     {"color": "#888888", "linewidth": 0.5, "linestyle": "--", "zorder": 1},
}

_TOL = 1e-6  # toleranse for sammenkjeding av endepunkter (meter)


def _snap_ref_elevation(station_z: float, min_v: float) -> int:
    """Returner referanselinjekoteen snappet til heltallsmeter under laveste punkt (R700)."""
    return math.floor(station_z + min_v)


def _chain_segments(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """Kjed isolerte linjestykker fra triangelsnitt til sammenhengende polylinjer."""
    if not segs:
        return []

    def key(p: tuple[float, float]) -> tuple:
        return (round(p[0] / _TOL) * _TOL, round(p[1] / _TOL) * _TOL)

    adj: dict[tuple, list[tuple[tuple, int, tuple]]] = defaultdict(list)
    for i, (p1, p2) in enumerate(segs):
        k1, k2 = key(p1), key(p2)
        adj[k1].append((k2, i, p2))
        adj[k2].append((k1, i, p1))

    used: set[int] = set()
    chains: list[list[tuple[float, float]]] = []

    # Start fra endepunkter (grad 1) for å bygge kjeder fra ytterpunktene innover
    start_candidates = [
        pt for pt, neighbors in adj.items()
        if len(neighbors) == 1 and neighbors[0][1] not in used
    ]
    if not start_candidates:
        start_candidates = list(adj.keys())

    for start in start_candidates:
        available = [(nb, idx, actual) for nb, idx, actual in adj[start] if idx not in used]
        if not available:
            continue

        first_nb, first_idx, _ = available[0]
        first_seg = segs[first_idx]
        chain: list[tuple[float, float]] = (
            [first_seg[0], first_seg[1]] if key(first_seg[0]) == start
            else [first_seg[1], first_seg[0]]
        )
        used.add(first_idx)
        current = first_nb

        while True:
            nxt = [(nb, idx, a) for nb, idx, a in adj[current] if idx not in used]
            if not nxt:
                break
            nb, idx, _ = nxt[0]
            seg = segs[idx]
            chain.append(seg[1] if key(seg[0]) == current else seg[0])
            used.add(idx)
            current = nb

        chains.append(chain)

    for i, (p1, p2) in enumerate(segs):
        if i not in used:
            chains.append([p1, p2])

    return chains

_PAPER_W_MM = 420  # A3 width
_PAPER_H_MM = 297  # A3 height


def render_cross_section_svg(cross_section: CrossSection, output_path: Path) -> Path:
    """Render one cross-section as an R700-compliant SVG.

    R700 requirements:
    - Graph-paper grid background
    - Profile number above plot
    - Horizontal reference line with elevation label
    - Solid lines for road geometry (planum, skjaering, fylling, groft)
    - Dashed lines for unknown/terrain
    - Title block lower-right

    Returns:
        Path to the produced SVG file.
    """
    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    # Collect all coordinates for auto-scaling
    all_u: list[float] = []
    all_v: list[float] = []
    for segs in cross_section.segments.values():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])

    if not all_u:
        logger.warning("Ingen segmenter å rendre for stasjon %.1f", cross_section.station)
        ax.set_title(
            f"Profil {cross_section.station:.2f} (tomt snitt)",
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

    # R700: ruteark 1m × 1m — etiketter hvert 5m horisontalt, gridlinjer hvert 1m
    ax.xaxis.set_major_locator(MultipleLocator(5.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#aaaaaa", linewidth=0.5, linestyle="-")
    ax.grid(which="minor", color="#dddddd", linewidth=0.25, linestyle="-")

    # R700: horisontal referanselinje snappet til heltallsmeter under laveste punkt
    ref_elev_abs = _snap_ref_elevation(cross_section.elevation, min(all_v))
    ref_line_v = ref_elev_abs - cross_section.elevation
    ax.axhline(y=ref_line_v, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8, ref_line_v,
        f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    # R700: vertikalt senterlinjemerke ved u=0
    ax.axvline(x=0.0, color="black", linewidth=0.5, linestyle=":", zorder=1)
    ax.text(
        0.0, max(all_v) + v_margin * 0.5,
        "SL",
        ha="center", va="bottom", fontsize=6, color="#333333",
    )

    # Draw segments as connected polylines
    for road_class, segs in cross_section.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for chain in _chain_segments(segs):
            us = [p[0] for p in chain]
            vs = [p[1] for p in chain]
            ax.plot(us, vs, **style)

    # Profile number above plot (R700)
    ax.set_title(
        f"Profil {cross_section.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )

    # Axis labels
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel(f"Høyde (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    # Title block lower-right (R700 U-drawing)
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:200 · Stasjon {cross_section.station:.2f} m",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output_path


def render_cross_section_png(cross_section: CrossSection, output_path: Path) -> Path:
    """PNG export is outside MVP scope."""
    raise NotImplementedError("PNG-eksport er utenfor MVP-scope. Bruk render_cross_section_svg.")


def render_longitudinal_profile_png(
    profile: LongitudinalProfile,
    output_path: Path,
) -> Path:
    """Render et lengdeprofil til PNG iht. R700.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError("TODO")


def _draw_dim_line(
    ax,
    u_start: float,
    u_end: float,
    v: float,
    label: str,
    color: str = "#cc0000",
) -> None:
    """Tegn en horisontal dimensjonslinje med vertikale tikk-merker og sentrert etikett.

    Args:
        ax: Matplotlib Axes.
        u_start: Startposisjon horisontalt (m).
        u_end: Sluttposisjon horisontalt (m).
        v: Høyde dimensjonslinjen tegnes ved (m).
        label: Tekstetikett (f.eks. "3.50 m").
        color: Farge (standard rød R700-dimensjonslinjer).
    """
    ax.plot([u_start, u_end], [v, v], color=color, linewidth=0.8)
    for u in (u_start, u_end):
        ax.plot([u, u], [v - 0.15, v + 0.15], color=color, linewidth=0.8)
    ax.text(
        (u_start + u_end) / 2,
        v + 0.2,
        label,
        ha="center", va="bottom", fontsize=6, color=color,
    )


def render_normal_section_svg(cs: CrossSection, output_path: Path) -> Path:
    """Render et R700-normalprofil (dimensjonert tverrsnitt) som SVG.

    Kaller compute_normal_section() internt for å beregne dimensjoner,
    og tegner deretter geometri + annotasjonslag (breddemål, tverrfall,
    skråningsforhold, komponentetiketter) iht. R700.

    Args:
        cs: CrossSection-objekt med snittgeometri.
        output_path: Ønsket filsti for SVG-filen.

    Returns:
        Path til den produserte SVG-filen.
    """
    ns = compute_normal_section(cs)

    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    # --- Samle alle koordinater for auto-skalering ---
    all_u: list[float] = []
    all_v: list[float] = []
    for segs in cs.segments.values():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])

    if not all_u:
        logger.warning("Ingen segmenter å rendre for normalprofil stasjon %.1f", cs.station)
        ax.set_title(
            f"Normalprofil {cs.station:.2f} (tomt snitt)",
            fontsize=9, fontweight="bold", pad=6, loc="left",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fig.savefig(str(output_path), format="svg")
        finally:
            plt.close(fig)
        return output_path

    u_margin = max(3.0, (max(all_u) - min(all_u)) * 0.15)
    v_margin = max(2.0, (max(all_v) - min(all_v)) * 0.20)

    # Ekstra plass over geometrien til dimensjonslinjer (minst 3 m)
    dim_overhead = 3.5
    ax.set_xlim(min(all_u) - u_margin, max(all_u) + u_margin)
    ax.set_ylim(min(all_v) - v_margin, max(all_v) + v_margin + dim_overhead)

    # --- R700: ruteark 1 m × 1 m ---
    ax.xaxis.set_major_locator(MultipleLocator(5.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#aaaaaa", linewidth=0.5, linestyle="-")
    ax.grid(which="minor", color="#dddddd", linewidth=0.25, linestyle="-")

    # --- R700: horisontal referanselinje ---
    ref_elev_abs = _snap_ref_elevation(cs.elevation, min(all_v))
    ref_line_v = ref_elev_abs - cs.elevation
    ax.axhline(y=ref_line_v, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8,
        ref_line_v,
        f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    # --- R700: vertikalt senterlinjemerke ved u=0 ---
    ax.axvline(x=0.0, color="black", linewidth=0.5, linestyle=":", zorder=1)
    ax.text(
        0.0, max(all_v) + v_margin * 0.3,
        "SL",
        ha="center", va="bottom", fontsize=6, color="#333333",
    )

    # --- Geometrilag (samme stil som tverrprofil) ---
    for road_class, segs in cs.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for chain in _chain_segments(segs):
            us = [p[0] for p in chain]
            vs = [p[1] for p in chain]
            ax.plot(us, vs, **style)

    # --- Annotasjonslag ---
    # Høyde for dimensjonslinjer: litt over høyeste geometripunkt
    dim_v = max(all_v) + 1.5

    # 1. Breddemål (røde dimensjonslinjer) — kun hvis ikke NaN
    if not math.isnan(ns.left_carriageway_width):
        _draw_dim_line(
            ax,
            u_start=-ns.left_carriageway_width,
            u_end=0.0,
            v=dim_v,
            label=f"{ns.left_carriageway_width:.2f} m",
        )
    if not math.isnan(ns.right_carriageway_width):
        _draw_dim_line(
            ax,
            u_start=0.0,
            u_end=ns.right_carriageway_width,
            v=dim_v,
            label=f"{ns.right_carriageway_width:.2f} m",
        )
    if not math.isnan(ns.left_carriageway_width) and not math.isnan(ns.left_shoulder_width):
        _draw_dim_line(
            ax,
            u_start=-(ns.left_carriageway_width + ns.left_shoulder_width),
            u_end=-ns.left_carriageway_width,
            v=dim_v + 1.0,
            label=f"{ns.left_shoulder_width:.2f} m",
        )
    if not math.isnan(ns.right_carriageway_width) and not math.isnan(ns.right_shoulder_width):
        _draw_dim_line(
            ax,
            u_start=ns.right_carriageway_width,
            u_end=ns.right_carriageway_width + ns.right_shoulder_width,
            v=dim_v + 1.0,
            label=f"{ns.right_shoulder_width:.2f} m",
        )

    # 2. Tverrfall (%) — mørk grå tekst midt på kjørefeltflaten + skråpil
    cf_color = "#555555"
    if not math.isnan(ns.left_cross_fall_pct) and not math.isnan(ns.left_carriageway_width):
        u_mid = -ns.left_carriageway_width / 2
        ax.text(
            u_mid, -0.3,
            f"{ns.left_cross_fall_pct:.1f}%",
            ha="center", va="top", fontsize=6, color=cf_color,
        )
        # Skråpil: fallet går fra u=0 (kronepunkt) mot venstre kant
        arrow_u_from = u_mid + 0.4   # closer to crown
        arrow_u_to   = u_mid - 0.4   # toward edge
        arrow_v      = -0.15          # on the road surface
        ax.annotate(
            "",
            xy=(arrow_u_to, arrow_v),
            xytext=(arrow_u_from, arrow_v - 0.05),
            arrowprops=dict(arrowstyle="-|>", color=cf_color, lw=0.6),
        )
    if not math.isnan(ns.right_cross_fall_pct) and not math.isnan(ns.right_carriageway_width):
        u_mid = ns.right_carriageway_width / 2
        ax.text(
            u_mid, -0.3,
            f"{ns.right_cross_fall_pct:.1f}%",
            ha="center", va="top", fontsize=6, color=cf_color,
        )
        # Skråpil: fallet går fra u=0 (kronepunkt) mot høyre kant
        arrow_u_from = u_mid - 0.4
        arrow_u_to   = u_mid + 0.4
        arrow_v      = -0.15
        ax.annotate(
            "",
            xy=(arrow_u_to, arrow_v),
            xytext=(arrow_u_from, arrow_v - 0.05),
            arrowprops=dict(arrowstyle="-|>", color=cf_color, lw=0.6),
        )

    # 3. Skråningsforhold (1:x) — grønn tekst langs skjæring/fylling
    slope_color = "#228B22"
    cut_segs = cs.segments.get("skjaering", []) or cs.segments.get("fylling", [])
    if not math.isnan(ns.left_slope_ratio):
        # Finn omtrentlig midtpunkt på venstre skjæring/fylling
        left_pts = [
            p
            for (u1, v1), (u2, v2) in cut_segs
            for p in [(u1, v1), (u2, v2)]
            if p[0] < 0
        ]
        if left_pts:
            u_sl = sum(p[0] for p in left_pts) / len(left_pts)
            v_sl = sum(p[1] for p in left_pts) / len(left_pts)
            # Vinkel fra innerste til ytterste punkt (sortert på u, stabilt uavhengig av segmentrekkefølge)
            if len(left_pts) >= 2:
                p_inner = max(left_pts, key=lambda p: p[0])
                p_outer = min(left_pts, key=lambda p: p[0])
                angle_deg = math.degrees(math.atan2(p_outer[1] - p_inner[1], p_outer[0] - p_inner[0]))
            else:
                angle_deg = 0
            ax.text(
                u_sl, v_sl,
                f"1:{ns.left_slope_ratio:.1f}",
                ha="center", va="center", fontsize=6, color=slope_color,
                rotation=angle_deg,
            )
    if not math.isnan(ns.right_slope_ratio):
        right_pts = [
            p
            for (u1, v1), (u2, v2) in cut_segs
            for p in [(u1, v1), (u2, v2)]
            if p[0] > 0
        ]
        if right_pts:
            u_sr = sum(p[0] for p in right_pts) / len(right_pts)
            v_sr = sum(p[1] for p in right_pts) / len(right_pts)
            # Vinkel fra innerste til ytterste punkt (sortert på u, stabilt uavhengig av segmentrekkefølge)
            if len(right_pts) >= 2:
                p_inner = min(right_pts, key=lambda p: p[0])
                p_outer = max(right_pts, key=lambda p: p[0])
                angle_deg = math.degrees(math.atan2(p_outer[1] - p_inner[1], p_outer[0] - p_inner[0]))
            else:
                angle_deg = 0
            ax.text(
                u_sr, v_sr,
                f"1:{ns.right_slope_ratio:.1f}",
                ha="center", va="center", fontsize=6, color=slope_color,
                rotation=angle_deg,
            )

    # 4. Komponentetiketter (svart, 6pt) — én etikett per veiklasse
    # "planum" er IFC-overflategeometri-klassen som tilsvarer kjørefelt i R700
    component_label = {
        "kjørefelt": "kjørefelt",
        "planum": "kjørefelt",
        "skulder": "skulder",
        "groft": "grøft",
        "skjaering": ns.section_type if ns.section_type in ("skjæring", "kombinasjon") else "skjæring",
        "fylling": ns.section_type if ns.section_type in ("fylling", "kombinasjon") else "fylling",
    }
    labeled: set[str] = set()
    for road_class, segs in cs.segments.items():
        if road_class not in component_label or road_class in labeled:
            continue
        label_text = component_label[road_class]
        pts = [p for (u1, v1), (u2, v2) in segs for p in [(u1, v1), (u2, v2)]]
        if not pts:
            continue
        # Plasser én etikett per side — unngår klynge ved CL når segmenter finnes på begge sider
        for side_pts in (
            [p for p in pts if p[0] < -0.1],   # venstre
            [p for p in pts if p[0] > 0.1],    # høyre
        ):
            if not side_pts:
                continue
            u_rep = sum(p[0] for p in side_pts) / len(side_pts)
            max_v = max(p[1] for p in side_pts)
            ax.annotate(
                label_text,
                xy=(u_rep, max_v),
                xytext=(u_rep, max_v + 0.6),
                ha="center", va="bottom", fontsize=6, color="black",
                arrowprops=dict(arrowstyle="-", color="black", lw=0.4),
            )
        labeled.add(road_class)

    # --- Titler og akseetiketter ---
    ax.set_title(
        f"Normalprofil {cs.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel("Høyde relativt til senterlinje (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    # Tittelfelt nedre høyre (R700)
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:50 · Stasjon {cs.station:.2f} m",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    # --- Forklaring nedre venstre ---
    legend_handles = [
        plt.Line2D([0], [0], color="black", linewidth=1.5, linestyle="-",
                   label="Prosjektert geometri"),
        plt.Line2D([0], [0], color="black", linewidth=0.8, linestyle="--",
                   label="Eksisterende terreng"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=6, framealpha=0.8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output_path
