# src/ifc_processor/centerline.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class Centerline:
    points: np.ndarray    # shape (M, 3): X, Y, Z i IFC lokalt koordinatsystem
    stations: np.ndarray  # shape (M,): kumulativ lengde i meter
    source_epsg: int = 25833  # EPSG-kode for koordinatsystemet (25833 = UTM33 EUREF89)

    @property
    def total_length(self) -> float:
        return float(self.stations[-1]) if len(self.stations) > 0 else 0.0

    @classmethod
    def from_points(cls, points: np.ndarray) -> "Centerline":
        return cls(points=points, stations=_stations_from_points(points))


def _stations_from_points(points: np.ndarray) -> np.ndarray:
    if len(points) < 2:
        raise ValueError(f"Senterlinje krever minst 2 punkter, fikk {len(points)}")
    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    if np.any(seg_lengths == 0):
        logger.warning("Senterlinje har duplikate punkter (0-lengde segmenter)")
    return np.concatenate([[0.0], np.cumsum(seg_lengths)])


def _load_from_geojson(path: Path) -> Centerline:
    data = json.loads(path.read_text())
    features = data.get("features", [data] if data.get("type") == "Feature" else [])
    for feat in features:
        geom = feat.get("geometry", feat)
        if geom.get("type") == "LineString":
            coords = geom["coordinates"]
            if not coords:
                raise ValueError(f"LineString i {path} har ingen koordinater")
            pts = np.array([[c[0], c[1], c[2] if len(c) > 2 else 0.0] for c in coords])
            return Centerline(points=pts, stations=_stations_from_points(pts))
    raise ValueError(f"Ingen LineString funnet i {path}")


def _sample_arc(
    s: tuple[float, float, float],
    e: tuple[float, float, float],
    c: tuple[float, float, float],
    rot: str,
    arc_len: float,
) -> list[tuple[float, float, float]]:
    """Sample punkter langs en sirkulær bue fra s til e rundt sentrum c."""
    import math
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


def _epsg_from_landxml_root(root, ns_uri: str) -> int:
    """Hent EPSG-kode fra LandXML <CoordinateSystem epsgCode="..."/>."""
    ns = {"lx": ns_uri} if ns_uri else {}
    cs = (
        root.find("lx:CoordinateSystem", ns) if ns_uri
        else root.find("CoordinateSystem")
    )
    if cs is None:
        # Prøv med jokertegn-namespace
        for child in root:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag == "CoordinateSystem":
                cs = child
                break
    if cs is not None:
        code = cs.get("epsgCode")
        if code:
            try:
                epsg = int(code)
                if epsg != 25833:
                    logger.info(
                        "LandXML bruker EPSG:%d (ikke UTM33) — "
                        "terrengsampling krever koordinattransformasjon",
                        epsg,
                    )
                return epsg
            except ValueError:
                pass
    return 25833  # ukjent → anta UTM33


def _load_from_landxml(path: Path) -> Centerline:
    """Les LandXML 1.2 — støtter PlanFeature/CoordGeom og Alignment/CoordGeom
    med Line- og Curve-elementer (sirkulære buer samples med ~5 m oppløsning).

    LandXML bruker (Northing, Easting, Z) — konverteres til (Easting, Northing, Z).
    """
    import math
    import xml.etree.ElementTree as ET

    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"Ugyldig XML i {path}: {exc}") from exc

    root = tree.getroot()
    ns_uri = ""
    if root.tag.startswith("{"):
        ns_uri = root.tag.split("}")[0][1:]
    ns = {"lx": ns_uri} if ns_uri else {}

    source_epsg = _epsg_from_landxml_root(root, ns_uri)

    def find_all(parent, tag):
        return parent.findall(f".//lx:{tag}", ns) if ns_uri else parent.findall(f".//{tag}")

    def child_find(el, tag):
        return el.find(f"lx:{tag}", ns) if ns_uri else el.find(tag)

    def parse_coord(text: str) -> tuple[float, float, float]:
        parts = text.strip().split()
        n, e = float(parts[0]), float(parts[1])
        z = float(parts[2]) if len(parts) > 2 else 0.0
        return e, n, z  # Northing/Easting-swap → (X, Y, Z)

    raw_pts: list[tuple[float, float, float]] = []

    for coord_geom in find_all(root, "CoordGeom"):
        for seg in coord_geom:
            tag = seg.tag.split("}")[-1] if "}" in seg.tag else seg.tag
            s_el = child_find(seg, "Start")
            e_el = child_find(seg, "End")
            if s_el is None or e_el is None or not s_el.text or not e_el.text:
                continue
            s = parse_coord(s_el.text)
            e = parse_coord(e_el.text)
            if not raw_pts:
                raw_pts.append(s)
            if tag == "Curve":
                c_el = child_find(seg, "Center")
                if c_el is not None and c_el.text:
                    c = parse_coord(c_el.text)
                    rot = seg.get("rot", "ccw")
                    arc_len = float(seg.get("length") or
                                    math.hypot(e[0] - s[0], e[1] - s[1]))
                    for pt in _sample_arc(s, e, c, rot, arc_len):
                        if pt != raw_pts[-1]:
                            raw_pts.append(pt)
                    continue
            if e != raw_pts[-1]:
                raw_pts.append(e)

    if not raw_pts:
        raise ValueError(f"Ingen Line/Curve-elementer i CoordGeom funnet i {path}")

    pts_arr = np.array(raw_pts)
    mask = np.ones(len(pts_arr), dtype=bool)
    mask[1:] = np.any(pts_arr[1:] != pts_arr[:-1], axis=1)
    pts_arr = pts_arr[mask]

    logger.info("LandXML: leste %d punkter fra %s (EPSG:%d)", len(pts_arr), path.name, source_epsg)
    return Centerline(points=pts_arr, stations=_stations_from_points(pts_arr), source_epsg=source_epsg)


def _load_from_csv(path: Path) -> Centerline:
    try:
        pts = np.loadtxt(path, delimiter=",", usecols=(0, 1, 2))
    except (ValueError, IndexError) as exc:
        raise ValueError(
            f"Kan ikke lese senterlinje fra {path}: {exc}. "
            "Forventet format: X,Y,Z per linje, minst 3 kolonner."
        ) from exc
    if pts.ndim == 1:
        pts = pts.reshape(1, 3)
    return Centerline(points=pts, stations=_stations_from_points(pts))


def _try_ifc_alignment(ifc_path: Path) -> Centerline | None:
    try:
        import ifcopenshell
        ifc = ifcopenshell.open(str(ifc_path))
        alignments = ifc.by_type("IfcAlignment")
        if not alignments:
            return None
        al = alignments[0]
        reps = getattr(al, "Representation", None)
        if reps is None:
            return None
        for rep in reps.Representations:
            for item in rep.Items:
                if item.is_a("IfcPolyline"):
                    pts = np.array([[p.Coordinates[0], p.Coordinates[1],
                                     p.Coordinates[2] if len(p.Coordinates) > 2 else 0.0]
                                    for p in item.Points])
                    return Centerline(points=pts, stations=_stations_from_points(pts))
    except Exception as exc:
        logger.warning("Kan ikke lese IfcAlignment: %s", exc)
    return None


def derive_centerline_from_ifc(ifc_path: Path, layer_keyword: str = "kjørefelt", n_slices: int = 200) -> Centerline:
    """Deriver senterlinje fra IFC-overflate-TIN via PCA-midtpunkt-metode.

    Finner TINer der Layer inneholder `layer_keyword` (f.eks. "kjørefelt"),
    bruker PCA til å finne vegens primærretning, skjærer langs denne og
    finner midtpunktet i tverrretningen for hvert snitt.

    Args:
        ifc_path:      Sti til IFC-fil.
        layer_keyword: Nøkkelord i Layer-navnet (ikke skift-sensitivt).
        n_slices:      Antall samplepunkter langs vegens lengderetning.

    Returns:
        Centerline med 3D-punkter.

    Raises:
        ValueError: Hvis ingen TINer med `layer_keyword` finnes.
    """
    from .ifc_reader import read_ifc_tins

    tins = read_ifc_tins(ifc_path)
    keyword_lower = layer_keyword.lower()
    surface_tins = [t for t in tins if keyword_lower in t.layer.lower()]

    if not surface_tins:
        available = sorted({t.layer for t in tins})
        raise ValueError(
            f"Ingen TINer med '{layer_keyword}' i Layer-navn. "
            f"Tilgjengelige lag: {available}"
        )

    logger.info("Deriverer senterlinje fra %d '%s'-TINer", len(surface_tins), layer_keyword)

    # Hent alle 3D-hjørnepunkter
    all_pts = np.vstack([t.triangles.reshape(-1, 3) for t in surface_tins])

    # PCA: finn primærretning (langs vegen) og sekundærretning (tvers)
    pts_2d = all_pts[:, :2]
    mean_2d = pts_2d.mean(axis=0)
    centered = pts_2d - mean_2d
    cov = np.cov(centered.T)
    eigvals, eigvecs = np.linalg.eigh(cov)
    primary = eigvecs[:, -1]    # langs vegen (størst varians)
    secondary = eigvecs[:, -2]  # tvers på vegen

    along = centered @ primary   # projeksjoner langs primærretning
    across = centered @ secondary

    # Skjær langs primærretningen og finn midtpunkt i tverrretningen
    s_min, s_max = along.min(), along.max()
    slice_centers = np.linspace(s_min, s_max, n_slices + 2)[1:-1]
    window = (s_max - s_min) / n_slices * 2.0

    centerline_pts: list[np.ndarray] = []
    for s in slice_centers:
        mask = np.abs(along - s) < window
        if mask.sum() < 3:
            continue
        mid_across = (across[mask].min() + across[mask].max()) / 2.0
        center_2d = mean_2d + s * primary + mid_across * secondary
        z = float(all_pts[mask, 2].mean())
        centerline_pts.append(np.array([center_2d[0], center_2d[1], z]))

    if len(centerline_pts) < 2:
        raise ValueError("For få snitt med data til å danne en senterlinje")

    pts_arr = np.array(centerline_pts)
    logger.info("Senterlinje derivert: %d punkter, %.1f m", len(pts_arr),
                np.sum(np.linalg.norm(np.diff(pts_arr, axis=0), axis=1)))
    return Centerline(points=pts_arr, stations=_stations_from_points(pts_arr))


def _medial_axis_from_tins(tins: list) -> Centerline:
    all_pts = np.vstack([t.triangles.reshape(-1, 3)[:, :2] for t in tins])
    from shapely.geometry import MultiPoint
    footprint = MultiPoint(all_pts).convex_hull
    logger.warning("Bruker forenklet medialakse-fallback — resultat kan være unøyaktig")
    pts = np.array([[c[0], c[1], 0.0] for c in list(footprint.exterior.coords)[::5]])
    return Centerline(points=pts, stations=_stations_from_points(pts))


def load_vertical_profile(path: Path) -> list[tuple[float, float]] | None:
    """Parse LandXML ProfAlign → sortert [(stasjon_m, kotehøyde_m), ...].

    Leser PVI- og CircCurve-elementer fra første ProfAlign i filen.
    Returnerer None dersom filen ikke er LandXML eller ingen ProfAlign finnes.
    """
    if path.suffix.lower() != ".xml":
        return None
    import xml.etree.ElementTree as ET
    try:
        tree = ET.parse(path)
    except ET.ParseError:
        return None
    root = tree.getroot()
    ns_uri = root.tag.split("}")[0][1:] if root.tag.startswith("{") else ""
    ns = {"lx": ns_uri} if ns_uri else {}

    def find_all(parent, tag):
        return parent.findall(f".//lx:{tag}", ns) if ns_uri else parent.findall(f".//{tag}")

    pts: list[tuple[float, float]] = []
    for prof_align in find_all(root, "ProfAlign"):
        for child in prof_align:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            if tag in ("PVI", "CircCurve") and child.text:
                parts = child.text.strip().split()
                if len(parts) >= 2:
                    try:
                        pts.append((float(parts[0]), float(parts[1])))
                    except ValueError:
                        pass
        if pts:
            break  # bruk kun første ProfAlign

    if not pts:
        return None
    pts.sort(key=lambda p: p[0])
    logger.info(
        "LandXML vertikalprofil: %d PVI-punkt(er), Z=[%.2f..%.2f] m",
        len(pts), pts[0][1], pts[-1][1],
    )
    return pts


def load_centerline(source: Path | None, ifc_path: Path) -> Centerline:
    """Last senterlinje.

    Prioritering:
    1. Eksplisitt kildefil (GeoJSON eller CSV)
    2. IfcAlignment i IFC 4.3-fil
    3. Medialakse fra Planum-TINer (upresist fallback)

    Raises:
        ValueError: hvis ingen senterlinje kan bestemmes
    """
    if source is not None:
        suffix = source.suffix.lower()
        if suffix in (".geojson", ".json"):
            return _load_from_geojson(source)
        if suffix == ".csv":
            return _load_from_csv(source)
        if suffix == ".xml":
            return _load_from_landxml(source)
        if suffix == ".ifc":
            from .alignment_parser import load_alignment_from_ifc
            return load_alignment_from_ifc(source).to_centerline()
        raise ValueError(
            f"Ukjent senterlinje-format: {suffix}. "
            "Godkjente formater: .geojson, .csv, .xml (LandXML), .ifc (IFC4X3)"
        )

    if ifc_path.exists():
        cl = _try_ifc_alignment(ifc_path)
        if cl is not None:
            logger.info("Bruker IfcAlignment fra IFC-fil")
            return cl

        try:
            from .ifc_reader import read_ifc_tins
            tins = read_ifc_tins(ifc_path)
            planum = [t for t in tins if t.road_class == "planum"]
            if planum:
                logger.warning("Ingen eksplisitt senterlinje — faller tilbake til medialakse fra Planum")
                return _medial_axis_from_tins(planum)
        except Exception as exc:
            logger.warning("Medialakse-fallback feilet: %s", exc)

    raise ValueError(
        "Ingen senterlinje funnet. Oppgi senterlinje som:\n"
        "  --centerline senterlinje.geojson   (GeoJSON med LineString)\n"
        "  --centerline senterlinje.xml        (LandXML 1.2 med PlanFeature/Line)\n"
        "  --centerline stasjoner.csv          (X,Y,Z per linje)"
    )
