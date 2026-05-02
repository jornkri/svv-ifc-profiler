# src/ifc_processor/renderer.py
from __future__ import annotations

import logging
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile

logger = logging.getLogger(__name__)

# R700 line styles per road component
_STYLE: dict[str, dict] = {
    "planum":    {"color": "black", "linewidth": 2.0, "linestyle": "-", "zorder": 3},
    "skjaering": {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "fylling":   {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "groft":     {"color": "black", "linewidth": 1.0, "linestyle": "-", "zorder": 2},
    "unknown":   {"color": "black", "linewidth": 0.5, "linestyle": "--", "zorder": 1},
}

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
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(str(output_path), format="svg")
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

    # Draw segments
    for road_class, segs in cross_section.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for (u1, v1), (u2, v2) in segs:
            ax.plot([u1, u2], [v1, v2], **style)

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
    fig.savefig(str(output_path), format="svg", bbox_inches="tight")
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
