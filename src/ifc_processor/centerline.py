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


def _stations_from_points(points: np.ndarray) -> np.ndarray:
    diffs = np.diff(points, axis=0)
    seg_lengths = np.linalg.norm(diffs, axis=1)
    return np.concatenate([[0.0], np.cumsum(seg_lengths)])


def _load_from_geojson(path: Path) -> Centerline:
    data = json.loads(path.read_text())
    features = data.get("features", [data] if data.get("type") == "Feature" else [])
    for feat in features:
        geom = feat.get("geometry", feat)
        if geom.get("type") == "LineString":
            coords = geom["coordinates"]
            pts = np.array([[c[0], c[1], c[2] if len(c) > 2 else 0.0] for c in coords])
            return Centerline(points=pts, stations=_stations_from_points(pts))
    raise ValueError(f"Ingen LineString funnet i {path}")


def _load_from_csv(path: Path) -> Centerline:
    pts = np.loadtxt(path, delimiter=",", usecols=(0, 1, 2))
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
        raise ValueError(f"Ukjent senterlinje-format: {suffix}. Godkjente formater: .geojson, .csv")

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
        "  --centerline stasjoner.csv          (X,Y,Z per linje)"
    )
