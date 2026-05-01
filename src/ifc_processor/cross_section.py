"""Generer tverrprofiler ved gitte stasjoner langs senterlinjen.

Strategi (utkast):
1. For hver stasjon (f.eks. hver 10. m): finn punkt og tangent på senterlinja.
2. Definér et plan vinkelrett på tangenten i punktet.
3. Skjær BIM-modellens geometri (mesh fra ifcopenshell) med planet.
4. Projiser snittlinjene til 2D (lokalt koordinatsystem i planet).
5. Klassifiser elementer (vegoverflate, grøft, fylling, kantstein, etc.) ut fra
   IFC-typene/-egenskapene som finnes i modellen.
6. Output: en datastruktur som renderer kan bruke til å tegne profilen iht. R700.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .centerline import Centerline


@dataclass
class CrossSection:
    """Et tverrprofil ved en gitt stasjon."""

    station: float                              # meter langs senterlinja
    polylines: list[list[tuple[float, float]]]  # 2D-linjer i tverrprofilplan
    classifications: list[str]                  # IFC-type / R700-kategori per polyline
    metadata: dict                              # f.eks. høyde over havet, helning


def generate_cross_sections(
    ifc_path: Path,
    centerline: Centerline,
    interval_m: float = 10.0,
    width_m: float = 30.0,
) -> list[CrossSection]:
    """Generer tverrprofiler langs senterlinja.

    Args:
        ifc_path: Sti til IFC-fil.
        centerline: Senterlinjeobjekt fra ``extract_centerline``.
        interval_m: Intervall mellom profiler (default 10 m, brukerstyrt på sikt).
        width_m: Halv bredde av tverrsnittet til hver side av senterlinja.

    Returns:
        Liste av CrossSection-objekter, en per stasjon.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError(
        "TODO: les IFC-geometri via ifcopenshell.geom, bygg meshes (trimesh), "
        "skjær med plan vinkelrett på tangenten, og returner 2D-polylines."
    )
