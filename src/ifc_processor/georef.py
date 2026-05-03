# src/ifc_processor/georef.py
"""Koordinattransform: IFC lokalt koordinatsystem → ETRS89/NTM.

Georeferering er et forhåndstrinn som kjøres separat (ArcPy på Windows).
Denne modulen er en stub for fremtidig integrasjon.
"""
from __future__ import annotations
from pathlib import Path


def read_prj(prj_path: Path) -> dict:
    """Les .prj-fil og returner koordinatreferansesystem-info."""
    return {"wkt": prj_path.read_text().strip()}
