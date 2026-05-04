# src/ifc_processor/renderer.py
from __future__ import annotations

import logging
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile

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
    "unknown":     {"color": "#888888", "linewidth": 0.5, "linestyle": "--", "zorder": 1},
}

_TOL = 1e-6  # toleranse for sammenkjeding av endepunkter (meter)


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

    # Graph-paper grid
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#cccccc", linewidth=0.4, linestyle="-")
    ax.grid(which="minor", color="#eeeeee", linewidth=0.2, linestyle="-")
    ax.minorticks_on()

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

    # Horizontal reference line with elevation label
    ref_elev = round(cross_section.elevation, 2)
    ax.axhline(y=0.0, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8, 0.0,
        f"{ref_elev:.2f}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
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
    ax.set_ylabel(f"Høyde over {ref_elev:.0f} m (m)", fontsize=7)
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
