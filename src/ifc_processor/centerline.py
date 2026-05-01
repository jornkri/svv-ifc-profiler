"""Ekstraher senterlinje fra en IFC-vegmodell.

Strategi (utkast):
1. Åpne IFC-fil med ifcopenshell.
2. Identifiser senterlinje-objekt(er). I IFC 4.3 (Road) finnes IfcAlignment som
   beskriver vegens horisontale og vertikale geometri eksplisitt. I eldre/andre
   IFC-er kan vi måtte rekonstruere fra geometriske representasjoner (f.eks.
   bounding box-akse til vegoverflate).
3. Returner senterlinjen som en sekvens 3D-punkter (x, y, z) eller en parametrisk
   kurve (stasjon → posisjon).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class Centerline:
    """Senterlinje representert som ordnede 3D-punkter med stasjonering."""

    points: list[tuple[float, float, float]]
    stations: list[float]  # kumulativ lengde langs linja, i meter

    @property
    def total_length(self) -> float:
        return self.stations[-1] if self.stations else 0.0


def extract_centerline(ifc_path: Path) -> Centerline:
    """Hent senterlinje fra IFC-fil.

    Args:
        ifc_path: Sti til .ifc-fil.

    Returns:
        Centerline-objekt med punkter og stasjonering.

    Raises:
        NotImplementedError: foreløpig stub.
    """
    raise NotImplementedError(
        "TODO: implementer ifcopenshell-parsing. Sjekk først for IfcAlignment "
        "(IFC 4.3). Hvis ikke til stede, fall tilbake til geometrisk rekonstruksjon."
    )
