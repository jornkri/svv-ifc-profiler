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


def _load_from_landxml(path: Path) -> Centerline:
    """Les LandXML 1.2 PlanFeature/CoordGeom/Line-struktur.

    LandXML bruker (Northing, Easting, Z) — konverteres til (Easting, Northing, Z)
    slik at koordinatene matcher IFC-modellens lokale system.
    """
    import xml.etree.ElementTree as ET

    # Støtt både med og uten LandXML-namespace
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        raise ValueError(f"Ugyldig XML i {path}: {exc}") from exc

    root = tree.getroot()
    ns_uri = ""
    if root.tag.startswith("{"):
        ns_uri = root.tag.split("}")[0][1:]
    ns = {"lx": ns_uri} if ns_uri else {}

    def find_all(parent, tag):
        if ns_uri:
            return parent.findall(f".//lx:{tag}", ns)
        return parent.findall(f".//{tag}")

    def parse_coord(text: str) -> tuple[float, float, float]:
        parts = text.strip().split()
        # LandXML: Northing Easting [Z]
        n, e = float(parts[0]), float(parts[1])
        z = float(parts[2]) if len(parts) > 2 else 0.0
        return e, n, z  # → (X, Y, Z) som samsvarer med IFC

    # Hent alle linjestykker og kjed dem til én sammenhengende polyline
    raw_pts: list[tuple[float, float, float]] = []

    for line in find_all(root, "Line"):
        start_el = line.find("lx:Start", ns) if ns_uri else line.find("Start")
        end_el = line.find("lx:End", ns) if ns_uri else line.find("End")
        if start_el is None or end_el is None:
            continue
        s = parse_coord(start_el.text)
        e = parse_coord(end_el.text)
        if not raw_pts:
            raw_pts.append(s)
        raw_pts.append(e)

    if not raw_pts:
        raise ValueError(f"Ingen Line-elementer funnet i {path}")

    # Fjern duplikate konsekutive punkter
    pts_arr = np.array(raw_pts)
    mask = np.ones(len(pts_arr), dtype=bool)
    mask[1:] = np.any(pts_arr[1:] != pts_arr[:-1], axis=1)
    pts_arr = pts_arr[mask]

    logger.info("LandXML: leste %d punkter fra %s", len(pts_arr), path.name)
    return Centerline(points=pts_arr, stations=_stations_from_points(pts_arr))


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
        raise ValueError(f"Ukjent senterlinje-format: {suffix}. Godkjente formater: .geojson, .csv, .xml (LandXML)")

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
