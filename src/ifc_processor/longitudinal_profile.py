"""Generer lengdeprofil langs vegens senterlinje.

Lengdeprofil = vertikal kurve som viser terreng/vegoverflate som funksjon av
stasjon. Iht. R700 vises typisk: vegoverflate, terreng (eksisterende), og
nøkkelelementer (kummer, kulverter, etc.) langs samme akse.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .centerline import Centerline


@dataclass
class LongitudinalProfile:
    """Lengdeprofil: stasjon → høyde for ulike linjer (vegoverflate, terreng, ...)."""

    stations: list[float]
    surfaces: dict[str, list[float]]   # f.eks. {"vegoverflate": [...], "terreng": [...]}
    annotations: list[dict]            # punktobjekter (kum, kulvert, etc.) langs profilen


def generate_longitudinal_profile(
    ifc_path: Path,
    centerline: Centerline,
    sample_interval_m: float = 1.0,
) -> LongitudinalProfile:
    """Generer lengdeprofil ved sampling langs senterlinja.

    Args:
        ifc_path: Sti til IFC-fil.
        centerline: Senterlinjeobjekt.
        sample_interval_m: Sample-intervall (default 1 m).

    Returns:
        LongitudinalProfile-objekt.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError(
        "TODO: sample senterlinjens z-verdi, og skjær terreng/andre flater "
        "vertikalt langs hele lengden."
    )
