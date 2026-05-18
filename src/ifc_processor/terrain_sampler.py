# src/ifc_processor/terrain_sampler.py
"""Hent eksisterende terrengprofil fra Kartverkets Høydedata-API (DTM1).

Bruker https://ws.geonorge.no/hoydedata/v1/punkt som er offentlig tilgjengelig
uten autentisering og støtter opptil 50 punkter per kall (UTM33 EUREF89).
"""
from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

import numpy as np

logger = logging.getLogger(__name__)

_KARTVERKET_URL = "https://ws.geonorge.no/hoydedata/v1/punkt"
_MAX_POINTS_PER_REQUEST = 50

# UTM33 EUREF89 (EPSG:25833) bounds for Norway.
# Vestlig Norge (rundt 5-9°E) gir easting < 200 000, derav romslig nedre grense.
_UTM33_EASTING_MIN  = -200_000.0
_UTM33_EASTING_MAX  = 1_200_000.0
_UTM33_NORTHING_MIN = 6_300_000.0
_UTM33_NORTHING_MAX = 7_950_000.0

# Log UTM33-range warning at most once per session to avoid spam
_utm33_warned: set[int] = set()


def _perp_axis(tangent: np.ndarray) -> np.ndarray:
    """Vinkelrett horisontal enhetsvektor (høyre side positiv u).

    Identisk logikk som _project_to_2d i cross_section.py slik at u-koordinater
    samsvarer direkte mellom IFC-geometri og terrengpunkter.
    """
    horiz = np.array([tangent[0], tangent[1], 0.0])
    n = np.linalg.norm(horiz)
    if n < 1e-9:
        return np.array([0.0, 1.0, 0.0])
    return np.cross(horiz / n, np.array([0.0, 0.0, 1.0]))


def _to_utm33(position: np.ndarray, source_epsg: int) -> np.ndarray | None:
    """Transformer 2D-posisjon fra source_epsg til UTM33 EUREF89 (EPSG:25833).

    Returnerer ny posisjon med UTM33 x/y og uendret z, eller None ved feil.
    Krever pyproj (installert via geopandas).
    """
    try:
        from pyproj import Transformer
        transformer = Transformer.from_crs(source_epsg, 25833, always_xy=True)
        x, y = transformer.transform(float(position[0]), float(position[1]))
        return np.array([x, y, float(position[2])])
    except ImportError:
        logger.warning(
            "pyproj ikke tilgjengelig — kan ikke transformere CRS %d → UTM33. "
            "Terrengdata vil ikke vises.",
            source_epsg,
        )
        return None
    except Exception as exc:
        logger.warning("CRS %d → UTM33 transformasjon feilet: %s", source_epsg, exc)
        return None


def _is_utm33(position: np.ndarray) -> bool:
    x, y = float(position[0]), float(position[1])
    return (
        _UTM33_EASTING_MIN  <= x <= _UTM33_EASTING_MAX
        and _UTM33_NORTHING_MIN <= y <= _UTM33_NORTHING_MAX
    )


def _query_kartverket(
    punkter: list[list[float]],
    timeout_s: float,
) -> list[dict]:
    """Gjør ett kall mot Kartverkets Høydedata-API og returner punktliste."""
    params = urllib.parse.urlencode({
        "koordsys": "25833",
        "punkter": json.dumps(punkter),
        "geojson": "false",
    })
    url = f"{_KARTVERKET_URL}?{params}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode())
    return data.get("punkter", [])


def fetch_terrain_profile(
    position: np.ndarray,
    tangent: np.ndarray,
    *,
    source_epsg: int = 25833,
    width_m: float = 80.0,
    sample_spacing_m: float = 2.0,
    timeout_s: float = 20.0,
) -> list[tuple[float, float]]:
    """Hent terrengprofil langs tverrprofil-snittet fra Kartverkets DTM1.

    Args:
        position:         3D senterlinjeposisjon i kilde-CRS (Easting, Northing, Z).
        tangent:          Normalisert tangentvektor langs senterlinjen.
        source_epsg:      EPSG-kode for koordinatsystemet til position (default: 25833 = UTM33).
                          Hvis annet enn 25833, transformeres koordinatene automatisk til UTM33
                          via pyproj før spørring mot Kartverket.
        width_m:          Total bredde å sample (fordelt likt på begge sider).
        sample_spacing_m: Avstand mellom terrengpunkter (meter, maks 50 punkter totalt).
        timeout_s:        HTTP-timeout i sekunder.

    Returns:
        Liste av (u, v) tupler sortert etter u:
        - u: horisontal avstand fra senterlinje (m), positiv = høyre side.
        - v: høyde i samme koordinatsystem som position.z (m).
        Tom liste ved feil, manglende data, eller koordinater utenfor Norge.
    """
    # --- Konverter til UTM33 for API-spørring ---
    if source_epsg == 25833:
        pos_utm33 = position
    else:
        pos_utm33 = _to_utm33(position, source_epsg)
        if pos_utm33 is None:
            return []

    # --- Sjekk at koordinatene er innenfor norsk UTM33-dekningsområde ---
    if not _is_utm33(pos_utm33):
        if source_epsg not in _utm33_warned:
            _utm33_warned.add(source_epsg)
            logger.warning(
                "Terrengsampling deaktivert: koordinater (%.0f E, %.0f N) er utenfor "
                "norsk UTM33N-område. "
                "Sjekk at senterlinjen er i UTM33 EUREF89 (EPSG:25833) — "
                "LandXML-filen oppgir EPSG:%d.",
                float(pos_utm33[0]), float(pos_utm33[1]),
                source_epsg,
            )
        return []

    perp = _perp_axis(tangent)
    half = width_m / 2.0
    n_pts = min(_MAX_POINTS_PER_REQUEST, max(2, round(width_m / sample_spacing_m) + 1))
    offsets = np.linspace(-half, half, n_pts)

    # Bygg UTM33-punkter langs den vinkelrette aksen
    punkter_utm = [
        [float(pos_utm33[0] + o * perp[0]), float(pos_utm33[1] + o * perp[1])]
        for o in offsets
    ]

    try:
        raw_pts = _query_kartverket(punkter_utm, timeout_s)
    except Exception as exc:
        logger.warning("Terrengforespørsel feilet (%.0f E, %.0f N): %s",
                       float(pos_utm33[0]), float(pos_utm33[1]), exc)
        return []

    if not raw_pts:
        logger.debug("Ingen terrengdata for (%.0f, %.0f)", float(pos_utm33[0]), float(pos_utm33[1]))
        return []

    station_z = float(position[2])
    result: list[tuple[float, float]] = []

    for p in raw_pts:
        sx, sy, sz = p.get("x"), p.get("y"), p.get("z")
        if sx is None or sy is None or sz is None:
            continue
        # u beregnes i UTM33-rommet (skala er tilnærmet lik kilde-CRS for 80 m bredde)
        delta_xy = np.array([float(sx) - float(pos_utm33[0]), float(sy) - float(pos_utm33[1])])
        u = float(np.dot(delta_xy, perp[:2]))
        v = float(sz) - station_z
        result.append((u, v))

    result.sort(key=lambda p: p[0])
    return result


def terrain_to_segments(
    points: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Konverter sortert liste med terrengpunkter til segmentliste for CrossSection.segments."""
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]
