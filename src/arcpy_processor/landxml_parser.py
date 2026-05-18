# src/arcpy_processor/landxml_parser.py
from __future__ import annotations

import math
import xml.etree.ElementTree as ET
from pathlib import Path

from .errors import ArcpyProcessorError, LANDXML_PARSE_ERROR


def _sample_arc(
    s: tuple[float, float, float],
    e: tuple[float, float, float],
    c: tuple[float, float, float],
    rot: str,
    arc_len: float,
) -> list[tuple[float, float, float]]:
    cx, cy = c[0], c[1]
    r = math.hypot(s[0] - cx, s[1] - cy)
    theta_s = math.atan2(s[1] - cy, s[0] - cx)
    theta_e = math.atan2(e[1] - cy, e[0] - cx)
    if rot == "cw":
        if theta_e > theta_s:
            theta_e -= 2 * math.pi
    else:
        if theta_e < theta_s:
            theta_e += 2 * math.pi
    n = max(2, int(arc_len / 5))
    pts: list[tuple[float, float, float]] = []
    for i in range(1, n + 1):
        t = i / n
        theta = theta_s + t * (theta_e - theta_s)
        pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta), s[2] + t * (e[2] - s[2])))
    return pts


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

    def _extract_pts_from_geom(parent: ET.Element) -> list[tuple[float, float, float]]:
        """Ekstraherer punkter fra CoordGeom Line- og Curve-elementer.
        Curve-buer samples med ~5 m oppløsning via sentrum og rotasjonsretning.
        """
        pts: list[tuple[float, float, float]] = []
        for seg in list(parent):
            tag = seg.tag.split("}")[-1] if "}" in seg.tag else seg.tag
            if tag not in ("Line", "Curve"):
                continue
            start_el = find_one(seg, "Start")
            end_el = find_one(seg, "End")
            if start_el is None or end_el is None:
                continue
            if start_el.text is None or end_el.text is None:
                continue
            s = parse_coord(start_el.text)
            e_pt = parse_coord(end_el.text)
            if not pts:
                pts.append(s)
            if tag == "Curve":
                center_el = find_one(seg, "Center")
                if center_el is not None and center_el.text:
                    c = parse_coord(center_el.text)
                    rot = seg.get("rot", "ccw")
                    arc_len = float(seg.get("length") or
                                    math.hypot(e_pt[0] - s[0], e_pt[1] - s[1]))
                    for pt in _sample_arc(s, e_pt, c, rot, arc_len):
                        if pt != pts[-1]:
                            pts.append(pt)
                    continue
            if e_pt != pts[-1]:
                pts.append(e_pt)
        return pts

    result: dict[str, list[tuple[float, float, float]]] = {}

    # --- PlanFeatures (FV229 / Gemini-format) ---
    plan_features = find_all(root, "PlanFeature")
    for pf in plan_features:
        name = pf.get("name", "")
        if features is not None and name not in features:
            continue
        geom_el = find_one(pf, "CoordGeom")
        parent = geom_el if geom_el is not None else pf
        pts = _extract_pts_from_geom(parent)
        if len(pts) >= 2:
            result[name] = pts

    # --- Alignments (Quadri / Novapoint-format) ---
    if not result:
        for al in find_all(root, "Alignment"):
            name = al.get("name", "")
            if features is not None and name not in features:
                continue
            geom_el = find_one(al, "CoordGeom")
            if geom_el is None:
                continue
            pts = _extract_pts_from_geom(geom_el)
            if len(pts) >= 2:
                result[name] = pts

    if not result:
        available_pf = [pf.get("name", "") for pf in plan_features]
        available_al = [al.get("name", "") for al in find_all(root, "Alignment")]
        available = available_pf or available_al
        hint = f" Tilgjengelige features: {available}." if available else ""
        raise ArcpyProcessorError(
            LANDXML_PARSE_ERROR,
            f"Ingen matchende PlanFeatures eller Alignments funnet i '{Path(path).name}'.{hint}",
        )

    return result, epsg
