"""IFC-prosessor: les IFC, ekstraher senterlinje, generer tverr- og lengdeprofiler."""

from .centerline import extract_centerline
from .cross_section import generate_cross_sections
from .longitudinal_profile import generate_longitudinal_profile

__all__ = [
    "extract_centerline",
    "generate_cross_sections",
    "generate_longitudinal_profile",
]
