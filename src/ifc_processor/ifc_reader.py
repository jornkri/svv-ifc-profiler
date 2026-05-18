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
    # IFC2X3 / IFC4 (IfcBuildingElementProxy med Attributter.Layer)
    "planum": "planum",
    "vegkropp": "planum",
    "kjørefelt": "kjørefelt",
    "kjorfelt": "kjørefelt",
    "skulder": "skulder",
    "skjæring": "skjaering",
    "skjaering": "skjaering",
    "berghylle": "skjaering",
    "bergskjær": "skjaering",
    "fylling": "fylling",
    "grøfteskråning": "groft",
    "grofteskraning": "groft",
    "grøfteskraning": "groft",
    "grøftebunn": "groft",
    "grøfteskråning": "groft",
    "sykkelveg": "gang_sykkel",
    "gangsykkel": "gang_sykkel",
    "kantstein": "kantstein",
    # IFC4X3 (IfcCourse / IfcEarthworksFill med PresentationLayerAssignment)
    "bindlag": "kjørefelt",       # wearing/binder course = kjørefelt surface
    "bærelag": "planum",          # base course
    "forsterkningslag": "planum", # subgrade reinforcement
    "filterlag": "planum",        # filter layer
    "jordskj": "skjaering",       # Jordskjæring (abbreviated "Jordskj.")
    "grøft": "groft",             # ditch
    "groft": "groft",
    # Eksisterende terreng / topografi
    "terreng": "terreng",
    "terrain": "terreng",
    "dtm": "terreng",
    "topografi": "terreng",
}


def _parse_label(name: str) -> str:
    """Hent siste segment etter '|' fra IFC Name-attributt.

    "70400 1 | Bindlag 1"          → "Bindlag 1"
    "70400 1 | -4.02 | V. Grøft 2" → "V. Grøft 2"
    """
    parts = name.split("|")
    return parts[-1].strip()


@dataclass
class TINLayer:
    element_id: str
    name: str
    label: str             # siste del av Name etter |, f.eks. "Bindlag 1"
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


def _build_repr_layer_map(ifc) -> dict[int, str]:
    """Bygg mapping fra IfcShapeRepresentation.id() → lagnavn (IFC4X3-stil)."""
    repr_to_layer: dict[int, str] = {}
    for la in ifc.by_type("IfcPresentationLayerAssignment"):
        for item in la.AssignedItems:
            repr_to_layer[item.id()] = la.Name
    return repr_to_layer


def _layer_from_repr(element, repr_to_layer: dict[int, str]) -> str:
    """Hent lagnavn fra PresentationLayerAssignment for et element."""
    rep_obj = getattr(element, "Representation", None)
    if rep_obj is None:
        return ""
    for rep in getattr(rep_obj, "Representations", []):
        name = repr_to_layer.get(rep.id(), "")
        if name:
            return name
    return ""


def _extract_tin(element, settings) -> np.ndarray | None:
    """Returner triangler (N,3,3) for et element, eller None ved feil."""
    try:
        shape = ifcopenshell.geom.create_shape(settings, element)
    except Exception as exc:
        logger.warning("Kan ikke hente geometri for %s: %s", element.GlobalId, exc)
        return None

    verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
    faces_raw = np.array(shape.geometry.faces, dtype=int)
    if len(faces_raw) % 3 != 0:
        logger.warning(
            "Element %s har ikke-triangulerte flater (%d indekser), hopper over",
            element.GlobalId, len(faces_raw),
        )
        return None
    faces = faces_raw.reshape(-1, 3)
    return verts[faces]


# IFC4X3 element-typer med veggeometri
_IFC4X3_ELEMENT_TYPES = (
    "IfcCourse",
    "IfcEarthworksFill",
    "IfcDistributionChamberElement",
    "IfcEarthworksCut",
    "IfcGeographicElement",
)


def read_ifc_tins(ifc_path: Path) -> list[TINLayer]:
    ifc = ifcopenshell.open(str(ifc_path))
    settings = ifcopenshell.geom.settings()
    settings.set(settings.USE_WORLD_COORDS, True)

    result: list[TINLayer] = []

    # --- IFC2X3 / IFC4: IfcBuildingElementProxy med Attributter.Layer ---
    for element in ifc.by_type("IfcBuildingElementProxy"):
        layer = _get_property(element, "Attributter", "Layer") or ""
        if not layer:
            layer = element.Name or ""
            logger.warning(
                "Element %s mangler Layer-egenskap, bruker navn: %s",
                element.GlobalId, layer,
            )
        triangles = _extract_tin(element, settings)
        if triangles is None:
            continue
        raw_name = element.Name or ""
        result.append(TINLayer(
            element_id=element.GlobalId,
            name=raw_name,
            label=_parse_label(raw_name),
            layer=layer,
            road_class=classify_layer(layer),
            triangles=triangles,
        ))

    # --- IFC4X3: IfcCourse / IfcEarthworksFill / etc. ---
    if not result:
        repr_to_layer = _build_repr_layer_map(ifc)
        for ifc_type in _IFC4X3_ELEMENT_TYPES:
            try:
                elements = ifc.by_type(ifc_type)
            except RuntimeError:
                continue
            for element in elements:
                layer = _layer_from_repr(element, repr_to_layer) or element.Name or ""
                road_class = classify_layer(layer)
                # IfcGeographicElement er IFC4X3-typen for topografi/eksisterende terreng.
                # Fall back til "terreng" dersom klassifiseringen ikke ga noe mer spesifikt.
                if ifc_type == "IfcGeographicElement" and road_class == "unknown":
                    road_class = "terreng"
                triangles = _extract_tin(element, settings)
                if triangles is None:
                    continue
                raw_name = element.Name or ""
                result.append(TINLayer(
                    element_id=element.GlobalId,
                    name=raw_name,
                    label=_parse_label(raw_name),
                    layer=layer,
                    road_class=road_class,
                    triangles=triangles,
                ))

    logger.info("read_ifc_tins: %d TINer fra %s", len(result), Path(ifc_path).name)
    return result
