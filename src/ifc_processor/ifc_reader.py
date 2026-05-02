# src/ifc_processor/ifc_reader.py
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np

logger = logging.getLogger(__name__)

_LAYER_KEYWORDS: dict[str, str] = {
    "planum": "planum",
    "skjæring": "skjaering",
    "skjaering": "skjaering",
    "fylling": "fylling",
    "grøfteskråning": "groft",
    "grofteskraning": "groft",
}


@dataclass
class TINLayer:
    element_id: str
    name: str
    layer: str
    road_class: str        # "planum" | "skjaering" | "fylling" | "groft" | "unknown"
    triangles: np.ndarray  # shape (N, 3, 3)


def classify_layer(layer_name: str) -> str:
    lower = layer_name.lower()
    for keyword, cls in _LAYER_KEYWORDS.items():
        if keyword in lower:
            return cls
    return "unknown"


def _get_property(element, pset_name: str, prop_name: str) -> str | None:
    for rel in getattr(element, "IsDefinedBy", []):
        if not rel.is_a("IfcRelDefinesByProperties"):
            continue
        pset = rel.RelatingPropertyDefinition
        if not (hasattr(pset, "Name") and pset.Name == pset_name):
            continue
        for prop in getattr(pset, "HasProperties", []):
            if prop.Name == prop_name:
                val = getattr(prop, "NominalValue", None)
                return str(val.wrappedValue) if val else None
    return None


def read_ifc_tins(ifc_path: Path) -> list[TINLayer]:
    ifc = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    result: list[TINLayer] = []
    for element in ifc.by_type("IfcBuildingElementProxy"):
        layer = _get_property(element, "Attributter", "Layer") or ""
        if not layer:
            layer = element.Name or ""
            logger.warning("Element %s mangler Layer-egenskap, bruker navn: %s", element.GlobalId, layer)

        road_class = classify_layer(layer)

        try:
            shape = ifcopenshell.geom.create_shape(settings, element)
        except Exception as exc:
            logger.warning("Kan ikke hente geometri for %s: %s", element.GlobalId, exc)
            continue

        verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
        faces = np.array(shape.geometry.faces, dtype=int).reshape(-1, 3)
        triangles = verts[faces]  # shape (N, 3, 3)

        result.append(TINLayer(
            element_id=element.GlobalId,
            name=element.Name or "",
            layer=layer,
            road_class=road_class,
            triangles=triangles,
        ))

    return result
