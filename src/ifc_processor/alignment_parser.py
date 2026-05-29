# src/ifc_processor/alignment_parser.py
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import ifcopenshell
import ifcopenshell.geom
import numpy as np

logger = logging.getLogger(__name__)

_SAMPLE_INTERVAL_M = 1.0


@dataclass
class HorizontalSegment:
    start_station: float
    length: float
    start_point: tuple[float, float]
    start_direction: float                 # radianer
    segment_type: str                      # "LINE" | "CIRCULARARC" | "CLOTHOID"
    start_radius: float | None = None
    end_radius: float | None = None
    is_ccw: bool | None = None


@dataclass
class VerticalSegment:
    start_station: float
    length: float
    start_height: float
    start_gradient: float                  # m/m
    segment_type: str                      # "CONSTANTGRADIENT" | "PARABOLICARC" | "CIRCULARARC"
    radius: float | None = None            # signert: + dal, − topp


@dataclass
class StationLabel:
    station: float
    name: str
    position: tuple[float, float, float]


@dataclass
class IfcAlignmentData:
    name: str
    points_3d: np.ndarray                  # (M, 3)
    stations: np.ndarray                   # (M,)
    horizontal_segments: list[HorizontalSegment] = field(default_factory=list)
    vertical_segments: list[VerticalSegment] = field(default_factory=list)
    station_labels: list[StationLabel] = field(default_factory=list)
    source_epsg: int = 25833

    def to_centerline(self) -> "Centerline":
        from .centerline import Centerline
        return Centerline(
            points=self.points_3d,
            stations=self.stations,
            source_epsg=self.source_epsg,
        )

    def vertical_profile_pvi(self) -> list[tuple[float, float]]:
        """Returner [(stasjon, høyde)] som matcher load_vertical_profile()-formatet."""
        if not self.vertical_segments:
            return []
        pvi: list[tuple[float, float]] = []
        for seg in self.vertical_segments:
            pvi.append((seg.start_station, seg.start_height))
        last = self.vertical_segments[-1]
        end_station = last.start_station + last.length
        end_height = last.start_height + last.start_gradient * last.length
        pvi.append((end_station, end_height))
        return pvi


# ---------------------------------------------------------------------------
# IFC loading helpers
# ---------------------------------------------------------------------------

_VALID_SCHEMAS = {"IFC4X3", "IFC4X3_ADD1", "IFC4X3_ADD2", "IFC4X3_TC1"}

_HORIZONTAL_TYPE_MAP = {
    "LINE": "LINE",
    "CIRCULARARC": "CIRCULARARC",
    "CLOTHOID": "CLOTHOID",
    "CLOTHOIDCURVE": "CLOTHOID",
    "CUBICSPIRAL": "CLOTHOID",
    "BLOSSCURVE": "CLOTHOID",
    "COSINECURVE": "CLOTHOID",
    "SINECURVE": "CLOTHOID",
    "VIENNESEBEND": "CLOTHOID",
    "HELMERTCURVE": "CLOTHOID",
}


def _find_horizontal(alignment):
    """Return the IfcAlignmentHorizontal nested under *alignment*, or None."""
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentHorizontal"):
                return obj
    return None


def _extract_horizontal_segments(horizontal) -> list[HorizontalSegment]:
    if horizontal is None:
        return []
    segments: list[HorizontalSegment] = []
    cum_station = 0.0
    nested_segs: list = []
    for rel in horizontal.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentSegment"):
                nested_segs.append(obj)

    for seg in nested_segs:
        params = seg.DesignParameters
        if params is None or not params.is_a("IfcAlignmentHorizontalSegment"):
            continue

        raw_type = (params.PredefinedType or "").upper()
        seg_type = _HORIZONTAL_TYPE_MAP.get(raw_type)
        if seg_type is None:
            logger.warning(
                "Ukjent horisontal segment-type '%s' — behandler som CLOTHOID",
                raw_type,
            )
            seg_type = "CLOTHOID"

        start_pt = (
            float(params.StartPoint.Coordinates[0]),
            float(params.StartPoint.Coordinates[1]),
        )
        start_dir = float(params.StartDirection or 0.0)
        length = float(params.SegmentLength or 0.0)
        start_r = params.StartRadiusOfCurvature
        end_r = params.EndRadiusOfCurvature

        # IFC4X3 konvensjon: signert radius → fortegn bestemmer retning
        is_ccw: bool | None = None
        if start_r is not None and start_r != 0.0:
            is_ccw = float(start_r) > 0.0
        elif end_r is not None and end_r != 0.0:
            is_ccw = float(end_r) > 0.0

        segments.append(HorizontalSegment(
            start_station=cum_station,
            length=length,
            start_point=start_pt,
            start_direction=start_dir,
            segment_type=seg_type,
            start_radius=abs(float(start_r)) if start_r else None,
            end_radius=abs(float(end_r)) if end_r else None,
            is_ccw=is_ccw,
        ))
        cum_station += length

    return segments


def _find_vertical(alignment):
    """Return the IfcAlignmentVertical nested under *alignment*, or None."""
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentVertical"):
                return obj
    return None


def _extract_vertical_segments(vertical) -> list[VerticalSegment]:
    if vertical is None:
        return []
    segments: list[VerticalSegment] = []
    nested_segs: list = []
    for rel in vertical.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcAlignmentSegment"):
                nested_segs.append(obj)

    for seg in nested_segs:
        params = seg.DesignParameters
        if params is None or not params.is_a("IfcAlignmentVerticalSegment"):
            continue

        raw_type = (params.PredefinedType or "").upper()
        if raw_type not in ("CONSTANTGRADIENT", "PARABOLICARC", "CIRCULARARC"):
            logger.warning(
                "Ukjent vertikal segment-type '%s' — behandler som CONSTANTGRADIENT",
                raw_type,
            )
            raw_type = "CONSTANTGRADIENT"

        start_station = float(params.StartDistAlong or 0.0)
        length = float(params.HorizontalLength or 0.0)
        start_height = float(params.StartHeight or 0.0)
        start_grad = float(params.StartGradient or 0.0)
        end_grad = float(params.EndGradient or start_grad)

        radius: float | None = None
        if raw_type in ("PARABOLICARC", "CIRCULARARC"):
            r_raw = params.RadiusOfCurvature
            if r_raw is not None and r_raw != 0.0:
                # Tegn-konvensjon: konkav (dal, gradient øker) → +, konveks (topp) → −
                sign = 1.0 if (end_grad - start_grad) > 0 else -1.0
                radius = sign * abs(float(r_raw))

        segments.append(VerticalSegment(
            start_station=start_station,
            length=length,
            start_height=start_height,
            start_gradient=start_grad,
            segment_type=raw_type,
            radius=radius,
        ))

    return segments


def _select_alignment(ifc):
    """Pick the single IfcAlignment in *ifc*, or the longest if multiple exist.

    Raises ValueError if none are found.
    """
    alignments = ifc.by_type("IfcAlignment")
    if not alignments:
        types = sorted({e.is_a() for e in ifc})
        raise ValueError(
            f"Ingen IfcAlignment funnet — er dette en vegmodell-IFC? "
            f"Topp-typer i filen: {types[:10]}{'...' if len(types) > 10 else ''}"
        )
    if len(alignments) == 1:
        return alignments[0]

    def total_len(al):
        h = _find_horizontal(al)
        if h is None:
            return 0.0
        return sum(
            (seg.DesignParameters.SegmentLength or 0.0)
            for rel in h.IsNestedBy
            for seg in rel.RelatedObjects
            if seg.is_a("IfcAlignmentSegment") and seg.DesignParameters is not None
        )

    chosen = max(alignments, key=total_len)
    logger.info(
        "Flere IfcAlignment i fil — valgte '%s'. Andre: %s",
        chosen.Name,
        [a.Name for a in alignments if a is not chosen],
    )
    return chosen


def _extract_station_labels(
    alignment,
    points_3d: np.ndarray,
    stations: np.ndarray,
) -> list[StationLabel]:
    """Hent IfcReferent som er nestet under alignment.

    IFC4X3 struktur (m_f-veg_12200_CL.ifc):
      IfcReferent.ObjectPlacement  → IfcLinearPlacement
        .RelativePlacement          → IfcAxis2PlacementLinear
          .Location                 → IfcPointByDistanceExpression
            .DistanceAlong          → IfcLengthMeasure (wrappedValue = float)

    Stasjonen er DistanceAlong-verdien (offset fra start av alignment).
    Negative verdier (referenter før alignment-start) filtreres bort.
    3D-posisjon interpoleres på samplede points_3d.
    """
    referents: list = []
    for rel in alignment.IsNestedBy:
        for obj in rel.RelatedObjects:
            if obj.is_a("IfcReferent"):
                referents.append(obj)

    labels: list[StationLabel] = []
    for ref in referents:
        placement = getattr(ref, "ObjectPlacement", None)
        if placement is None or not placement.is_a("IfcLinearPlacement"):
            continue

        # Primary path: RelativePlacement → IfcAxis2PlacementLinear → Location → DistanceAlong
        station_val: float | None = None
        rel_pl = getattr(placement, "RelativePlacement", None)
        if rel_pl is not None:
            loc = getattr(rel_pl, "Location", None)
            if loc is not None:
                da = getattr(loc, "DistanceAlong", None)
                if da is not None:
                    if hasattr(da, "wrappedValue"):
                        station_val = float(da.wrappedValue)
                    elif isinstance(da, (int, float)):
                        station_val = float(da)
                    else:
                        try:
                            station_val = float(da)
                        except (TypeError, ValueError):
                            pass

        # Fallback path: Distance attribute (older IFC4X3 drafts)
        if station_val is None:
            dist_attr = getattr(placement, "Distance", None)
            if dist_attr is not None:
                if hasattr(dist_attr, "DistanceAlong"):
                    raw = dist_attr.DistanceAlong
                    station_val = float(raw.wrappedValue) if hasattr(raw, "wrappedValue") else float(raw)
                elif hasattr(dist_attr, "wrappedValue"):
                    station_val = float(dist_attr.wrappedValue)
                elif isinstance(dist_attr, (int, float)):
                    station_val = float(dist_attr)

        if station_val is None:
            logger.debug("IfcReferent '%s': kan ikke lese DistanceAlong — hopper over", ref.Name)
            continue

        # Skip referents that lie before the alignment start
        if station_val < 0.0:
            logger.debug(
                "IfcReferent '%s': DistanceAlong=%.3f < 0 — hopper over",
                ref.Name, station_val,
            )
            continue

        station = station_val

        if stations.size >= 2:
            x = float(np.interp(station, stations, points_3d[:, 0]))
            y = float(np.interp(station, stations, points_3d[:, 1]))
            z = float(np.interp(station, stations, points_3d[:, 2]))
            pos = (x, y, z)
        else:
            pos = (0.0, 0.0, 0.0)

        name = ref.Name or f"P {station:.0f}"
        labels.append(StationLabel(
            station=station,
            name=name,
            position=pos,
        ))

    labels.sort(key=lambda sl: sl.station)
    return labels


def _find_curve3d_representation(alignment):
    """Return the Curve3D IfcShapeRepresentation for *alignment*, or None.

    IfcAlignment in IFC4X3 typically carries two representations:
    - 'Curve3D' — the IfcGradientCurve (3D, used for sampling)
    - 'Curve2D' / 'FootPrint' — horizontal projection only

    ifcopenshell.geom.create_shape() picks the first representation it can
    process; on this IFC file that is the Curve2D which causes a RuntimeError.
    We must pass the Curve3D representation explicitly.
    """
    if alignment.Representation is None:
        return None
    for rep in alignment.Representation.Representations:
        if rep.RepresentationType == "Curve3D":
            return rep
    return None


def _sample_alignment_3d(
    alignment,
    horizontal_segments: list[HorizontalSegment],
) -> tuple[np.ndarray, np.ndarray]:
    """Returner (M,3) 3D-punkter + (M,) kumulative stasjoner.

    Bruker ifcopenshell.geom på IfcAlignment for å få ut Curve3D-polylinje
    (representerer IfcGradientCurve). Resampler til ~1 m intervall.
    """
    settings = ifcopenshell.geom.settings()
    # IFC4X3 alignment geometri evalueres som kurver; sett flagg der mulig
    try:
        settings.set(settings.INCLUDE_CURVES, True)
    except AttributeError:
        try:
            settings.set("include-curves", True)
        except Exception:
            pass

    # Must pass the Curve3D representation explicitly; create_shape without it
    # defaults to Curve2D/FootPrint which raises RuntimeError.
    curve3d_rep = _find_curve3d_representation(alignment)
    if curve3d_rep is None:
        raise ValueError(
            f"IfcAlignment '{alignment.Name}' mangler Curve3D-representasjon."
        )

    try:
        shape = ifcopenshell.geom.create_shape(settings, alignment, curve3d_rep)
    except RuntimeError as exc:
        raise ValueError(
            f"Kan ikke evaluere geometri for IfcAlignment '{alignment.Name}': {exc}"
        ) from exc

    verts = np.array(shape.geometry.verts, dtype=float).reshape(-1, 3)
    if verts.shape[0] < 2:
        raise ValueError(
            f"IfcAlignment '{alignment.Name}' produserte for få 3D-punkter ({verts.shape[0]})"
        )

    diffs = np.diff(verts, axis=0)
    seg_lens = np.linalg.norm(diffs, axis=1)
    raw_stations = np.concatenate([[0.0], np.cumsum(seg_lens)])

    total_len = float(raw_stations[-1])
    if total_len <= 0:
        return verts, raw_stations
    n_samples = max(2, int(np.ceil(total_len / _SAMPLE_INTERVAL_M)) + 1)
    target_stations = np.linspace(0.0, total_len, n_samples)
    resampled = np.column_stack([
        np.interp(target_stations, raw_stations, verts[:, i]) for i in range(3)
    ])
    return resampled, target_stations


def load_alignment_from_ifc(ifc_path: Path) -> IfcAlignmentData:
    """Les IFC4X3 IfcAlignment og returner felles datakontrakt.

    Raises:
        ValueError: filen er ikke IFC4X3, mangler IfcAlignment, eller alignment er tom.
    """
    ifc = ifcopenshell.open(str(ifc_path))
    if ifc.schema not in _VALID_SCHEMAS:
        raise ValueError(
            f"IFC4X3 kreves for senterlinje-IFC. Fil-schema: {ifc.schema}. "
            "Bruk LandXML-senterlinje for IFC4-modeller."
        )

    alignment = _select_alignment(ifc)
    name = alignment.Name or "<ukjent>"

    h = _find_horizontal(alignment)
    horizontal_segments = _extract_horizontal_segments(h)
    if not horizontal_segments:
        raise ValueError(
            f"IfcAlignment '{name}' har ingen horisontalsegmenter."
        )

    v = _find_vertical(alignment)
    vertical_segments = _extract_vertical_segments(v)

    points_3d, stations = _sample_alignment_3d(alignment, horizontal_segments)

    station_labels = _extract_station_labels(alignment, points_3d, stations)

    logger.info(
        "alignment_parser: Lastet '%s' (%d hor.seg, %d vert.seg, %d referenter, %.1f m)",
        name, len(horizontal_segments), len(vertical_segments),
        len(station_labels), float(stations[-1]) if stations.size else 0.0,
    )

    return IfcAlignmentData(
        name=name,
        points_3d=points_3d,
        stations=stations,
        horizontal_segments=horizontal_segments,
        vertical_segments=vertical_segments,
        station_labels=station_labels,
    )
