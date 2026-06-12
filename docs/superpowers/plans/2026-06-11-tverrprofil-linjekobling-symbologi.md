# Tverrprofil: linjekobling + R700-symbologi (hybrid) — Implementeringsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tverrprofil-SVG-ene skal ha sammenhengende linjer (toleransebasert kjeding + robust gap-stitching) og R700-korrekt symbologi i hybrid-stil (kote-akse, tegnforklaring, tittelfelt, ryddet etikett-støy).

**Architecture:** `_chain_segments` flyttes til `cross_section.py` og får euklidsk toleranse (romlig hash) i stedet for eksakt 1 mm-nøkkel. `stitch_cross_section_gaps` skrives om til kjede-endepunkt + gjensidig-nærmeste-bro (maks én bro per endepunkt) som strukturelt hindrer stjerne-artefakter. Renderer går fra entalls-envelope til hull-splittende `_upper_envelope_chains`, fra segment-nivå til kjede-nivå ytterflate-filter, og får hybrid R700-presentasjon (kote-y-akse via FixedLocator, tegnforklaring via Line2D-proxyer, ekte tittelfelt).

**Tech Stack:** Python 3, matplotlib (Agg, SVG/PNG via suffix), numpy, pytest. Norsk i docstrings/kommentarer/commit-meldinger (som resten av repoet).

---

## Designbeslutninger og bevisste avvik

1. **Stitch-toleranse 0,40 m (avvik fra opprinnelig punktliste som sa 0,5 → 0,05).** Målte gap mellom IFC-elementer i samme klasse er 9–340 mm (st. 120 skulder: 25/36/198 mm; st. 800 grøft: 9/47/235/337 mm). 0,05 m ville ikke tettet dem. Den dokumenterte grunnen til lav toleranse (stjerne-artefakter) elimineres i stedet strukturelt: broer legges kun mellom *kjede*-endepunkter (ikke alle rå segment-endepunkter), kun mellom gjensidig nærmeste par, og hvert endepunkt brukes maks én gang.
2. **Terreng tegnes som tynn heltrukken linje med tverrstrek-grupper, ikke stiplet.** R700-teksten sier «eksisterende terreng stiplet», men ground-truth-eksempelet U201 (`C:\Users\jornk\.claude\skills\r700-tverrprofil\assets\examples\U201-tverrprofil.png`) viser nettopp heltrukken tynn linje med tick-grupper — dagens `_draw_terrain_chain` matcher U201 og beholdes uendret. Avviket er bevisst og notert her.
3. **Hybrid ark-stil (brukerens valg):** behold matplotlib-akser/tall (nyttig i web-utforskeren), men y-aksen viser **kote** (absolutt høyde) i stedet for relativ høyde, tegnforklaring legges på arket, og debug-tittelfeltet erstattes av et rent tittelfelt.
4. **`max_slope`-mismatch (kommentar sa 3.0, koden sa 2.0) løses i favør av 3.0** for navngitte sidekomponenter — beholder grøfteskråninger opp til ~72°.
5. **Full pytest-suite skal ALDRI kjøres** — `tests/test_pipeline.py` henger. Kun målrettede testkommandoer som angitt per task.

## Filstruktur

| Fil | Ansvar i denne planen |
|---|---|
| `src/ifc_processor/cross_section.py` | Får `_chain_segments` (toleransebasert) + omskrevet `stitch_cross_section_gaps` + modul-nivå `_PRIO` |
| `src/ifc_processor/renderer.py` | Mister `_TOL`/`_chain_segments`/`_outer_face_segs`/`_lower_envelope_chain`; får `_upper_envelope_chains`, `_outer_face_chains`, `_is_generic_label`, kote-akse, tegnforklaring, tittelfelt |
| `src/ifc_processor/pipeline.py` | Linje 353: bruk ny stitch-default |
| `tests/test_cross_section.py` | Nye tester for kjeding og stitching |
| `tests/test_renderer.py` | Oppdaterte envelope-tester (flertall), nye tester for ytterflate, kote, tegnforklaring, tittelfelt, etikett-støy |
| `scratch_diag_tverrprofil.py` + `scratch_diag_out/` | Visuell verifisering (Task 9), slettes etterpå |

Merk: `render_normal_section_svg` (renderer.py ~1102–1110) bruker `_chain_segments` og `_is_suspect_arm` direkte og skal fortsette å virke — re-eksport i Task 1 sørger for det. `tests/test_normal_section.py` kjøres som regresjonsvakt i hver task som rører renderer.py.

---

### Task 1: Toleransebasert `_chain_segments` i cross_section.py

Dagens kjeding (renderer.py:138–195) matcher endepunkter via eksakt avrundingsnøkkel med `_TOL = 1e-3` (1 mm). Reelle gap mellom IFC-elementer er 9–340 mm → fragmenterte kjeder. Ny implementasjon: romlig hash med euklidsk node-snapping innenfor `tol=0.02` (2 cm håndterer modelleringsslark uten å koble fysisk adskilte elementer; større gap håndteres av stitcheren i Task 2). Funksjonen flyttes til `cross_section.py` (stitcheren trenger den; renderer re-eksporterer for testene og normalprofilen).

**Files:**
- Modify: `src/ifc_processor/cross_section.py` (ny funksjon etter `_project_to_2d`)
- Modify: `src/ifc_processor/renderer.py` (slett linje 108 `_TOL` og linje 138–195 `_chain_segments`; oppdater import linje 6 og 15)
- Test: `tests/test_cross_section.py`

- [ ] **Step 1: Skriv feilende tester**

Legg til nederst i `tests/test_cross_section.py`:

```python
# ---------------------------------------------------------------------------
# _chain_segments — toleransebasert kjeding
# ---------------------------------------------------------------------------

from src.ifc_processor.cross_section import _chain_segments


def test_chain_segments_joins_within_tolerance():
    """15 mm gap mellom segmenter skal kjedes (reelle IFC-gap er 9–340 mm)."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.015, 0.0), (2.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 1
    assert len(chains[0]) >= 3


def test_chain_segments_keeps_large_gap_separate():
    """100 mm gap er over default-toleransen (20 mm) — to kjeder."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.1, 0.0), (2.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 2


def test_chain_segments_exact_touch_still_works():
    """Eksakt like endepunkter (gammel oppførsel) skal fortsatt kjedes."""
    segs = [
        ((0.0, 0.0), (1.0, 0.0)),
        ((1.0, 0.0), (2.0, 0.5)),
        ((2.0, 0.5), (3.0, 0.5)),
    ]
    chains = _chain_segments(segs)
    assert len(chains) == 1
    assert len(chains[0]) == 4
```

- [ ] **Step 2: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_cross_section.py -v -k chain_segments`
Forventet: ImportError / FAIL — `_chain_segments` finnes ikke i cross_section.

- [ ] **Step 3: Implementer i cross_section.py**

I `src/ifc_processor/cross_section.py`: legg til `from collections import defaultdict` i importene (etter `from dataclasses import ...`), og legg til denne funksjonen rett etter `_project_to_2d`:

```python
def _chain_segments(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    tol: float = 0.02,
) -> list[list[tuple[float, float]]]:
    """Kjed sammen segmenter hvis endepunkter ligger innenfor `tol` meter.

    Bruker romlig hash (cellestørrelse = tol) slik at endepunkter som ikke er
    eksakt like likevel matches: målte gap mellom IFC-elementer er typisk
    9–340 mm, langt over den gamle 1 mm-avrundingsnøkkelen. Kjedene beholder
    de faktiske segment-endepunktene — hopp <= tol er usynlige i 1:200.
    """
    if not segs:
        return []

    inv = 1.0 / tol
    cell_nodes: dict[tuple[int, int], list[int]] = defaultdict(list)
    node_pts: list[tuple[float, float]] = []

    def node_for(p: tuple[float, float]) -> int:
        """Finn nærmeste eksisterende node innenfor tol, ellers opprett ny."""
        cx, cy = int(math.floor(p[0] * inv)), int(math.floor(p[1] * inv))
        best: int | None = None
        best_d = tol
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for ni in cell_nodes.get((cx + dx, cy + dy), ()):
                    q = node_pts[ni]
                    d = math.hypot(p[0] - q[0], p[1] - q[1])
                    if d <= best_d:
                        best, best_d = ni, d
        if best is not None:
            return best
        ni = len(node_pts)
        node_pts.append(p)
        cell_nodes[(cx, cy)].append(ni)
        return ni

    # node -> [(nabo-node, segment-indeks)]
    adj: dict[int, list[tuple[int, int]]] = defaultdict(list)
    seg_nodes: list[tuple[int, int]] = []
    for idx, (p1, p2) in enumerate(segs):
        n1, n2 = node_for(p1), node_for(p2)
        seg_nodes.append((n1, n2))
        adj[n1].append((n2, idx))
        adj[n2].append((n1, idx))

    used: set[int] = set()
    chains: list[list[tuple[float, float]]] = []

    # Start fra grad-1-noder (kjedeender) for lengst mulig kjeder; ellers alle.
    starts = [n for n in adj if len(adj[n]) == 1] or list(adj)

    for start in starts:
        while any(si not in used for _other, si in adj[start]):
            chain_pts: list[tuple[float, float]] = []
            node = start
            while True:
                cand = [(other, si) for other, si in adj[node] if si not in used]
                if not cand:
                    break
                other, si = cand[0]
                used.add(si)
                p1, p2 = segs[si]
                n1, _n2 = seg_nodes[si]
                a, b = (p1, p2) if n1 == node else (p2, p1)
                if not chain_pts:
                    chain_pts.append(a)
                chain_pts.append(b)
                node = other
            if len(chain_pts) >= 2:
                chains.append(chain_pts)

    # Segmenter som aldri ble nådd (f.eks. lukkede sykluser uten grad-1-node)
    for idx, (p1, p2) in enumerate(segs):
        if idx not in used:
            chains.append([p1, p2])

    return chains
```

- [ ] **Step 4: Fjern gammel implementasjon i renderer.py, re-eksporter**

I `src/ifc_processor/renderer.py`:

1. Endre linje 15 fra `from .cross_section import CrossSection` til:
   ```python
   from .cross_section import CrossSection, _chain_segments  # noqa: F401 — _chain_segments re-eksporteres for tester og normalprofil
   ```
2. Slett linje 6 `from collections import defaultdict` (eneste bruker var gammel `_chain_segments` — verifiser med `rg -n "defaultdict" src/ifc_processor/renderer.py`; etter sletting skal grep gi 0 treff).
3. Slett linje 108–109 (`_TOL = 1e-3 ...`-linjen med kommentar) og hele funksjonen `_chain_segments` (linje 138–195, fra `def _chain_segments(` til linjen før `def _upper_envelope_chain(`).

- [ ] **Step 5: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_cross_section.py -v -k chain_segments`
Forventet: 3 PASS.

Kjør: `pytest tests/test_renderer.py tests/test_normal_section.py -v`
Forventet: alle PASS (gamle `test_chain_segments_*` i test_renderer.py importerer fra renderer — re-eksporten dekker dem; eksakt-touch-oppførsel er bevart).

- [ ] **Step 6: Commit**

```bash
git add src/ifc_processor/cross_section.py src/ifc_processor/renderer.py tests/test_cross_section.py
git commit -m "fix(tverrprofil): toleransebasert kjeding av snittsegmenter (20 mm romlig hash)"
```

---

### Task 2: Omskrevet `stitch_cross_section_gaps` (kjede-endepunkter, gjensidig nærmeste)

Dagens stitcher (cross_section.py:155–211) sammenligner alle rå segment-endepunkter O(n²), hopper over par i samme klasse, og har derfor dokumentert lav toleranse (0,02) for å unngå stjerne-artefakter — mens pipeline overstyrer med 0,5. Ny semantikk: kjed per klasse først, bro kun mellom *kjede*-endepunkter, kun gjensidig nærmeste par, maks én bro per endepunkt, samme klasse tillatt, terreng aldri. Default `tol=0.40` (se Designbeslutning 1).

**Files:**
- Modify: `src/ifc_processor/cross_section.py:155-211` (erstatt hele funksjonen; `_PRIO` til modulnivå)
- Test: `tests/test_cross_section.py`

- [ ] **Step 1: Skriv feilende tester**

Legg til nederst i `tests/test_cross_section.py`:

```python
# ---------------------------------------------------------------------------
# stitch_cross_section_gaps — kjede-endepunkter + gjensidig nærmeste bro
# ---------------------------------------------------------------------------

from src.ifc_processor.cross_section import CrossSection, stitch_cross_section_gaps


def _cs(segments: dict) -> CrossSection:
    return CrossSection(station=0.0, elevation=100.0, segments=segments)


def test_stitch_bridges_same_class_gap():
    """200 mm gap innen samme klasse (skulder) skal broes — gammel kode nektet samme klasse."""
    cs = _cs({"skulder": [((0.0, 0.0), (1.0, 0.0)), ((1.2, 0.0), (2.2, 0.0))]})
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 3
    assert len(_chain_segments(out.segments["skulder"])) == 1


def test_stitch_bridge_lands_in_lower_priority_class():
    """Bro mellom skulder (prio 4) og groft (prio 3) skal ligge i groft."""
    cs = _cs({
        "skulder": [((0.0, 0.0), (1.0, 0.0))],
        "groft": [((1.1, -0.05), (2.0, -0.5))],
    })
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 1
    assert len(out.segments["groft"]) == 2


def test_stitch_never_bridges_terreng():
    """Terreng skal aldri broes — naturlige terrengbrudd forblir åpne."""
    cs = _cs({
        "terreng": [((0.0, 0.0), (1.0, 0.0))],
        "fylling": [((1.1, 0.0), (2.0, -0.5))],
    })
    out = stitch_cross_section_gaps(cs)
    total = sum(len(s) for s in out.segments.values())
    assert total == 2  # ingen bro lagt til


def test_stitch_ignores_gap_above_tolerance():
    """600 mm gap er over tol=0.40 — ingen bro."""
    cs = _cs({"skulder": [((0.0, 0.0), (1.0, 0.0)), ((1.6, 0.0), (2.6, 0.0))]})
    out = stitch_cross_section_gaps(cs)
    assert len(out.segments["skulder"]) == 2


def test_stitch_max_one_bridge_per_endpoint():
    """Tre kjedeender nær hverandre skal gi nøyaktig én bro (gjensidig nærmeste),
    ikke en stjerne av broer."""
    cs = _cs({"fylling": [
        ((0.0, 0.0), (1.0, 0.0)),       # ende A = (1.0, 0)
        ((1.10, 0.0), (2.0, 0.0)),      # ende B = (1.10, 0); d(A,B)=0.100
        ((1.18, 0.05), (1.5, 0.8)),     # ende C = (1.18, 0.05); d(B,C)=0.094, d(A,C)=0.187
    ]})
    out = stitch_cross_section_gaps(cs)
    total = sum(len(s) for s in out.segments.values())
    assert total == 4  # 3 originale + nøyaktig 1 bro (B<->C, gjensidig nærmeste)
```

- [ ] **Step 2: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_cross_section.py -v -k stitch`
Forventet: FAIL — `test_stitch_bridges_same_class_gap` (gammel kode hopper over samme klasse), `test_stitch_max_one_bridge_per_endpoint` (gammel kode broer ikke samme klasse i det hele tatt → total 3, ikke 4).

- [ ] **Step 3: Erstatt implementasjonen**

I `src/ifc_processor/cross_section.py`: erstatt hele `stitch_cross_section_gaps` (linje 155–211, fra `def stitch_cross_section_gaps(` til linjen før `def recenter_on_pavement(`) med:

```python
# Bro-segmenter legges i klassen med lavest prioritet, slik at broer ikke
# forstyrrer øvre-envelope-renderingen av vegdekkeklassene.
_PRIO = {
    "planum": 5, "kjørefelt": 5, "skulder": 4, "kantstein": 4, "gang_sykkel": 4,
    "groft": 3, "skjaering": 3, "fylling": 3, "terreng": 2, "unknown": 1,
}


def stitch_cross_section_gaps(
    cs: CrossSection,
    tol: float = 0.40,
) -> CrossSection:
    """Tett modelleringsgap mellom tilstøtende IFC-elementer med bro-segmenter.

    IFC-vegmodeller lagrer planum, fylling, skulder etc. som separate
    TIN-objekter. Disse møtes geometrisk, men har gap på 9–340 mm ved kantene.
    Strategi: kjed segmentene per klasse og se kun på KJEDE-endepunkter (ikke
    alle rå segment-endepunkter). Bro legges kun mellom gjensidig nærmeste
    endepunkt-par fra ulike kjeder, og hvert endepunkt brukes maks én gang.
    Det hindrer stjerne-artefakter strukturelt, slik at toleransen kan være
    høy nok (0,40 m) til å dekke reelle gap — også innen samme klasse.

    Terreng broes aldri: naturlige terrengbrudd skal forbli åpne.
    """
    # (u, v, klasse, kjede-id) for begge ender av hver kjede
    endpoints: list[tuple[float, float, str, int]] = []
    chain_id = 0
    for cls, segs in cs.segments.items():
        if cls == "terreng":
            continue
        for chain in _chain_segments(segs):
            if len(chain) < 2:
                continue
            endpoints.append((chain[0][0], chain[0][1], cls, chain_id))
            endpoints.append((chain[-1][0], chain[-1][1], cls, chain_id))
            chain_id += 1

    def nearest(i: int) -> int | None:
        """Nærmeste endepunkt fra en ANNEN kjede, innenfor tol."""
        u1, v1, _c1, ch1 = endpoints[i]
        best: int | None = None
        best_d = tol
        for j, (u2, v2, _c2, ch2) in enumerate(endpoints):
            if ch2 == ch1:
                continue
            d = math.hypot(u2 - u1, v2 - v1)
            if 1e-9 < d <= best_d:
                best, best_d = j, d
        return best

    new_segs: dict[str, list[tuple[tuple[float, float], tuple[float, float]]]] = {
        k: list(v) for k, v in cs.segments.items()
    }
    bridged: set[int] = set()
    for i in range(len(endpoints)):
        if i in bridged:
            continue
        j = nearest(i)
        if j is None or j in bridged:
            continue
        if nearest(j) != i:
            continue  # ikke gjensidig nærmeste — dropp
        u1, v1, c1, _ = endpoints[i]
        u2, v2, c2, _ = endpoints[j]
        bridged.add(i)
        bridged.add(j)
        bridge_cls = c1 if _PRIO.get(c1, 0) <= _PRIO.get(c2, 0) else c2
        new_segs.setdefault(bridge_cls, []).append(((u1, v1), (u2, v2)))

    return CrossSection(
        station=cs.station,
        elevation=cs.elevation,
        segments=new_segs,
        named_segments=cs.named_segments,
    )
```

- [ ] **Step 4: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_cross_section.py -v`
Forventet: alle PASS (5 nye stitch-tester + 3 chain-tester + eksisterende).

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/cross_section.py tests/test_cross_section.py
git commit -m "fix(tverrprofil): stitch via kjede-endepunkter og gjensidig naermeste bro (tol 0.40)"
```

---

### Task 3: Pipeline bruker ny stitch-default

**Files:**
- Modify: `src/ifc_processor/pipeline.py:353`

- [ ] **Step 1: Finn alle kallere**

Kjør: `rg -n "stitch_cross_section_gaps" src/ tests/`
Forventet: kun `src/ifc_processor/pipeline.py:353` (kall) og `src/ifc_processor/cross_section.py` (def) — pluss `scratch_diag_tverrprofil.py` i rot (håndteres i Task 9).

- [ ] **Step 2: Endre kallet**

I `src/ifc_processor/pipeline.py` linje 353, endre:

```python
            cs = stitch_cross_section_gaps(cs, tol=0.5)
```

til:

```python
            cs = stitch_cross_section_gaps(cs)
```

- [ ] **Step 3: Verifiser med eksisterende tester**

Kjør: `pytest tests/test_cross_section.py -v -k stitch`
Forventet: PASS. (Pipeline-effekten verifiseres visuelt i Task 9 — `tests/test_pipeline.py` skal ALDRI kjøres, den henger.)

- [ ] **Step 4: Commit**

```bash
git add src/ifc_processor/pipeline.py
git commit -m "fix(pipeline): bruk ny stitch-default 0.40 i tverrprofilgenerering"
```

---

### Task 4: Hull-splittende øvre envelope (`_upper_envelope_chains`)

Dagens `_upper_envelope_chain` (renderer.py:197–233) dropper NaN-bins stille, så linjen «hopper» i rett strek over fysiske hull (f.eks. midtrabatt). Ny flertallsvariant splitter ved NaN. Linspace inkluderer eksakt u_min/u_max, så envelope-endene treffer klassens ytterpunkter — sammen med Task 2-broene løser det «snap envelope-ender»-punktet strukturelt. Ubrukt `_lower_envelope_chain` slettes (YAGNI).

**Files:**
- Modify: `src/ifc_processor/renderer.py` (erstatt `_upper_envelope_chain` ~197–233; slett `_lower_envelope_chain` ~312–337; oppdater to kallere)
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Bekreft at `_lower_envelope_chain` er ubrukt**

Kjør: `rg -n "_lower_envelope_chain" src/ tests/`
Forventet: kun definisjonen i `src/ifc_processor/renderer.py`. (Treff i `.claude/worktrees/` og `docs/` ignoreres.)

- [ ] **Step 2: Oppdater og utvid testene**

I `tests/test_renderer.py`: endre importlinje 6 til:

```python
from src.ifc_processor.renderer import _chain_segments, _upper_envelope_chains, render_cross_section_svg
```

Erstatt de tre eksisterende envelope-testene (`test_upper_envelope_collapses_stacked_layers`, `test_upper_envelope_single_segment`, `test_upper_envelope_empty`) med:

```python
def test_upper_envelope_collapses_stacked_layers():
    """To lag oppå hverandre skal gi én linje langs ØVERSTE lag."""
    segs = [((-3.0, 0.0), (3.0, 0.0)), ((-3.0, -0.3), (3.0, -0.3))]
    chains = _upper_envelope_chains(segs)
    assert len(chains) == 1
    assert all(v > -0.15 for _u, v in chains[0])


def test_upper_envelope_single_segment():
    chains = _upper_envelope_chains([((0.0, 0.0), (5.0, 1.0))])
    assert len(chains) == 1
    assert len(chains[0]) >= 2


def test_upper_envelope_empty():
    assert _upper_envelope_chains([]) == []


def test_upper_envelope_splits_at_gap():
    """Fysisk hull (2–5 m udekket) skal gi to kjeder, ikke en falsk rett linje."""
    segs = [((0.0, 0.0), (2.0, 0.0)), ((5.0, 0.5), (7.0, 0.5))]
    chains = _upper_envelope_chains(segs)
    assert len(chains) == 2


def test_upper_envelope_covers_extremes():
    """Envelopen skal starte/slutte eksakt på klassens u-ytterpunkter."""
    chains = _upper_envelope_chains([((0.0, 0.0), (5.0, 0.0))])
    assert chains[0][0][0] == pytest.approx(0.0)
    assert chains[-1][-1][0] == pytest.approx(5.0)
```

(`import pytest` øverst i filen hvis det ikke allerede finnes.)

- [ ] **Step 3: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_renderer.py -v -k upper_envelope`
Forventet: ImportError — `_upper_envelope_chains` finnes ikke.

- [ ] **Step 4: Implementer flertallsvarianten**

I `src/ifc_processor/renderer.py`: erstatt hele `_upper_envelope_chain` (fra `def _upper_envelope_chain(` til linjen før `_SLOPE_CLASSES = ...`) med:

```python
def _upper_envelope_chains(
    segs: list[tuple[tuple[float, float], tuple[float, float]]],
    u_step: float = 0.1,
) -> list[list[tuple[float, float]]]:
    """Øvre envelope av segmenter, splittet i separate kjeder ved hull.

    Resampler på et regulært u-grid og tar maks v per bin. Bins uten dekning
    (NaN) markerer fysiske hull (f.eks. midtrabatt) — envelopen splittes der
    i stedet for å tegne en falsk rett linje over hullet. Linspace inkluderer
    eksakt u_min/u_max, så kjedene når klassens ytterpunkter.
    """
    if not segs:
        return []

    u_min = min(min(p1[0], p2[0]) for p1, p2 in segs)
    u_max = max(max(p1[0], p2[0]) for p1, p2 in segs)
    n = max(3, int((u_max - u_min) / u_step) + 2)
    us = np.linspace(u_min, u_max, n)
    max_v = np.full(n, np.nan)

    for (u1, v1), (u2, v2) in segs:
        if u2 < u1:
            u1, v1, u2, v2 = u2, v2, u1, v1
        du = u2 - u1
        if abs(du) < 1e-3:
            continue  # nær-vertikale segmenter bidrar ikke til overflaten
        i_lo = int(np.searchsorted(us, u1, side="left"))
        i_hi = int(np.searchsorted(us, u2, side="right"))
        for i in range(max(0, i_lo), min(n, i_hi)):
            t = min(max((us[i] - u1) / du, 0.0), 1.0)
            v = v1 + t * (v2 - v1)
            if np.isnan(max_v[i]) or v > max_v[i]:
                max_v[i] = v

    chains: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    for u, v in zip(us, max_v):
        if np.isnan(v):
            if len(current) >= 2:
                chains.append(current)
            current = []
        else:
            current.append((float(u), float(v)))
    if len(current) >= 2:
        chains.append(current)
    return chains
```

Slett deretter hele `_lower_envelope_chain` (fra `def _lower_envelope_chain(` til linjen før `def _is_pavement_label(`).

- [ ] **Step 5: Oppdater kaller 1 — vegdekke-envelope i `render_cross_section_svg`**

Erstatt blokken (renderer.py ~563–575):

```python
    if pavement_segs:
        envelope = _upper_envelope_chain(_filter_horiz_segs(pavement_segs))
        if len(envelope) >= 2:
            lines = ax.plot(
                [p[0] for p in envelope],
                [p[1] for p in envelope],
                color="black", linewidth=2.0, linestyle="-", zorder=5,
            )
            lines[0].set_gid('cs:kjørefelt')
```

med:

```python
    if pavement_segs:
        for envelope in _upper_envelope_chains(_filter_horiz_segs(pavement_segs)):
            lines = ax.plot(
                [p[0] for p in envelope],
                [p[1] for p in envelope],
                color="black", linewidth=2.0, linestyle="-", zorder=5,
            )
            lines[0].set_gid('cs:kjørefelt')
```

- [ ] **Step 6: Oppdater kaller 2 — vegdekke-gren i `_draw_named_layer_chains`**

Erstatt (renderer.py ~358–366):

```python
        if _is_pavement_label(label):
            h_segs = _filter_horiz_segs(segs)
            upper = _upper_envelope_chain(h_segs)
            if len(upper) >= 2:
                is_bindlag = "bindlag" in label.lower() or "bindelag" in label.lower()
                lw = 1.8 if is_bindlag else 0.5
                lines = ax.plot([p[0] for p in upper], [p[1] for p in upper],
                        color=color, linewidth=lw, linestyle="-", zorder=3)
                lines[0].set_gid('cs:named')
```

med:

```python
        if _is_pavement_label(label):
            h_segs = _filter_horiz_segs(segs)
            is_bindlag = "bindlag" in label.lower() or "bindelag" in label.lower()
            lw = 1.8 if is_bindlag else 0.5
            for upper in _upper_envelope_chains(h_segs):
                lines = ax.plot([p[0] for p in upper], [p[1] for p in upper],
                        color=color, linewidth=lw, linestyle="-", zorder=3)
                lines[0].set_gid('cs:named')
```

(Bindlag-spesialtilfellet fjernes i Task 8 — her bevares oppførselen uendret.)

- [ ] **Step 7: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_renderer.py tests/test_normal_section.py -v`
Forventet: alle PASS.

- [ ] **Step 8: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "fix(tverrprofil): envelope splitter ved hull i stedet for aa hoppe over dem"
```

---

### Task 5: Kjede-nivå ytterflate-filter + hele kjeder for navngitte sidekomponenter

`_outer_face_segs` (renderer.py:260–288) filtrerer per SEGMENT: skråningssegmenter lengre inn enn `tol=1.0` fra ytterkant droppes selv om de henger sammen med ytterflaten → kappede skråningslinjer. Nytt `_outer_face_chains` filtrerer per KJEDE: en kjede beholdes hvis den når ut til ytterkanten. Samtidig fikses navngitt-grenen: `max_slope=3.0` (Designbeslutning 4) og minstelengde 0,15 m på KJEDE-nivå (per-segment-filteret brøt kjedene i biter).

**Files:**
- Modify: `src/ifc_processor/renderer.py` (ny `_outer_face_chains`, slett `_outer_face_segs` ~260–288, oppdater tegneløkke ~582–597 og navngitt else-gren ~368–384)
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Skriv feilende tester**

I `tests/test_renderer.py`: utvid importlinje 6 med `_outer_face_chains`:

```python
from src.ifc_processor.renderer import (
    _chain_segments, _outer_face_chains, _upper_envelope_chains, render_cross_section_svg,
)
```

Legg til:

```python
def test_outer_face_chains_drops_interior_chain():
    """Indre flater (vegger mellom TIN-lag) skal droppes; ytterflaten beholdes."""
    chains = [
        [(0.0, 0.0), (4.0, 2.0), (8.0, 4.0)],  # når begge ytterkanter
        [(3.0, 0.0), (5.0, 1.0)],               # ren indre flate
    ]
    assert _outer_face_chains(chains) == [chains[0]]


def test_outer_face_chains_keeps_full_chain_reaching_inward():
    """En kjede som starter ved ytterkant og går innover skal beholdes HEL —
    gammel per-segment-filtrering kappet den ved tol-grensen."""
    chains = [
        [(0.0, 0.0), (8.0, 0.0)],                # definerer u-utstrekningen
        [(7.5, 0.0), (5.0, 1.0), (3.0, 2.0)],    # ytterflate som går innover
    ]
    result = _outer_face_chains(chains)
    assert chains[1] in result


def test_outer_face_chains_keeps_all_when_narrow():
    """Smal klasse (< tol utstrekning) har ingen meningsfull ytterkant — behold alt."""
    chains = [[(0.0, 0.0), (0.4, 0.2)], [(0.2, 0.0), (0.6, 0.1)]]
    assert _outer_face_chains(chains) == chains
```

- [ ] **Step 2: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_renderer.py -v -k outer_face`
Forventet: ImportError — `_outer_face_chains` finnes ikke.

- [ ] **Step 3: Implementer `_outer_face_chains` og slett `_outer_face_segs`**

I `src/ifc_processor/renderer.py`: erstatt hele `_outer_face_segs` (fra `def _outer_face_segs(` til linjen før `_NAMED_LAYER_COLORS = ...`) med:

```python
def _outer_face_chains(
    chains: list[list[tuple[float, float]]],
    tol: float = 1.0,
) -> list[list[tuple[float, float]]]:
    """Behold kjeder som når ut til ytterkantene av klassens u-utstrekning.

    TIN-solider har indre flater (vegger mellom lag) som gir doble linjer i
    snittet; ytterflaten er den som når lengst ut. Filtrering på KJEDE-nivå
    beholder hele skråningsforløpet fra ytterkant og innover, der gammel
    per-segment-filtrering kappet linjen ved tol-grensen.
    """
    pts = [p for chain in chains for p in chain]
    if not pts:
        return chains
    u_min = min(p[0] for p in pts)
    u_max = max(p[0] for p in pts)
    if u_max - u_min < tol:
        return chains  # for smal utstrekning til å skille indre/ytre
    return [
        chain for chain in chains
        if any(p[0] <= u_min + tol or p[0] >= u_max - tol for p in chain)
    ]
```

- [ ] **Step 4: Oppdater tegneløkka i `render_cross_section_svg`**

Erstatt (renderer.py ~582–586):

```python
    for road_class, segs in cross_section.segments.items():
        if road_class in _PAVEMENT_CLASSES:
            continue  # already drawn as upper envelope above
        draw_segs = _outer_face_segs(segs) if road_class in _SLOPE_CLASSES else segs
        for chain in _chain_segments(draw_segs):
```

med:

```python
    for road_class, segs in cross_section.segments.items():
        if road_class in _PAVEMENT_CLASSES:
            continue  # already drawn as upper envelope above
        chains = _chain_segments(segs)
        if road_class in _SLOPE_CLASSES:
            chains = _outer_face_chains(chains)
        for chain in chains:
```

(Resten av løkkekroppen — `_is_suspect_arm`-sjekk, terreng-gren, stil-oppslag — er uendret.)

- [ ] **Step 5: Oppdater navngitt else-gren i `_draw_named_layer_chains`**

Erstatt (renderer.py ~368–384):

```python
        else:
            # Side-komponenter (grøft, skjæring, fylling): fjern nær-loddrette sideflater
            # (vegger på TIN-solider) via slope-filter, kjedet som profil.
            # max_slope=3.0 beholder grøfteskråninger opp til ~72° mens loddrette vegger filtreres.
            clean = [
                (p1, p2) for p1, p2 in _filter_horiz_segs(segs, max_slope=2.0)
                if math.hypot(p2[0] - p1[0], p2[1] - p1[1]) >= 0.15
            ]
            for chain in _chain_segments(clean):
                if _is_suspect_arm(chain):
                    continue
                lines = ax.plot([p[0] for p in chain], [p[1] for p in chain],
                        color=color, linewidth=0.7, linestyle="-", zorder=3)
                lines[0].set_gid('cs:named')
```

med:

```python
        else:
            # Side-komponenter (grøft, skjæring, fylling): fjern nær-loddrette sideflater
            # (vegger på TIN-solider) via slope-filter, kjedet som profil.
            # max_slope=3.0 beholder grøfteskråninger opp til ~72° mens loddrette vegger filtreres.
            clean = _filter_horiz_segs(segs, max_slope=3.0)
            for chain in _chain_segments(clean):
                if _is_suspect_arm(chain):
                    continue
                # Minstelengde på KJEDE-nivå: per-segment-filter brøt kjedene i biter.
                length = sum(
                    math.hypot(chain[i + 1][0] - chain[i][0], chain[i + 1][1] - chain[i][1])
                    for i in range(len(chain) - 1)
                )
                if length < 0.15:
                    continue
                lines = ax.plot([p[0] for p in chain], [p[1] for p in chain],
                        color=color, linewidth=0.7, linestyle="-", zorder=3)
                lines[0].set_gid('cs:named')
```

- [ ] **Step 6: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_renderer.py tests/test_normal_section.py -v`
Forventet: alle PASS. (Merk: `render_normal_section_svg` bruker IKKE `_outer_face_segs` — slettingen er trygg, men kjør grep for sikkerhet: `rg -n "_outer_face_segs" src/ tests/` → 0 treff.)

- [ ] **Step 7: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "fix(tverrprofil): ytterflate-filter paa kjedenivaa + hele kjeder for navngitte sidekomponenter"
```

---

### Task 6: Hybrid presentasjon — kote-akse, kotehøyde-plassering, rent tittelfelt

Tre endringer i `render_cross_section_svg`: (a) kotehøyde-etiketten flyttes innenfor arket (i dag `ha="right"` på 2 %-posisjon → havner UTENFOR/overlapper aksen), (b) y-aksen viser kote (absolutt høyde) med ticks på hele meter — gridlinjene lander da på hele koter og referanselinja treffer en gridlinje, (c) debug-tittelfeltet (`xlim=[...]`) erstattes med et reelt tittelfelt nederst til høyre (R700).

**Files:**
- Modify: `src/ifc_processor/renderer.py` (importlinje 13, ny import `date`, tre blokker i `render_cross_section_svg`)
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Skriv feilende tester**

Legg til i `tests/test_renderer.py`:

```python
def test_y_axis_shows_kote():
    """Y-aksen skal vise absolutt kote, ikke relativ høyde. Med elevation=100.0
    skal tick-etiketten '100' finnes (senterlinjehøyden er en hel kote)."""
    cs = _simple_cross_section(elevation=100.0)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "<!-- 100 -->" in content
    assert "Kote (m)" in content


def test_no_debug_text_in_title_block():
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "xlim" not in content


def test_title_block_contains_maalestokk():
    cs = _simple_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "Målestokk 1:200" in content
```

- [ ] **Step 2: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_renderer.py -v -k "kote or debug_text or maalestokk"`
Forventet: 3 FAIL (y-aksen viser relativ høyde; «xlim» finnes i debug-teksten; «Målestokk» finnes ikke).

- [ ] **Step 3: Oppdater importer**

I `src/ifc_processor/renderer.py`: endre linje 13 fra

```python
from matplotlib.ticker import MultipleLocator
```

til

```python
from matplotlib.ticker import FixedLocator, FuncFormatter, MultipleLocator
```

og legg til etter `import math` (linje 5):

```python
from datetime import date
```

(FixedLocator + FuncFormatter brukes i stedet for `MultipleLocator(offset=...)` som krever matplotlib ≥ 3.8 — unngår versjonsrisiko.)

- [ ] **Step 4: Kote-akse i grid-blokken**

I `render_cross_section_svg`, erstatt linjen:

```python
    ax.yaxis.set_major_locator(MultipleLocator(1.0))
```

med:

```python
    # Y-ticks på HELE KOTER (absolutt høyde): gridlinjer lander på hele meter
    # i kote, og referanselinja (heltallskote) treffer en gridlinje.
    elev = cross_section.elevation
    kote_lo = math.ceil(y_lo + elev)
    kote_hi = math.floor(y_hi + elev)
    ax.yaxis.set_major_locator(FixedLocator([k - elev for k in range(kote_lo, kote_hi + 1)]))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _pos: f"{v + elev:.0f}"))
```

og erstatt y-akse-etiketten:

```python
    ax.set_ylabel(f"Høyde (m)", fontsize=7)
```

med:

```python
    ax.set_ylabel("Kote (m)", fontsize=7)
```

- [ ] **Step 5: Flytt kotehøyde-etiketten på referanselinja**

Erstatt:

```python
    ax.text(
        x_lo + (x_hi - x_lo) * 0.02, ref_line_v,
        f"{ref_elev_abs}",
        va="center", ha="right", fontsize=7, fontfamily="monospace",
    )
```

med:

```python
    ax.text(
        x_lo + (x_hi - x_lo) * 0.01, ref_line_v + 0.10,
        f"{ref_elev_abs}",
        va="bottom", ha="left", fontsize=7, fontfamily="monospace",
    )
```

- [ ] **Step 6: Erstatt debug-tittelfeltet**

Erstatt:

```python
    fig.text(
        0.98, 0.02,
        f"SVV · R700 · 1:200 · Stasjon {cross_section.station:.2f} m · xlim=[{ax.get_xlim()[0]:.0f},{ax.get_xlim()[1]:.0f}]",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )
```

med:

```python
    # Tittelfelt nederst til høyre (R700) — uten debug-info
    fig.text(
        0.98, 0.02,
        f"Tverrprofil · Profil {cross_section.station:.2f} · Målestokk 1:200 · {date.today().isoformat()}",
        ha="right", va="bottom", fontsize=5, color="#555555",
    )
```

- [ ] **Step 7: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_renderer.py -v`
Forventet: alle PASS — inkludert eksisterende `test_svg_contains_scale_1_200` («1:200» finnes fortsatt, nå i «Målestokk 1:200») og `test_kotehøyde_label_is_whole_metre` (etikett-teksten `<!-- 98 -->` er uendret, bare flyttet).

- [ ] **Step 8: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "feat(tverrprofil): kote-akse, flyttet kotehoydeetikett og rent tittelfelt (hybrid R700)"
```

---

### Task 7: Tegnforklaring per ark

R700: hvert ark skal ha tegnforklaring som forklarer symbolene som faktisk er brukt — og BARE dem. Legenden bygges betinget med `Line2D`-proxyer.

**Files:**
- Modify: `src/ifc_processor/renderer.py` (ny import, blokk før tittelen i `render_cross_section_svg`)
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Skriv feilende test**

Legg til i `tests/test_renderer.py`:

```python
def test_svg_contains_tegnforklaring():
    cs = _full_cross_section()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "Tegnforklaring" in content
    assert "Prosjektert vegoverflate" in content
```

- [ ] **Step 2: Kjør testen — forventet FAIL**

Kjør: `pytest tests/test_renderer.py -v -k tegnforklaring`
Forventet: FAIL — «Tegnforklaring» finnes ikke i SVG-en.

- [ ] **Step 3: Implementer legenden**

Legg til import etter `from matplotlib.ticker import ...` (linje 13):

```python
from matplotlib.lines import Line2D
```

I `render_cross_section_svg`, rett FØR linjen `ax.set_title(f"Profil {cross_section.station:.2f}", ...)`, sett inn:

```python
    # Tegnforklaring (R700: forklar symbolene som er brukt på arket — og bare dem)
    legend_handles = []
    if pavement_segs:
        legend_handles.append(
            Line2D([], [], color="black", lw=2.0, label="Prosjektert vegoverflate"))
    if any(c in cross_section.segments for c in _SLOPE_CLASSES):
        legend_handles.append(
            Line2D([], [], color="black", lw=1.0, label="Skjæring/fylling/grøft"))
    if "terreng" in cross_section.segments:
        legend_handles.append(
            Line2D([], [], color="black", lw=0.8, label="Eksisterende terreng"))
    if cross_section.named_segments:
        legend_handles.append(
            Line2D([], [], color="#555555", lw=0.5, label="Laggrenser (IFC)"))
    if legend_handles:
        ax.legend(
            handles=legend_handles, loc="upper right", fontsize=5.5,
            title="Tegnforklaring", title_fontsize=6, framealpha=0.9,
            edgecolor="#888888", borderpad=0.6, handlelength=2.2,
        )
```

(`pavement_segs` er allerede definert tidligere i funksjonen.)

- [ ] **Step 4: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_renderer.py -v`
Forventet: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "feat(tverrprofil): tegnforklaring med kun brukte symboler (R700)"
```

---

### Task 8: Etikett-støy («Triangelnett - N») + bindlag-vekt

To symbologi-fikser: (a) generiske IFC-navn som «Triangelnett - 4» er navnestøy uten faglig verdi — callouten droppes (geometrien tegnes fortsatt), (b) bindlag tegnes i dag med lw=1.8 — TYKKERE enn selve vegoverflate-konturen i navngitt-laget (vektinversjon); alle navngitte vegdekke-lag skal ha lw=0.5.

**Files:**
- Modify: `src/ifc_processor/renderer.py` (ny `_is_generic_label` + `import re`; skip i `_draw_named_labels`; fjern bindlag-spesialtilfellet i `_draw_named_layer_chains`)
- Test: `tests/test_renderer.py`

- [ ] **Step 1: Skriv feilende tester**

I `tests/test_renderer.py`: utvid renderer-importen med `_is_generic_label`. Legg til:

```python
def test_is_generic_label():
    from src.ifc_processor.renderer import _is_generic_label
    assert _is_generic_label("Triangelnett - 4")
    assert _is_generic_label("triangelnett")
    assert not _is_generic_label("Bindlag 1")
    assert not _is_generic_label("V. Grøft 2")


def test_generic_triangelnett_callout_suppressed():
    """Geometrien tegnes, men callout-etiketten 'Triangelnett - N' skal vekk."""
    cs = CrossSection(
        station=50.0, elevation=100.0,
        segments={"planum": [((-3.0, 0.0), (3.0, 0.0))]},
        named_segments={"Triangelnett - 4": [((-2.0, -0.5), (2.0, -0.5))]},
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "Triangelnett" not in content


def test_bindlag_drawn_thin():
    """Bindlag skal IKKE tegnes tykkere enn vegoverflaten (gammel lw=1.8)."""
    cs = CrossSection(
        station=50.0, elevation=100.0,
        segments={"planum": [((-3.0, 0.0), (3.0, 0.0))]},
        named_segments={"Bindlag 1": [((-3.0, -0.1), (3.0, -0.1))]},
    )
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "test.svg"
        render_cross_section_svg(cs, out)
        content = out.read_text(encoding="utf-8")
    assert "stroke-width: 1.8" not in content
    assert "stroke-width:1.8" not in content
```

- [ ] **Step 2: Kjør testene — forventet FAIL**

Kjør: `pytest tests/test_renderer.py -v -k "generic or bindlag"`
Forventet: ImportError på `_is_generic_label`; `test_bindlag_drawn_thin` FAIL.

- [ ] **Step 3: Implementer**

I `src/ifc_processor/renderer.py`:

1. Legg til `import re` etter `import math` (linje 5).
2. Legg til rett før `def _is_pavement_label(`:

```python
_GENERIC_LABEL_RE = re.compile(r"(?i)^\s*triangelnett")


def _is_generic_label(label: str) -> bool:
    """Etiketter som 'Triangelnett - 4' er IFC-navnestøy uten faglig verdi —
    geometrien tegnes, men callouten droppes."""
    return bool(_GENERIC_LABEL_RE.match(label))
```

3. I `_draw_named_labels`: finn løkka som itererer over `sorted(named_segments.items())` (der `label_positions` bygges) og legg til som FØRSTE linjer i løkkekroppen:

```python
        if _is_generic_label(label):
            continue
```

4. I `_draw_named_layer_chains`, vegdekke-grenen (etter Task 4-endringen): slett de to linjene

```python
            is_bindlag = "bindlag" in label.lower() or "bindelag" in label.lower()
            lw = 1.8 if is_bindlag else 0.5
```

og endre `linewidth=lw` til `linewidth=0.5` i plot-kallet, slik at grenen blir:

```python
        if _is_pavement_label(label):
            h_segs = _filter_horiz_segs(segs)
            for upper in _upper_envelope_chains(h_segs):
                lines = ax.plot([p[0] for p in upper], [p[1] for p in upper],
                        color=color, linewidth=0.5, linestyle="-", zorder=3)
                lines[0].set_gid('cs:named')
```

- [ ] **Step 4: Kjør testene — forventet PASS**

Kjør: `pytest tests/test_renderer.py tests/test_normal_section.py -v`
Forventet: alle PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ifc_processor/renderer.py tests/test_renderer.py
git commit -m "fix(tverrprofil): skjul Triangelnett-callouts og fjern bindlag-vektinversjon"
```

---

### Task 9: Visuell verifisering (st. 120/400/800) + opprydding

**Denne tasken utføres av hovedsesjonen (visuell vurdering), ikke en subagent.** Sammenlign før/etter mot samme jobbdata og mot U201-eksempelet.

**Files:**
- Modify: `scratch_diag_tverrprofil.py:37` (deretter SLETT filen)
- Delete: `scratch_diag_out/`, `scratch_diag_out_before/`

- [ ] **Step 1: Bevar før-bildene**

`scratch_diag_out/` inneholder PNG-ene fra diagnosen (gammel kode). Kjør i PowerShell:

```powershell
Rename-Item scratch_diag_out scratch_diag_out_before
```

- [ ] **Step 2: Oppdater diagnoseskriptet til ny stitch-signatur**

I `scratch_diag_tverrprofil.py` linje 37, endre:

```python
    cs = stitch_cross_section_gaps(cs, tol=0.5)
```

til:

```python
    cs = stitch_cross_section_gaps(cs)
```

- [ ] **Step 3: Kjør diagnosen på ny kode**

Kjør: `python scratch_diag_tverrprofil.py`
Forventet: PNG/SVG i `scratch_diag_out/`; stdout viser kjedetall per klasse. Suksesskriterier mot før-tallene:
- st. 120: skulder 10 seg → 1 kjede (før: 4 kjeder, gap 25/36/198 mm)
- st. 400: antall endepunkt-gap 1 mm–1 m vesentlig redusert (før: 8 gap 39–308 mm)
- st. 800: grøft 18 seg → få kjeder (før: 13 kjeder, gap 9/47/235/337 mm)

- [ ] **Step 4: Visuell sammenligning**

Les (Read-verktøyet) og sammenlign parvis:
- `scratch_diag_out/tp_00120.png` mot `scratch_diag_out_before/tp_00120.png`
- `scratch_diag_out/tp_00400.png` mot `scratch_diag_out_before/tp_00400.png`
- `scratch_diag_out/tp_00800.png` mot `scratch_diag_out_before/tp_00800.png`
- og mot `C:\Users\jornk\.claude\skills\r700-tverrprofil\assets\examples\U201-tverrprofil.png`

Sjekkliste: (1) linjer henger sammen — ingen fragmenterte skuldre/grøfter, (2) ingen falsk linje over fysiske hull, (3) skråninger ikke kappet, (4) y-akse viser kote og referanselinja ligger på en gridlinje, (5) kotehøydeetikett innenfor arket, (6) tegnforklaring øverst til høyre med kun brukte symboler, (7) tittelfelt nederst til høyre uten xlim-debug, (8) ingen «Triangelnett»-callouts, (9) terreng som tynn heltrukken linje med tick-grupper (matcher U201), (10) lesbart i svart-hvitt.

Hvis noe feiler: fiks, kjør målrettede tester på nytt, re-render og sammenlign igjen før opprydding.

- [ ] **Step 5: Opprydding**

```powershell
Remove-Item scratch_diag_tverrprofil.py -Confirm:$false
Remove-Item -Recurse -Force scratch_diag_out, scratch_diag_out_before
```

- [ ] **Step 6: Full målrettet testkjøring (ALDRI hele suiten)**

Kjør: `pytest tests/test_renderer.py tests/test_cross_section.py tests/test_normal_section.py -v`
Forventet: alle PASS.

- [ ] **Step 7: Commit (kun hvis Step 4 medførte kodeendringer)**

```bash
git add src/ifc_processor/ tests/
git commit -m "fix(tverrprofil): justeringer etter visuell verifisering mot U201"
```
