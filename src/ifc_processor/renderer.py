# src/ifc_processor/renderer.py
from __future__ import annotations

import logging
import math
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.ticker import MultipleLocator

from .cross_section import CrossSection
from .longitudinal_profile import LongitudinalProfile
from .normal_section import compute_normal_section

logger = logging.getLogger(__name__)

# R700 line styles per road component
_STYLE: dict[str, dict] = {
    "planum":      {"color": "black",   "linewidth": 2.0, "linestyle": "-",  "zorder": 5},
    "kjørefelt":   {"color": "#111111", "linewidth": 1.5, "linestyle": "-",  "zorder": 4},
    "skulder":     {"color": "#333333", "linewidth": 1.0, "linestyle": "-",  "zorder": 4},
    "kantstein":   {"color": "black",   "linewidth": 1.5, "linestyle": "-",  "zorder": 4},
    "gang_sykkel": {"color": "#444444", "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "skjaering":   {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "fylling":     {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "groft":       {"color": "black",   "linewidth": 1.0, "linestyle": "-",  "zorder": 3},
    "terreng":     {"color": "black",   "linewidth": 0.8, "linestyle": "-",  "zorder": 2},
    "unknown":     {"color": "#888888", "linewidth": 0.5, "linestyle": "--", "zorder": 1},
}

# Avstand mellom tikk-merker og tikk-lengde for R700 TerrengrofilJord (meter, modellenhet).
# R700 Vedlegg 3: tikklengde ≈ 25 % av intervallet, dvs. ~0.25 m ved 1 m intervall.
_TERRAIN_TICK_INTERVAL = 1.0   # 1 m = 5 mm på papir ved 1:200
_TERRAIN_TICK_LEN      = 0.25  # R700 TerrengrofilJord: kort tikk, ikke dominerende


def _draw_terrain_chain(ax, chain: list[tuple[float, float]]) -> None:
    """R700 TerrengrofilJord: hel linje + korte skråstreker ved fast vinkel.

    Tikkene resamples langs hele kjedens totale buelengde slik at de fordeles
    jevnt uavhengig av enkelt-segmentlengder fra TIN-snittet.  Uten dette gir
    korte TIN-triangler klynger av tikker med store gap mellom.
    """
    if len(chain) < 2:
        return
    us = [p[0] for p in chain]
    vs = [p[1] for p in chain]
    ax.plot(us, vs, color="black", linewidth=0.8, linestyle="-", zorder=2)

    seg_lengths = [
        math.hypot(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
        for i in range(len(chain) - 1)
    ]
    total_len = sum(seg_lengths)
    if total_len < 1e-6:
        return

    # R700 TerrengrofilJord: tikkene peker skrått opp fra terrenglinjen.
    # 110° = 70° til venstre for positiv x-akse (\ retning oppover-venstre).
    _angle = math.radians(110)
    tick_du = _TERRAIN_TICK_LEN * math.cos(_angle)
    tick_dv = _TERRAIN_TICK_LEN * math.sin(_angle)

    n_ticks = max(1, int(total_len / _TERRAIN_TICK_INTERVAL))
    tick_targets = [(k + 0.5) / n_ticks * total_len for k in range(n_ticks)]

    accumulated = 0.0
    tick_idx = 0
    for i, seg_len in enumerate(seg_lengths):
        if seg_len < 1e-9:
            continue
        u1, v1 = chain[i]
        u2, v2 = chain[i + 1]
        while tick_idx < len(tick_targets) and tick_targets[tick_idx] <= accumulated + seg_len + 1e-9:
            t = min(max((tick_targets[tick_idx] - accumulated) / seg_len, 0.0), 1.0)
            uc = u1 + t * (u2 - u1)
            vc = v1 + t * (v2 - v1)
            ax.plot(
                [uc, uc + tick_du],
                [vc, vc + tick_dv],
                color="black", linewidth=0.6, zorder=2,
            )
            tick_idx += 1
        accumulated += seg_len

_TOL = 1e-6  # toleranse for sammenkjeding av endepunkter (meter)

# Classes that represent solid pavement volumes — stacked layers produce multiple TIN edges
# at nearly identical v values. We render only the upper envelope instead of all edges.
_PAVEMENT_CLASSES = frozenset({"planum", "kjørefelt", "skulder", "kantstein", "gang_sykkel"})


def _is_suspect_arm(chain: list[tuple[float, float]]) -> bool:
    """Returner True for nær-vertikale enkelt-segmenter kortere enn 2 m.

    Slike segmenter oppstår typisk fra vegmøblering (rekkverk, stolper, murer)
    som ikke er vegflate-geometri, og som gir visuelt forstyrrende 'armer'
    i tverrprofilet. Lengre eller bredere segmenter beholdes uansett.
    """
    if len(chain) != 2:
        return False
    (u1, v1), (u2, v2) = chain[0], chain[1]
    du = abs(u2 - u1)
    dv = abs(v2 - v1)
    length = math.hypot(du, dv)
    if length > 2.0 or du > 0.5:
        return False
    return du < 1e-6 or dv / max(du, 1e-9) > 2.5


def _snap_ref_elevation(station_z: float, min_v: float) -> int:
    """Returner referanselinjekoteen snappet til heltallsmeter under laveste punkt (R700)."""
    return math.floor(station_z + min_v)


def _chain_segments(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
) -> list[list[tuple[float, float]]]:
    """Kjed isolerte linjestykker fra triangelsnitt til sammenhengende polylinjer."""
    if not segs:
        return []

    def key(p: tuple[float, float]) -> tuple:
        return (round(p[0] / _TOL) * _TOL, round(p[1] / _TOL) * _TOL)

    adj: dict[tuple, list[tuple[tuple, int, tuple]]] = defaultdict(list)
    for i, (p1, p2) in enumerate(segs):
        k1, k2 = key(p1), key(p2)
        adj[k1].append((k2, i, p2))
        adj[k2].append((k1, i, p1))

    used: set[int] = set()
    chains: list[list[tuple[float, float]]] = []

    # Start fra endepunkter (grad 1) for å bygge kjeder fra ytterpunktene innover
    start_candidates = [
        pt for pt, neighbors in adj.items()
        if len(neighbors) == 1 and neighbors[0][1] not in used
    ]
    if not start_candidates:
        start_candidates = list(adj.keys())

    for start in start_candidates:
        available = [(nb, idx, actual) for nb, idx, actual in adj[start] if idx not in used]
        if not available:
            continue

        first_nb, first_idx, _ = available[0]
        first_seg = segs[first_idx]
        chain: list[tuple[float, float]] = (
            [first_seg[0], first_seg[1]] if key(first_seg[0]) == start
            else [first_seg[1], first_seg[0]]
        )
        used.add(first_idx)
        current = first_nb

        while True:
            nxt = [(nb, idx, a) for nb, idx, a in adj[current] if idx not in used]
            if not nxt:
                break
            nb, idx, _ = nxt[0]
            seg = segs[idx]
            chain.append(seg[1] if key(seg[0]) == current else seg[0])
            used.add(idx)
            current = nb

        chains.append(chain)

    for i, (p1, p2) in enumerate(segs):
        if i not in used:
            chains.append([p1, p2])

    return chains

def _upper_envelope_chain(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    u_step: float = 0.1,
) -> list[tuple[float, float]]:
    """Return the highest v at each u across all segments — the visible road surface.

    IFC road models store each pavement layer (slitelag, bærelag, …) as a separate
    solid TIN. Cutting through them produces top + bottom edges for every layer, giving
    a dense bundle of near-identical lines. This function collapses them to a single
    chain tracing only the topmost surface (what R700 wants in a tverrprofil).
    Near-vertical segments (|Δu| < 1 mm) are ignored.
    """
    if not segs:
        return []

    all_u = [u for (u1, _), (u2, _) in segs for u in (u1, u2)]
    u_min, u_max = min(all_u), max(all_u)
    if u_max - u_min < 1e-6:
        return []

    n = max(3, int((u_max - u_min) / u_step) + 2)
    us = np.linspace(u_min, u_max, n)
    max_v = np.full(n, np.nan)

    for (u1, v1), (u2, v2) in segs:
        du = u2 - u1
        if abs(du) < 1e-3:
            continue
        i_lo = int(np.searchsorted(us, min(u1, u2) - 1e-9))
        i_hi = int(np.searchsorted(us, max(u1, u2) + 1e-9, side="right"))
        for i in range(i_lo, i_hi):
            t = float(np.clip((us[i] - u1) / du, 0.0, 1.0))
            v = v1 + t * (v2 - v1)
            if np.isnan(max_v[i]) or v > max_v[i]:
                max_v[i] = v

    return [(float(u), float(v)) for u, v in zip(us, max_v) if not np.isnan(v)]


_SLOPE_CLASSES = frozenset({"skjaering", "fylling"})


def _outer_face_segs(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    tol: float = 1.0,
) -> list[tuple[tuple[float, float], tuple[float, float]]]:
    """Behold bare den ytterste flanken av skjæring/fylling-segmenter.

    IFC modellerer skjæring og fylling som solide TIN-volumer. Et snitt gjennom
    et slikt volum gir BEGGE flatene (indre og ytre) i tillegg til topp/bunn.
    I R700-tverrprofil vises bare den ytterste synlige flaten (bergflaten eller
    fyllingsskråningen). Denne funksjonen beholder bare segmenter der minst ett
    endepunkt er innenfor `tol` meter fra den ytterste u-koordinaten per side.
    """
    if not segs:
        return segs
    all_u = [u for (u1, _), (u2, _) in segs for u in (u1, u2)]
    u_min, u_max = min(all_u), max(all_u)
    u_span = u_max - u_min
    if u_span < tol:
        return segs  # smalt element — behold alt

    result = []
    for (u1, v1), (u2, v2) in segs:
        seg_u_min = min(u1, u2)
        seg_u_max = max(u1, u2)
        at_right = seg_u_max >= u_max - tol
        at_left  = seg_u_min <= u_min + tol
        if at_right or at_left:
            result.append(((u1, v1), (u2, v2)))
    return result


# Farger for navngitte dekkelag — grovere lag lysere (intuitiv dybde)
_NAMED_LAYER_COLORS: list[tuple[str, str]] = [
    ("slitelag",        "#111111"),
    ("bindlag",         "#333333"),
    ("bærelag",         "#555555"),
    ("berelag",         "#555555"),   # uten æ
    ("forsterkningslag","#888888"),
    ("filterlag",       "#aaaaaa"),
]

_OTHER_NAMED_COLOR = "#444444"   # grøft, jordskj., ukjent


def _named_layer_color(label: str) -> str:
    lower = label.lower()
    for keyword, color in _NAMED_LAYER_COLORS:
        if keyword in lower:
            return color
    return _OTHER_NAMED_COLOR


def _lower_envelope_chain(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    u_step: float = 0.1,
) -> list[tuple[float, float]]:
    """Returner laveste v ved hver u — undergrenselinje for et lag."""
    if not segs:
        return []
    all_u = [u for (u1, _), (u2, _) in segs for u in (u1, u2)]
    u_min, u_max = min(all_u), max(all_u)
    if u_max - u_min < 1e-6:
        return []
    n = max(3, int((u_max - u_min) / u_step) + 2)
    us = np.linspace(u_min, u_max, n)
    min_v = np.full(n, np.nan)
    for (u1, v1), (u2, v2) in segs:
        du = u2 - u1
        if abs(du) < 1e-3:
            continue
        i_lo = int(np.searchsorted(us, min(u1, u2) - 1e-9))
        i_hi = int(np.searchsorted(us, max(u1, u2) + 1e-9, side="right"))
        for i in range(i_lo, i_hi):
            t = float(np.clip((us[i] - u1) / du, 0.0, 1.0))
            v = v1 + t * (v2 - v1)
            if np.isnan(min_v[i]) or v < min_v[i]:
                min_v[i] = v
    return [(float(u), float(v)) for u, v in zip(us, min_v) if not np.isnan(v)]


def _is_pavement_label(label: str) -> bool:
    lower = label.lower()
    return any(kw in lower for kw in ("lag", "binder", "slite"))


def _draw_named_layer_chains(
    ax,
    named_segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]],
) -> None:
    """Tegn individuelle IFC-komponentkjeder (ett lag per farge).

    Stablede dekkelag (bindlag, bærelag, filterlag …) tegnes via øvre og nedre
    konvolutt — dette unngår stjernartefakter i hjørner der mange trekanter møtes.
    Andre komponenter (grøft, jordskj.) tegnes med lengde-filtrerte kjeder.
    """
    for label, segs in named_segments.items():
        color = _named_layer_color(label)

        if _is_pavement_label(label):
            # Øvre konvolutt per lag = grensesnitt mot laget over.
            # Nedre konvolutt utelates — den tracer sideflater ned i grøft/skjæring
            # og produserer lange diagonale artefakter i hjørnene.
            upper = _upper_envelope_chain(segs)
            if len(upper) >= 2:
                ax.plot([p[0] for p in upper], [p[1] for p in upper],
                        color=color, linewidth=0.8, linestyle="-", zorder=3)
        else:
            # Side-komponenter: kjedete segmenter med lengde-filter
            clean = [
                (p1, p2) for p1, p2 in segs
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 0.15
            ]
            for chain in _chain_segments(clean):
                if _is_suspect_arm(chain):
                    continue
                ax.plot([p[0] for p in chain], [p[1] for p in chain],
                        color=color, linewidth=0.7, linestyle="-", zorder=3)


def _draw_named_labels(
    ax,
    named_segments: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]],
    v_max_all: float,
) -> None:
    """Tegn IFC-komponentetiketter fra Name-attributt.

    Pil-ankeret settes til geometrisk midtpunkt (v_mid) for hvert lag
    slik at etiketter for stablede dekkelag ikke alle peker til samme v.
    Bruker høyde-stagger for å unngå overlapp mellom etiketter med lik u.
    """
    label_positions: list[tuple[str, float, float, float]] = []  # (label, u_mid, v_ref, color)
    for label, segs in sorted(named_segments.items()):
        pts = [(u, v) for (u1, v1), (u2, v2) in segs for (u, v) in [(u1, v1), (u2, v2)]]
        if not pts:
            continue
        u_mid = sum(p[0] for p in pts) / len(pts)
        v_top = max(p[1] for p in pts)
        v_bot = min(p[1] for p in pts)
        v_ref = (v_top + v_bot) / 2   # midtpunkt i laget, ikke toppen
        color = _named_layer_color(label)
        label_positions.append((label, u_mid, v_ref, color))

    if not label_positions:
        return

    # Sorter etter v_ref (øverst først) slik at stagger-logikken virker naturlig
    label_positions.sort(key=lambda x: -x[2])

    placed: list[tuple[float, float]] = []
    base_gap = 0.5
    stagger  = 0.6

    for label, u_mid, v_ref, color in label_positions:
        vy = v_ref + base_gap
        # Skyv opp til vi ikke lenger kolliderer med allerede plassert etikett
        for _attempt in range(20):
            collision = any(
                abs(u_mid - pu) < 3.0 and abs(vy - pv) < 0.45
                for pu, pv in placed
            )
            if not collision:
                break
            vy += stagger
        placed.append((u_mid, vy))

        ax.annotate(
            label,
            xy=(u_mid, v_ref),
            xytext=(u_mid, vy),
            ha="center", va="bottom",
            fontsize=5.5, color=color,
            arrowprops=dict(arrowstyle="-", color=color, lw=0.5),
            bbox=dict(boxstyle="round,pad=0.15", fc="white", ec=color, alpha=0.90, lw=0.5),
        )


_PAPER_W_MM = 420  # A3 width
_PAPER_H_MM = 297  # A3 height


def render_cross_section_svg(cross_section: CrossSection, output_path: Path) -> Path:
    """Render one cross-section as an R700-compliant SVG.

    R700 requirements:
    - Graph-paper grid background
    - Profile number above plot
    - Horizontal reference line with elevation label
    - Solid lines for road geometry (planum, skjaering, fylling, groft)
    - Dashed lines for unknown/terrain
    - Title block lower-right

    Returns:
        Path to the produced SVG file.
    """
    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    # Collect coordinates in three buckets:
    #   all_u/all_v   — every segment including terrain (fallback)
    #   road_u/road_v — non-terrain segments (y-centering, ref-line snap)
    #   core_u/core_v — pavement + ditch only (x-viewport, keeps range tight)
    # Slopes (skjaering/fylling) extend far from the centreline and are deliberately
    # excluded from core_u so they don't bloat the horizontal range. They are still
    # rendered; matplotlib clips them at the viewport edges.
    all_u: list[float] = []
    all_v: list[float] = []
    road_u: list[float] = []
    road_v: list[float] = []
    core_u: list[float] = []
    core_v: list[float] = []
    for road_class, segs in cross_section.segments.items():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])
            if road_class != "terreng":
                road_u.extend([u1, u2])
                road_v.extend([v1, v2])
            if road_class in _PAVEMENT_CLASSES or road_class == "groft":
                core_u.extend([u1, u2])
                core_v.extend([v1, v2])
    for segs in cross_section.named_segments.values():
        for (u1, v1), (u2, v2) in segs:
            road_u.extend([u1, u2])
            road_v.extend([v1, v2])
            core_u.extend([u1, u2])
            core_v.extend([v1, v2])

    if not all_u:
        logger.warning("Ingen segmenter å rendre for stasjon %.1f", cross_section.station)
        ax.set_title(
            f"Profil {cross_section.station:.2f} (tomt snitt)",
            fontsize=9, fontweight="bold", pad=6, loc="left",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fig.savefig(str(output_path), format="svg")
        finally:
            plt.close(fig)
        return output_path

    # x-viewport: pavement+ditch width + 10 m margin on each side.
    # Slopes and terrain are drawn but clipped at the viewport edges.
    x_base = core_u if core_u else (road_u if road_u else all_u)
    core_span = max(x_base) - min(x_base)
    x_margin = max(10.0, core_span * 0.50)
    x_lo = min(x_base) - x_margin
    x_hi = max(x_base) + x_margin
    x_range = x_hi - x_lo
    view_v = road_v if road_v else all_v

    # y-range from x-range for 1:1 data scale (R700 1:200); centered on pavement geometry.
    fig_ratio = _PAPER_H_MM / _PAPER_W_MM   # ~0.707 for A3
    axes_fraction = 0.78
    y_range = x_range * fig_ratio * axes_fraction
    v_base = core_v if core_v else view_v
    v_mid = (min(v_base) + max(v_base)) / 2.0
    y_lo = v_mid - y_range / 2.0
    y_hi = v_mid + y_range / 2.0

    ax.set_xlim(x_lo, x_hi)
    ax.set_ylim(y_lo, y_hi)

    # R700: ruteark 1m × 1m — etiketter hvert 5m horisontalt, gridlinjer hvert 1m
    ax.xaxis.set_major_locator(MultipleLocator(5.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#aaaaaa", linewidth=0.5, linestyle="-")
    ax.grid(which="minor", color="#dddddd", linewidth=0.25, linestyle="-")

    # R700: horisontal referanselinje snappet til heltallsmeter under laveste punkt
    ref_elev_abs = _snap_ref_elevation(cross_section.elevation, min(view_v))
    ref_line_v = ref_elev_abs - cross_section.elevation
    ax.axhline(y=ref_line_v, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        x_lo + (x_hi - x_lo) * 0.02, ref_line_v,
        f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    # R700: vertikalt senterlinjemerke ved u=0
    ax.axvline(x=0.0, color="black", linewidth=0.5, linestyle=":", zorder=1)
    ax.text(
        0.0, y_hi - (y_hi - y_lo) * 0.05,
        "SL",
        ha="center", va="bottom", fontsize=6, color="#333333",
    )

    # --- Pavement classes: draw upper envelope only (R700 road surface) ---
    # Multiple solid IFC layers (slitelag, bærelag …) each produce top+bottom edges.
    # Collapsing to the upper envelope gives the clean road-surface profile R700 requires.
    pavement_segs: list[tuple[tuple[float, float], tuple[float, float]]] = []
    for cls in _PAVEMENT_CLASSES:
        pavement_segs.extend(cross_section.segments.get(cls, []))

    if pavement_segs:
        envelope = _upper_envelope_chain(pavement_segs)
        if len(envelope) >= 2:
            ax.plot(
                [p[0] for p in envelope],
                [p[1] for p in envelope],
                color="black", linewidth=2.0, linestyle="-", zorder=5,
            )

    # --- Named layer chains (individuelle dekkelagsgrenser) ---
    if cross_section.named_segments:
        _draw_named_layer_chains(ax, cross_section.named_segments)

    # --- Other road geometry: draw individual chains ---
    for road_class, segs in cross_section.segments.items():
        if road_class in _PAVEMENT_CLASSES:
            continue  # already drawn as upper envelope above
        draw_segs = _outer_face_segs(segs) if road_class in _SLOPE_CLASSES else segs
        for chain in _chain_segments(draw_segs):
            if _is_suspect_arm(chain):
                logger.debug("Filtrerer nær-vertikal arm for klasse '%s'", road_class)
                continue
            if road_class == "terreng":
                _draw_terrain_chain(ax, chain)
            else:
                style = _STYLE.get(road_class, _STYLE["unknown"])
                us = [p[0] for p in chain]
                vs = [p[1] for p in chain]
                ax.plot(us, vs, **style)

    # IFC-komponentetiketter fra Name-attributt
    if cross_section.named_segments:
        _draw_named_labels(ax, cross_section.named_segments, max(view_v))

    # Varseltekst dersom terrengdata mangler (R700 krever eksisterende terreng)
    if "terreng" not in cross_section.segments:
        ax.text(
            ax.get_xlim()[0] + 0.3,
            ref_line_v + 0.25,
            "Eksisterende terreng ikke tilgjengelig",
            fontsize=5.5, color="#888888", style="italic", va="bottom",
        )

    # Profile number above plot (R700)
    ax.set_title(
        f"Profil {cross_section.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )

    # Axis labels
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel(f"Høyde (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    # Title block lower-right (R700 U-drawing)
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:200 · Stasjon {cross_section.station:.2f} m · xlim=[{ax.get_xlim()[0]:.0f},{ax.get_xlim()[1]:.0f}]",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output_path


def render_cross_section_png(cross_section: CrossSection, output_path: Path) -> Path:
    """PNG export is outside MVP scope."""
    raise NotImplementedError("PNG-eksport er utenfor MVP-scope. Bruk render_cross_section_svg.")


# ---------------------------------------------------------------------------
# Lengdeprofil (R700 C-tegning)
# ---------------------------------------------------------------------------

_LABEL_INTERVAL_M = 100.0   # Profilnummer + terrenghøyde-verdier hvert 100 m (R700)
_N_RUBRIC_ROWS = 6

# Rad 0 nederst (fjernest fra profilen), rad 5 øverst (nærmest profilen) — R700-rekkefølge
_ROW_LABELS = [
    "Terrenghøyde",
    "Profilhøyde",
    "Tverrfall",
    "Breddeutvidelse",
    "Horisontalkurv.",
    "Profilnummer",
]


def _interp_elevation(
    stations: list[float],
    elevations: list[float],
    target: float,
) -> float:
    """Lineær interpolasjon av høyde ved gitt stasjon."""
    if not stations:
        return float("nan")
    for i in range(len(stations) - 1):
        if stations[i] <= target <= stations[i + 1]:
            ds = stations[i + 1] - stations[i]
            if ds < 1e-9:
                return elevations[i]
            t = (target - stations[i]) / ds
            return elevations[i] + t * (elevations[i + 1] - elevations[i])
    return elevations[0] if target <= stations[0] else elevations[-1]


def _label_positions(s_min: float, s_max: float, interval: float) -> list[float]:
    """Returnerer stasjonsverdier ved hvert intervall innenfor [s_min, s_max]."""
    first = math.ceil(s_min / interval) * interval
    pos: list[float] = []
    s = first
    while s <= s_max + 0.5:
        pos.append(s)
        s += interval
    return pos


def _draw_gradient_labels(
    ax,
    stations: list[float],
    design_z: list[float],
    label_pos: list[float],
) -> None:
    """Tegn stigningsetiketter mellom profilnummer-posisjonene (R700: % med fortegn)."""
    for i in range(len(label_pos) - 1):
        s0, s1 = label_pos[i], label_pos[i + 1]
        z0 = _interp_elevation(stations, design_z, s0)
        z1 = _interp_elevation(stations, design_z, s1)
        if math.isnan(z0) or math.isnan(z1):
            continue
        ds = s1 - s0
        if ds < 1e-6:
            continue
        grad_pct = (z1 - z0) / ds * 100
        label = f"+{grad_pct:.1f} %" if grad_pct >= 0 else f"{grad_pct:.1f} %"
        mid_s = (s0 + s1) / 2
        mid_z = _interp_elevation(stations, design_z, mid_s)
        ax.text(
            mid_s, mid_z,
            label,
            ha="center", va="bottom", fontsize=6, color="#222222",
            bbox=dict(boxstyle="round,pad=0.1", fc="white", ec="none", alpha=0.7),
        )


def _draw_tverrfall_row(
    ax,
    stations: list[float],
    cross_falls: list[tuple[float, float]],
    row_idx: int,
) -> None:
    """Tegn tverrfall-stepped diagram i rubrikk-rad row_idx.

    Viser gjennomsnitt av venstre/høyre tverrfall som step-kurve.
    1 % tverrfall ≈ 0.04 rad-enheter i rubrikken.
    """
    y_center = row_idx + 0.5
    row_half = 0.38

    valid = [
        (s, (lp + rp) / 2)
        for s, (lp, rp) in zip(stations, cross_falls)
        if not (math.isnan(lp) and math.isnan(rp))
        for lp, rp in [(
            lp if not math.isnan(lp) else rp,
            rp if not math.isnan(rp) else lp,
        )]
    ]

    if not valid:
        ax.text(
            (stations[0] + stations[-1]) / 2, y_center,
            "(ingen tverrfalldata)",
            ha="center", va="center", fontsize=5, color="#888888",
        )
        return

    # Horisontal referanselinje
    ax.axhline(y=y_center, color="#cccccc", linewidth=0.3, zorder=1)

    all_vals = [v for _, v in valid]
    max_val = max(all_vals) if all_vals else 8.0
    scale = row_half / max(max_val, 2.0)

    # Desimer til maks 1 punkt per 20 m for lesbarhet
    decimated: list[tuple[float, float]] = []
    last_s: float | None = None
    for s, avg in valid:
        if last_s is None or s - last_s >= 20.0:
            decimated.append((s, avg))
            last_s = s

    if decimated:
        xs = [p[0] for p in decimated]
        ys = [y_center + p[1] * scale for p in decimated]
        ax.step(xs, ys, where="mid", color="#555555", linewidth=0.8, zorder=3)


def _draw_rubric(
    ax,
    stations: list[float],
    design_z: list[float],
    terrain_z: list[float] | None,
    cross_falls: list[tuple[float, float]],
    curve_points: list[tuple[float, float]],
    label_pos: list[float],
    s_min: float,
    s_max: float,
) -> None:
    """Tegn rubrikk-blokk under profilgrafen iht. R700."""
    n_rows = _N_RUBRIC_ROWS
    s_range = s_max - s_min

    ax.set_ylim(0, n_rows)
    ax.set_yticks([])
    ax.tick_params(axis="x", labelsize=6)
    ax.set_xlabel("Stasjon (m)", fontsize=7)
    ax.spines["left"].set_visible(False)
    ax.spines["right"].set_visible(False)

    # Rad-separatorer
    for i in range(n_rows + 1):
        ax.axhline(y=i, color="black", linewidth=0.5, zorder=4)

    # Vertikale skillelinjer ved hvert 100 m
    for s in label_pos:
        ax.axvline(x=s, color="#cccccc", linewidth=0.3, zorder=1)

    # Rad-etiketter (utenfor aksene, via transAxes)
    for i, label in enumerate(_ROW_LABELS):
        ax.text(
            -0.005, (i + 0.5) / n_rows,
            label,
            transform=ax.transAxes,
            ha="right", va="center",
            fontsize=5.5, color="black",
        )

    # Rad 5 — Profilnummer
    for s in label_pos:
        ax.text(s, 5.5, f"{s:.0f}", ha="center", va="center",
                fontsize=5.5, color="black", fontweight="bold")

    # Rad 4 — Horisontalkurvatur
    for s_cp, delta in curve_points:
        if s_min <= s_cp <= s_max:
            ax.plot([s_cp, s_cp], [4.05, 4.95],
                    color="#444444", linewidth=0.5, linestyle=":", zorder=2)
            sign = "H" if delta > 0 else "V"
            ax.text(s_cp + s_range * 0.004, 4.75, sign,
                    ha="left", va="center", fontsize=4.5, color="#444444")

    # Rad 3 — Breddeutvidelse (placeholder)
    ax.text(
        (s_min + s_max) / 2, 3.5,
        "(breddeutvidelse ikke beregnet)",
        ha="center", va="center", fontsize=4.5, color="#aaaaaa",
    )

    # Rad 2 — Tverrfall
    _draw_tverrfall_row(ax, stations, cross_falls, row_idx=2)

    # Rad 1 — Profilhøyde
    for s in label_pos:
        z = _interp_elevation(stations, design_z, s)
        if not math.isnan(z):
            ax.text(s, 1.5, f"{z:.1f}", ha="center", va="center",
                    fontsize=5.0, color="black")

    # Rad 0 — Terrenghøyde
    if terrain_z is not None:
        for s in label_pos:
            z = _interp_elevation(stations, terrain_z, s)
            if not math.isnan(z):
                ax.text(s, 0.5, f"{z:.1f}", ha="center", va="center",
                        fontsize=5.0, color="black")
    else:
        ax.text(
            (s_min + s_max) / 2, 0.5,
            "(terrengdata ikke tilgjengelig)",
            ha="center", va="center", fontsize=4.5, color="#888888",
        )


def render_longitudinal_profile_svg(
    profile: LongitudinalProfile,
    output_path: Path,
) -> Path:
    """Render et R700-lengdeprofil (C-tegning øverste halvdel) som SVG.

    Produserer:
    - Profilgraf med 10× vertikal eksaggerasjon (Hor 1:1000, Vert 1:100)
    - Stigningsetiketter mellom profilpunkter
    - Vertikale stiplede linjer ved horisontale kurvepunkter
    - Rubrikk-blokk med 6 rader: Profilnummer, Horisontalkurvatur,
      Breddeutvidelse, Tverrfall, Profilhøyde, Terrenghøyde

    Args:
        profile:     LongitudinalProfile fra generate_longitudinal_profile().
        output_path: Ønsket filsti for SVG.

    Returns:
        Path til den produserte SVG-filen.
    """
    stations = profile.stations
    if not stations:
        raise ValueError("Tomt lengdeprofil — ingen stasjoner")

    s_min = stations[0]
    s_max = stations[-1]
    route_length = max(s_max - s_min, 1.0)

    design_z = profile.surfaces["vegoverflate"]
    terrain_z = profile.surfaces.get("terreng")

    # Figurdimensjoner: bredde skalerer med strekningslengde
    fig_w = max(16.0, route_length * 0.022 + 4.0)
    fig_h = 10.0

    fig = plt.figure(figsize=(fig_w, fig_h), dpi=96)
    gs = fig.add_gridspec(2, 1, height_ratios=[3, 2], hspace=0.02)
    ax_prof = fig.add_subplot(gs[0])
    ax_rub = fig.add_subplot(gs[1], sharex=ax_prof)

    # ------------------------------------------------------------------ #
    #  Profilgraf                                                          #
    # ------------------------------------------------------------------ #

    # Designert profil (solid, tung)
    ax_prof.plot(
        stations, design_z,
        color="black", linewidth=2.0, linestyle="-",
        label="Prosjektert profil", zorder=5,
    )

    # Eksisterende terreng (stiplet)
    if terrain_z is not None:
        valid_t = [(s, z) for s, z in zip(stations, terrain_z) if not math.isnan(z)]
        if valid_t:
            ts, tz = zip(*valid_t)
            ax_prof.plot(
                ts, tz,
                color="black", linewidth=0.8, linestyle="--",
                label="Eksisterende terreng", zorder=4,
            )

    # Y-akse: helautomatisk skalering med 15 % margin + plass til stigningsetiketter
    all_z = [z for z in design_z if not math.isnan(z)]
    if terrain_z:
        all_z += [z for z in terrain_z if not math.isnan(z)]
    z_min = min(all_z)
    z_max = max(all_z)
    z_range = max(z_max - z_min, 1.0)
    z_margin = z_range * 0.15 + 1.0
    ax_prof.set_ylim(z_min - z_margin * 0.5, z_max + z_margin * 1.8)
    ax_prof.set_xlim(s_min - route_length * 0.01, s_max + route_length * 0.01)

    # Rutenett: 1 m vertikalt, 100 m / 10 m horisontalt
    ax_prof.yaxis.set_major_locator(MultipleLocator(1.0))
    ax_prof.xaxis.set_major_locator(MultipleLocator(100.0))
    ax_prof.xaxis.set_minor_locator(MultipleLocator(10.0))
    ax_prof.set_axisbelow(True)
    ax_prof.grid(which="major", color="#cccccc", linewidth=0.4)
    ax_prof.grid(which="minor", color="#eeeeee", linewidth=0.2)

    # Stigningsetiketter og kurvepunkter
    label_pos = _label_positions(s_min, s_max, _LABEL_INTERVAL_M)
    _draw_gradient_labels(ax_prof, stations, design_z, label_pos)

    for s_cp, _ in profile.curve_points:
        ax_prof.axvline(x=s_cp, color="#666666", linewidth=0.5, linestyle=":", zorder=2)

    # Forklaring
    legend_handles = [
        plt.Line2D([0], [0], color="black", linewidth=2.0, linestyle="-",
                   label="Prosjektert profil"),
        plt.Line2D([0], [0], color="black", linewidth=0.8, linestyle="--",
                   label="Eksisterende terreng"),
    ]
    ax_prof.legend(handles=legend_handles, loc="upper left", fontsize=6, framealpha=0.8)

    ax_prof.set_ylabel("Høyde (m)", fontsize=7)
    ax_prof.tick_params(axis="both", labelsize=6)
    ax_prof.tick_params(axis="x", labelbottom=False)
    ax_prof.spines["bottom"].set_visible(False)

    ax_prof.set_title(
        f"Lengdeprofil  profil {s_min:.0f} – {s_max:.0f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )

    # ------------------------------------------------------------------ #
    #  Rubrikk                                                             #
    # ------------------------------------------------------------------ #
    ax_rub.spines["top"].set_visible(False)
    _draw_rubric(
        ax_rub,
        stations=stations,
        design_z=design_z,
        terrain_z=terrain_z,
        cross_falls=profile.cross_falls,
        curve_points=profile.curve_points,
        label_pos=label_pos,
        s_min=s_min,
        s_max=s_max,
    )

    # Tittelfelt (nedre høyre)
    fig.text(
        0.98, 0.01,
        "SVV · R700 · Hor: 1:1000  Vert: 1:100",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)

    return output_path


def _draw_dim_line(
    ax,
    u_start: float,
    u_end: float,
    v: float,
    label: str,
    color: str = "#cc0000",
) -> None:
    """Tegn en horisontal dimensjonslinje med vertikale tikk-merker og sentrert etikett.

    Args:
        ax: Matplotlib Axes.
        u_start: Startposisjon horisontalt (m).
        u_end: Sluttposisjon horisontalt (m).
        v: Høyde dimensjonslinjen tegnes ved (m).
        label: Tekstetikett (f.eks. "3.50 m").
        color: Farge (standard rød R700-dimensjonslinjer).
    """
    ax.plot([u_start, u_end], [v, v], color=color, linewidth=0.8)
    for u in (u_start, u_end):
        ax.plot([u, u], [v - 0.15, v + 0.15], color=color, linewidth=0.8)
    ax.text(
        (u_start + u_end) / 2,
        v + 0.2,
        label,
        ha="center", va="bottom", fontsize=6, color=color,
    )


def render_normal_section_svg(cs: CrossSection, output_path: Path) -> Path:
    """Render et R700-normalprofil (dimensjonert tverrsnitt) som SVG.

    Kaller compute_normal_section() internt for å beregne dimensjoner,
    og tegner deretter geometri + annotasjonslag (breddemål, tverrfall,
    skråningsforhold, komponentetiketter) iht. R700.

    Args:
        cs: CrossSection-objekt med snittgeometri.
        output_path: Ønsket filsti for SVG-filen.

    Returns:
        Path til den produserte SVG-filen.
    """
    ns = compute_normal_section(cs)

    fig, ax = plt.subplots(figsize=(_PAPER_W_MM / 25.4, _PAPER_H_MM / 25.4), dpi=96)

    # --- Samle alle koordinater for auto-skalering ---
    all_u: list[float] = []
    all_v: list[float] = []
    for segs in cs.segments.values():
        for (u1, v1), (u2, v2) in segs:
            all_u.extend([u1, u2])
            all_v.extend([v1, v2])

    if not all_u:
        logger.warning("Ingen segmenter å rendre for normalprofil stasjon %.1f", cs.station)
        ax.set_title(
            f"Normalprofil {cs.station:.2f} (tomt snitt)",
            fontsize=9, fontweight="bold", pad=6, loc="left",
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fig.savefig(str(output_path), format="svg")
        finally:
            plt.close(fig)
        return output_path

    u_margin = max(3.0, (max(all_u) - min(all_u)) * 0.15)
    v_margin = max(2.0, (max(all_v) - min(all_v)) * 0.20)

    # Ekstra plass over geometrien til dimensjonslinjer (minst 3 m)
    dim_overhead = 3.5
    ax.set_xlim(min(all_u) - u_margin, max(all_u) + u_margin)
    ax.set_ylim(min(all_v) - v_margin, max(all_v) + v_margin + dim_overhead)

    # --- R700: ruteark 1 m × 1 m ---
    ax.xaxis.set_major_locator(MultipleLocator(5.0))
    ax.xaxis.set_minor_locator(MultipleLocator(1.0))
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
    ax.set_axisbelow(True)
    ax.grid(which="major", color="#aaaaaa", linewidth=0.5, linestyle="-")
    ax.grid(which="minor", color="#dddddd", linewidth=0.25, linestyle="-")

    # --- R700: horisontal referanselinje ---
    ref_elev_abs = _snap_ref_elevation(cs.elevation, min(all_v))
    ref_line_v = ref_elev_abs - cs.elevation
    ax.axhline(y=ref_line_v, color="black", linewidth=0.8, linestyle="-")
    ax.text(
        min(all_u) - u_margin * 0.8,
        ref_line_v,
        f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )

    # --- R700: vertikalt senterlinjemerke ved u=0 ---
    ax.axvline(x=0.0, color="black", linewidth=0.5, linestyle=":", zorder=1)
    ax.text(
        0.0, max(all_v) + v_margin * 0.3,
        "SL",
        ha="center", va="bottom", fontsize=6, color="#333333",
    )

    # --- Geometrilag (samme stil som tverrprofil) ---
    for road_class, segs in cs.segments.items():
        style = _STYLE.get(road_class, _STYLE["unknown"])
        for chain in _chain_segments(segs):
            if _is_suspect_arm(chain):
                logger.debug("Filtrerer nær-vertikal arm for klasse '%s' (normalprofil)", road_class)
                continue
            us = [p[0] for p in chain]
            vs = [p[1] for p in chain]
            ax.plot(us, vs, **style)

    # --- Annotasjonslag ---
    # Høyde for dimensjonslinjer: litt over høyeste geometripunkt
    dim_v = max(all_v) + 1.5

    # 1. Breddemål (røde dimensjonslinjer) — kun hvis ikke NaN
    if not math.isnan(ns.left_carriageway_width):
        _draw_dim_line(
            ax,
            u_start=-ns.left_carriageway_width,
            u_end=0.0,
            v=dim_v,
            label=f"{ns.left_carriageway_width:.2f} m",
        )
    if not math.isnan(ns.right_carriageway_width):
        _draw_dim_line(
            ax,
            u_start=0.0,
            u_end=ns.right_carriageway_width,
            v=dim_v,
            label=f"{ns.right_carriageway_width:.2f} m",
        )
    if not math.isnan(ns.left_carriageway_width) and not math.isnan(ns.left_shoulder_width):
        _draw_dim_line(
            ax,
            u_start=-(ns.left_carriageway_width + ns.left_shoulder_width),
            u_end=-ns.left_carriageway_width,
            v=dim_v + 1.0,
            label=f"{ns.left_shoulder_width:.2f} m",
        )
    if not math.isnan(ns.right_carriageway_width) and not math.isnan(ns.right_shoulder_width):
        _draw_dim_line(
            ax,
            u_start=ns.right_carriageway_width,
            u_end=ns.right_carriageway_width + ns.right_shoulder_width,
            v=dim_v + 1.0,
            label=f"{ns.right_shoulder_width:.2f} m",
        )

    # 2. Tverrfall (%) — mørk grå tekst midt på kjørefeltflaten + skråpil
    cf_color = "#555555"
    if not math.isnan(ns.left_cross_fall_pct) and not math.isnan(ns.left_carriageway_width):
        u_mid = -ns.left_carriageway_width / 2
        ax.text(
            u_mid, -0.3,
            f"{ns.left_cross_fall_pct:.1f}%",
            ha="center", va="top", fontsize=6, color=cf_color,
        )
        # Skråpil: fallet går fra u=0 (kronepunkt) mot venstre kant
        arrow_u_from = u_mid + 0.4   # closer to crown
        arrow_u_to   = u_mid - 0.4   # toward edge
        arrow_v      = -0.15          # on the road surface
        ax.annotate(
            "",
            xy=(arrow_u_to, arrow_v),
            xytext=(arrow_u_from, arrow_v - 0.05),
            arrowprops=dict(arrowstyle="-|>", color=cf_color, lw=0.6),
        )
    if not math.isnan(ns.right_cross_fall_pct) and not math.isnan(ns.right_carriageway_width):
        u_mid = ns.right_carriageway_width / 2
        ax.text(
            u_mid, -0.3,
            f"{ns.right_cross_fall_pct:.1f}%",
            ha="center", va="top", fontsize=6, color=cf_color,
        )
        # Skråpil: fallet går fra u=0 (kronepunkt) mot høyre kant
        arrow_u_from = u_mid - 0.4
        arrow_u_to   = u_mid + 0.4
        arrow_v      = -0.15
        ax.annotate(
            "",
            xy=(arrow_u_to, arrow_v),
            xytext=(arrow_u_from, arrow_v - 0.05),
            arrowprops=dict(arrowstyle="-|>", color=cf_color, lw=0.6),
        )

    # 3. Skråningsforhold (1:x) — grønn tekst langs skjæring/fylling
    slope_color = "#228B22"
    cut_segs = cs.segments.get("skjaering", []) or cs.segments.get("fylling", [])
    if not math.isnan(ns.left_slope_ratio):
        # Finn omtrentlig midtpunkt på venstre skjæring/fylling
        left_pts = [
            p
            for (u1, v1), (u2, v2) in cut_segs
            for p in [(u1, v1), (u2, v2)]
            if p[0] < 0
        ]
        if left_pts:
            u_sl = sum(p[0] for p in left_pts) / len(left_pts)
            v_sl = sum(p[1] for p in left_pts) / len(left_pts)
            # Vinkel fra innerste til ytterste punkt (sortert på u, stabilt uavhengig av segmentrekkefølge)
            if len(left_pts) >= 2:
                p_inner = max(left_pts, key=lambda p: p[0])
                p_outer = min(left_pts, key=lambda p: p[0])
                angle_deg = math.degrees(math.atan2(p_outer[1] - p_inner[1], p_outer[0] - p_inner[0]))
            else:
                angle_deg = 0
            ax.text(
                u_sl, v_sl,
                f"1:{ns.left_slope_ratio:.1f}",
                ha="center", va="center", fontsize=6, color=slope_color,
                rotation=angle_deg,
            )
    if not math.isnan(ns.right_slope_ratio):
        right_pts = [
            p
            for (u1, v1), (u2, v2) in cut_segs
            for p in [(u1, v1), (u2, v2)]
            if p[0] > 0
        ]
        if right_pts:
            u_sr = sum(p[0] for p in right_pts) / len(right_pts)
            v_sr = sum(p[1] for p in right_pts) / len(right_pts)
            # Vinkel fra innerste til ytterste punkt (sortert på u, stabilt uavhengig av segmentrekkefølge)
            if len(right_pts) >= 2:
                p_inner = min(right_pts, key=lambda p: p[0])
                p_outer = max(right_pts, key=lambda p: p[0])
                angle_deg = math.degrees(math.atan2(p_outer[1] - p_inner[1], p_outer[0] - p_inner[0]))
            else:
                angle_deg = 0
            ax.text(
                u_sr, v_sr,
                f"1:{ns.right_slope_ratio:.1f}",
                ha="center", va="center", fontsize=6, color=slope_color,
                rotation=angle_deg,
            )

    # 4. Komponentetiketter (svart, 6pt) — én etikett per side per veiklasse
    # "planum" er IFC-overflategeometri-klassen som tilsvarer kjørefelt i R700
    # Rank styrer etikett-høyde: kjørefelt lavest (nærmest geometrien), skjæring/fylling høyest
    _LABEL_RANK = {"kjørefelt": 0, "planum": 0, "skulder": 1, "groft": 2, "skjaering": 3, "fylling": 3}
    component_label = {
        "kjørefelt": "kjørefelt",
        "planum": "kjørefelt",
        "skulder": "skulder",
        "groft": "grøft",
        "skjaering": ns.section_type if ns.section_type in ("skjæring", "kombinasjon") else "skjæring",
        "fylling": ns.section_type if ns.section_type in ("fylling", "kombinasjon") else "fylling",
    }
    labeled: set[str] = set()
    for road_class, segs in cs.segments.items():
        if road_class not in component_label or road_class in labeled:
            continue
        label_text = component_label[road_class]
        rank = _LABEL_RANK.get(road_class, 0)
        v_offset = 0.4 + rank * 0.65
        pts = [p for (u1, v1), (u2, v2) in segs for p in [(u1, v1), (u2, v2)]]
        if not pts:
            continue
        # Plasser én etikett per side med rank-basert høyde-stagger
        for side_pts in (
            [p for p in pts if p[0] < -0.1],   # venstre
            [p for p in pts if p[0] > 0.1],    # høyre
        ):
            if not side_pts:
                continue
            u_rep = sum(p[0] for p in side_pts) / len(side_pts)
            max_v = max(p[1] for p in side_pts)
            ax.annotate(
                label_text,
                xy=(u_rep, max_v),
                xytext=(u_rep, max_v + v_offset),
                ha="center", va="bottom", fontsize=6, color="black",
                arrowprops=dict(arrowstyle="-", color="black", lw=0.4),
            )
        labeled.add(road_class)

    # --- Titler og akseetiketter ---
    ax.set_title(
        f"Normalprofil {cs.station:.2f}",
        fontsize=9, fontweight="bold", pad=6, loc="left",
    )
    ax.set_xlabel("Avstand fra senterlinje (m)", fontsize=7)
    ax.set_ylabel("Høyde relativt til senterlinje (m)", fontsize=7)
    ax.tick_params(labelsize=6)

    # Tittelfelt nedre høyre (R700)
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:50 · Stasjon {cs.station:.2f} m",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )

    # --- Forklaring nedre venstre ---
    legend_handles = [
        plt.Line2D([0], [0], color="black", linewidth=1.5, linestyle="-",
                   label="Prosjektert geometri"),
        plt.Line2D([0], [0], color="black", linewidth=0.8, linestyle="--",
                   label="Eksisterende terreng"),
    ]
    ax.legend(handles=legend_handles, loc="lower left", fontsize=6, framealpha=0.8)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fig.savefig(str(output_path), format="svg", bbox_inches="tight")
    finally:
        plt.close(fig)
    return output_path
