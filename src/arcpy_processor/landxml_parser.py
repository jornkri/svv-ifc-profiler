# src/arcpy_processor/landxml_parser.py
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import ArcpyProcessorError, LANDXML_PARSE_ERROR


def parse_landxml(
    path: Path,
    features: list[str] | None = None,
    source_epsg: int | None = None,
) -> tuple[dict[str, list[tuple[float, float, float]]], int]:
    """Les LandXML og returner PlanFeature-polylinjer + kilde-EPSG.

    Args:
        path:        Sti til LandXML-fil.
        features:    Navnliste over PlanFeatures å inkludere. None = alle.
        source_epsg: Fallback-EPSG brukes kun hvis epsgCode mangler i fil.
                     Filens epsgCode overstyrer alltid.

    Returns:
        Tuple (points_dict, epsg) der points_dict mapper PlanFeature-navn
        til liste med (Easting, Northing, Z)-tupler i kilde-CRS.

    Raises:
        ArcpyProcessorError: LANDXML_PARSE_ERROR ved ugyldig XML, manglende
            EPSG eller ingen matchende features.
    """
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR, f"Ugyldig XML i '{Path(path).name}': {exc}"
        ) from exc

    root = tree.getroot()
    ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
    ns = {"lx": ns_uri} if ns_uri else {}

    def find_all(parent: ET.Element, tag: str) -> list[ET.Element]:
        return (parent.findall(f".//lx:{tag}", ns) if ns_uri
                else parent.findall(f".//{tag}"))

    def find_one(parent: ET.Element, tag: str) -> ET.Element | None:
        return (parent.find(f"lx:{tag}", ns) if ns_uri
                else parent.find(tag))

    # Read EPSG — file value takes precedence over source_epsg override
    epsg: int | None = source_epsg
    cs_el = find_one(root, "CoordinateSystem")
    if cs_el is not None and cs_el.get("epsgCode"):
        try:
            epsg = int(cs_el.get("epsgCode"))
        except ValueError:
            epsg = None  # will be caught below as missing EPSG
    if epsg is None:
        bad_code = cs_el.get("epsgCode") if cs_el is not None else None
        if bad_code:
            raise ArcpyProcessorError(
                LANDXML_PARSE_ERROR,
                f"Ugyldig epsgCode '{bad_code}' i '{Path(path).name}'. Forventet et heltall.",
            )
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR,
            f"Filen '{Path(path).name}' mangler epsgCode i <CoordinateSystem>. "
            "Oppgi kildesystem med --source-epsg.",
        )

    def parse_coord(text: str) -> tuple[float, float, float]:
        try:
            parts = text.strip().split()
            n, e = float(parts[0]), float(parts[1])
            z = float(parts[2]) if len(parts) > 2 else 0.0
            return e, n, z  # Northing/Easting-swap → (X=Easting, Y=Northing, Z)
        except (IndexError, ValueError) as exc:
            raise ArcpyProcessorError(
                LANDXML_PARSE_ERROR, f"Ugyldig koordinat '{text.strip()}': {exc}"
            ) from exc

    plan_features = find_all(root, "PlanFeature")
    result: dict[str, list[tuple[float, float, float]]] = {}
    for pf in plan_features:
        name = pf.get("name", "")
        if features is not None and name not in features:
            continue
        pts: list[tuple[float, float, float]] = []
        for line in find_all(pf, "Line"):
            start_el = find_one(line, "Start")
            end_el = find_one(line, "End")
            if start_el is None or end_el is None:
                continue
            if start_el.text is None or end_el.text is None:
                continue
            s = parse_coord(start_el.text)
            e_pt = parse_coord(end_el.text)
            if not pts:
                pts.append(s)
            # tuple float-equality OK: adjacent End/Start share bit-identical text values
            if e_pt != pts[-1]:
                pts.append(e_pt)
        if len(pts) >= 2:
            result[name] = pts

    if not result:
        available = [pf.get("name", "") for pf in plan_features]
        hint = f" Tilgjengelige PlanFeatures: {available}." if available else ""
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR,
            f"Ingen matchende PlanFeatures funnet i '{Path(path).name}'.{hint}",
        )

    return result, epsg
