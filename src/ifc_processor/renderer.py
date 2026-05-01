"""Render tverrprofiler og lengdeprofiler som bilder iht. SVV håndbok R700.

R700 spesifiserer tegningsgrunnlag: linjetyper, fargekoder, ramme, tittelfelt,
målestokk, koordinatkryss, etc. Renderer skal produsere PNG/SVG som passer
inn i webvisningen og som er gjenkjennelige som R700-tegninger.
"""

from __future__ import annotations

from pathlib import Path

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile


def render_cross_section_png(
    cross_section: CrossSection,
    output_path: Path,
    *,
    scale: float = 1.0 / 100.0,  # 1:100 typisk for tverrprofiler
    paper_size: tuple[float, float] = (297, 210),  # A4 landscape, mm
) -> Path:
    """Render et tverrprofil til PNG iht. R700.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError(
        "TODO: bruk matplotlib til å tegne polylines med R700-linjetyper og "
        "-farger, legg på rutenett, målestokk, tittelfelt."
    )


def render_longitudinal_profile_png(
    profile: LongitudinalProfile,
    output_path: Path,
) -> Path:
    """Render et lengdeprofil til PNG iht. R700.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError("TODO")
