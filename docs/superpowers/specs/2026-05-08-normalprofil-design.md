# Normalprofil per tverrprofil-stasjon — designspesifikasjon

**Dato:** 2026-05-08
**Scope:** Automatisk generering av R700-normalprofil (dimensjonert snitt med mål og etiketter) per tverrprofil-stasjon, publisert som eget SVG-vedlegg på tilhørende AGOL-punkt.

---

## Mål

For hvert tverrprofil-punkt i AGOL skal det finnes to navngitte SVG-vedlegg:

- `tverrprofil_XXXXX.X.svg` — geometrisk snitt i 1:200 (eksisterende)
- `normalprofil_XXXXX.X.svg` — dimensjonert snitt i 1:50 med bredder, tverrfall, skråningsforhold og komponentetiketter (ny)

Normalprofilen genereres fullt automatisk fra IFC-geometrien (tilnærming A). Designet er utvidbart: når IFC-modellen inneholder lagpakker (slitelag, bærelag, forsterkningslag etc.) kan disse plugges inn uten arkitekturendring.

---

## Arkitektur

```
CrossSection (eksisterende)
    │
    ├─► compute_normal_section()   → NormalSection   [NY: normal_section.py]
    │
    ├─► render_cross_section_svg() → tverrprofil SVG [eksisterende renderer.py]
    └─► render_normal_section_svg()→ normalprofil SVG [NY funksjon i renderer.py]

pipeline.py  ← kaller begge render-funksjoner per stasjon, lagrer begge stier i metadata
tverrprofil_to_agol.py  ← legger ved begge SVGer per AGOL-punkt
```

Ingen endringer i `job_runner.py`, `server.py` eller frontend.

---

## Nye filer og moduler

### `src/ifc_processor/normal_section.py` — NY

#### `NormalSection` dataclass

```python
@dataclass
class NormalSection:
    station: float
    elevation: float

    left_carriageway_width: float   # m fra CL, NaN hvis mangler
    right_carriageway_width: float
    left_shoulder_width: float      # NaN hvis mangler
    right_shoulder_width: float
    left_ditch_depth: float         # vertikal dybde, NaN hvis ingen grøft
    right_ditch_depth: float
    left_slope_ratio: float         # 1:x for skjæring/fylling, NaN hvis ingen
    right_slope_ratio: float
    left_cross_fall_pct: float      # % fall, NaN hvis ikke beregnes
    right_cross_fall_pct: float
    section_type: str               # "skjæring" | "fylling" | "plan" | "kombinasjon"
```

#### `compute_normal_section(cs: CrossSection) -> NormalSection`

Itererer over `cs.segments` og utleder dimensjoner:

- **Bredder**: ytterste u-koordinat per klasse per side (u<0 = venstre, u>0 = høyre).
  - `kjørefelt`-bredde = `max(|u|)` for `kjørefelt`-segmenter på hver side
  - `skulder`-bredde = `max(|u|)` for `skulder` minus `kjørefelt` yttergrense
- **Tverrfall**: `Δv/Δu × 100` langs `kjørefelt`-segmenter, per side
- **Skråningsforhold**: `|Δu/Δv|` langs `skjaering`/`fylling`-segmenter → uttrykkes som `1:x` (avrundet til én desimal)
- **Grøftdybde**: vertikal avstand mellom øverste og nederste punkt i `groft`-segmenter per side
- **section_type**:
  - Har `skjaering` men ikke `fylling` → `"skjæring"`
  - Har `fylling` men ikke `skjaering` → `"fylling"`
  - Har begge → `"kombinasjon"`
  - Ingen av dem → `"plan"`
- Manglende klasser gir `float("nan")` — rendereren hopper over tilhørende annotasjon

---

### `src/ifc_processor/renderer.py` — UTVIDET

#### `render_normal_section_svg(cs: CrossSection, output_path: Path) -> Path` — NY

Kaller `compute_normal_section(cs)` internt, renderer til SVG.

**Tegningsoppsett:**
- Papirformat: A3 landskap (420 × 297 mm)
- Skala: **1:50** (1 m = 20 mm på papir) — angitt i tittelfelt
- Grid: 1 m × 1 m i verdenskoordinater (`MultipleLocator(1.0)`, x-etiketter hvert 5 m)
- Tittel øverst venstre: `Normalprofil {station:.2f}`
- Tittelfelt nederst høyre: `SVV · R700 · 1:50 · Stasjon {station:.2f} m`
- Referanselinje med snappet kotehøyde (`_snap_ref_elevation`)
- SL-merke ved u=0

**Annotasjonslag (i rekkefølge):**

| Lag | Farge | Innhold |
|---|---|---|
| Geometri | Sort | Solid for prosjektert, stiplet for terreng — identisk stil som tverrprofil |
| Breddemål | Rød | Dimensjonslinjer med piler over vegbanen: kjørefelt og skulder |
| Tverrfall | Mørkegrå | `3%` med skråpil på kjørebaneflaten, per side |
| Skråningsforhold | Grønn | `1:1.5` langs skjærings-/fyllingslinje, per side |
| Komponentetiketter | Sort, 6 pt | `kjørefelt`, `skulder`, `grøft`, `skjæring`/`fylling` med lederlinjer |

**Tegnforklaring** nederst til venstre (én per SVG):
- Solid linje = prosjektert geometri
- Stiplet linje = eksisterende terreng

**NaN-håndtering:** Alle annotasjoner sjekkes mot NaN før tegning — manglende dimensjoner utelates stille, tegningen er alltid gyldig SVG.

---

## Endringer i eksisterende filer

### `src/ifc_processor/pipeline.py`

1. Importer `render_normal_section_svg`
2. Endre filnavn fra `station_{dist:07.1f}.svg` til `tverrprofil_{dist:07.1f}.svg`
3. Generer `normalprofil_{dist:07.1f}.svg` i samme løkke
4. Utvid `metadata_rows` med felt `normal_svg`
5. Returner `normal_svgs`-liste i pipeline-resultatet

```python
svg_path        = output_dir / f"tverrprofil_{s.distance:07.1f}.svg"
normal_svg_path = output_dir / f"normalprofil_{s.distance:07.1f}.svg"

render_cross_section_svg(cs, svg_path)
render_normal_section_svg(cs, normal_svg_path)
```

### `src/arcpy_processor/tverrprofil_to_agol.py`

Filen bruker en match-tabell (`AddAttachments`) for å feste vedlegg. Endringen er:

1. Oppdater SVG-søkemønster fra `station_{m:07.1f}.svg` til `tverrprofil_{m:07.1f}.svg`
2. Legg til **to rader per OID** i match-tabellen — én for tverrprofil-SVG og én for normalprofil-SVG:

```python
for oid, station_m in cur:
    tp_svg  = svgs_dir / f"tverrprofil_{station_m:07.1f}.svg"
    np_svg  = svgs_dir / f"normalprofil_{station_m:07.1f}.svg"
    for svg in (tp_svg, np_svg):
        if svg.exists():
            ins.insertRow((oid, str(svg)))
        else:
            logger.warning("SVG ikke funnet: %s", svg)
```

ArcPy sin `AddAttachments` støtter flere rader per OID i match-tabellen.

---

## Output i AGOL

Hvert tverrprofil-punkt i AGOL-tjenesten vil ha to vedlegg:

```
Punkt (stasjon 4920.0 m)
├── tverrprofil_4920.0.svg   ← geometrisk snitt 1:200
└── normalprofil_4920.0.svg  ← dimensjonert snitt 1:50
```

---

## Teststrategi

| Fil | Hva testes |
|---|---|
| `tests/test_normal_section.py` (NY) | `compute_normal_section`: bredder, tverrfall, skråningsforhold, NaN for manglende klasser, `section_type` |
| `tests/test_renderer.py` | `render_normal_section_svg` produserer gyldig SVG med "1:50" og profilnummer |
| `tests/test_pipeline.py` | Filnavn er `tverrprofil_*` og `normalprofil_*`, `normal_svg`-felt i metadata |

Eksisterende tester som refererer `station_XXXXX.X.svg` oppdateres til `tverrprofil_XXXXX.X.svg`.

---

## Utenfor scope

- Lagpakker (slitelag, bærelag, forsterkningslag) — legges til når IFC inneholder dette
- Type-baserte normalprofil-maler (tilnærming B) — ikke nødvendig med tilnærming A
- Lengdeprofil-vedlegg — eget fremtidig feature
- Kombinert SVG/PDF med begge tegninger på én side
