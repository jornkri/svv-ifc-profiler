# BIM-kategorisering for 3D + C-plan — designspesifikasjon

**Dato:** 2026-05-29
**Scope:** Omstrukturere BIM-publiseringen så IFC-data blir kategorisert fagmessig
(grøft, bindlag, bærelag, fylling …) i stedet for Esris rå geometriklasser
(Courses, Kerbs, ExteriorShell …). Resultatet skal kunne vises både som 3D-modell
og som 2D C-plan (R700) i profilutforsker-web.

> **Denne iterasjonen:** pipeline + publisering (datastrukturen).
> **Neste iterasjon (egen spec):** webvisning i profilutforsker.

---

## Problem

Dagens flyt (`arcpy_processor/converter.py`) kjører `BIMFileToGeodatabase` og
publiserer resultatet råt. Esri deler da dataene etter sine egne IFC-geometriklasser,
og produserer doble lag (3D multipatch + 2D-fотavtrykk) per klasse:

```
ExteriorShell model / model 1
DistributionChambers model / model 1
Courses model / model 1
Kerbs model / model 1
```

Dette er ubrukelig for en C-plan — lagene sier ingenting om hva objektene *er*
fagmessig. Vi vil ha lag som betyr noe: grøft, bindlag, bærelag, fylling, skjæring osv.

---

## Mål

Publisere én feature service med **to lag**, begge kategorisert på attributt:

- **`[0] bim_3d`** — multipatch (3D-objektlag) for SceneView/3D-visning.
- **`[1] bim_plan`** — polygon-fотavtrykk for 2D C-plan i MapView.

Begge bærer feltene `kategori`, `fag_gruppe`, `ifc_klasse`, `navn`. Symbolisering og
lagvelger styres av web-appen (neste iterasjon) basert på `kategori` — derfor holder
det med to fysiske lag, uavhengig av hvor mange kategorier som finnes.

---

## Arkitektur

Beholder den eksisterende todelingen:

- **Klassifisering** skjer i ren Python (ifcopenshell) — testbar uten ArcGIS Pro.
- **Geometri** håndteres i ArcPy — isolerer Windows/ArcGIS-avhengigheten.

```
src/ifc_processor/
  bim_classifier.py    ← NY: IFC → {GlobalId: (kategori, fag_gruppe, ifc_klasse, navn)}

src/arcpy_processor/
  converter.py         ← UTVIDES: merge → join kategori → fотavtrykk → 2 FC-er
  bim_to_agol.py       ← uendret arbeidsflyt (publiserer hele GDB)
  publisher.py         ← uendret
```

---

## Klassifisering (`bim_classifier.py`)

Ren funksjon `classify(element) -> (kategori, fag_gruppe)` og en modul-API
`classify_ifc(ifc_path) -> dict[str, ClassifiedElement]` keyet på `GlobalId`.

Klassifiseringen baseres primært på IFC-klasse + `PredefinedType`/`ObjectType`
(rene ASCII-koder, pålitelige), og nøkkelord i `Name` der det trengs. `Name`-feltet
har encoding-artefakter (æ/ø/å kommer som mojibake), så nøkkelordmatch må være
ASCII-tolerant: match på trygge delstrenger (`"relag"` for Bærelag) og bruk
`PredefinedType`/`ObjectType` der `Name` er upålitelig (Kjørefelt, Grøft).

### Kategoritabell

| fag_gruppe | kategori | kilde-regel (prioritert rekkefølge) |
|---|---|---|
| Vegoverbygning | Slitelag | `IfcCourse` Name⊃"Slitelag"; `IfcPavement` |
| Vegoverbygning | Bindlag | `IfcCourse` Name⊃"Bindlag" |
| Vegoverbygning | Bærelag | `IfcCourse` Name⊃"relag" (etter Filter/Forsterkning) |
| Vegoverbygning | Forsterkningslag | `IfcEarthworksFill` Name⊃"Forsterkningslag" |
| Vegoverbygning | Filterlag | `IfcEarthworksFill` Name⊃"Filterlag" |
| Vegbane | Kjørefelt | `IfcCourse` ObjectType=TRAFFICLANE_SURFACE (inkl. breddeutvidelse) |
| Vegbane | Skulder | `IfcCourse` ObjectType=ROADSHOULDER_SURFACE |
| Vegbane | Kantstein | `IfcKerb` |
| Underbygning | Planum | `IfcEarthworks*` PredefinedType⊃SUBGRADE; Name⊃"Constructionbed"/"Subgrade" |
| Underbygning | Forsterket grunn | `IfcReinforcedSoil`; Name⊃"Fyllingslag" |
| Terreng | Fylling | `IfcEarthworksFill` PredefinedType∈{SLOPEFILL, EMBANKMENT}; Name⊃"Fylling" |
| Terreng | Skjæring | `IfcEarthworksCut/Fill` Name⊃"Jordskj"/"Fjellskj"/"InCutSoil"/"InCutRock"/"RockCutFace"/"Dypsprenging" |
| Terreng | Avrunding | Name⊃"Avrunding" |
| Drenering | Grøft | `IfcDistributionChamberElement` PredefinedType=TRENCH |

Elementer uten solid geometri droppes fra begge lag: `IfcAnnotation`,
`IfcRoadPart`, `IfcRoad`, `IfcSite`, `IfcGeomodel`.

Ukjent kombinasjon → `(kategori="Uklassifisert", fag_gruppe="Annet")` (tas med,
men logges, så ingenting forsvinner stille).

`ClassifiedElement` (dataclass): `global_id, ifc_klasse, navn, kategori, fag_gruppe`.

---

## ArcPy-steg (`converter.py`)

1. `BIMFileToGeodatabase(ifc, gdb, dataset, sr)` — som i dag.
2. Slett tomme FC-er (eksisterende logikk).
3. **Merge** alle gjenværende multipatch-FC-er til én FC `bim_3d`.
4. Legg til feltene `kategori, fag_gruppe, ifc_klasse, navn` (TEXT) på `bim_3d`.
5. **Join kategori:** for hver feature, slå opp IFC-GlobalId i klassifiseringsdict-en
   og skriv kategori-feltene (`UpdateCursor`).
6. **Fотavtrykk:** `arcpy.ddd.MultiPatchFootprint(bim_3d, bim_plan)` → polygon-FC,
   ett fотavtrykk per element. Overfør kategori-feltene (footprint beholder
   kildefeltene, evt. join tilbake på OID).
7. (Hvis `input_wkid != output_wkid`) reprosjekter begge FC-er til 25833.
8. GDB inneholder nå nøyaktig 2 FC-er → `bim_to_agol.py` publiserer som før.

### Join-nøkkel — risiko å verifisere tidlig

Steg 5 forutsetter at `BIMFileToGeodatabase` legger igjen et felt med IFC-GlobalId.
**Verifiseres på Windows før resten bygges.** Hvis feltet mangler:

- **Fallback:** re-utled kategori direkte fra GDB-feltene `ObjectType` + `Name`
  (samme klassifiseringsregler, men mer sårbart for encoding). `bim_classifier`
  eksponerer derfor også `classify_from_fields(ifc_klasse, object_type, name)` som
  begge stier kan dele.

---

## Output

Feature service uendret format fra `publisher.py`, men nå med 2 meningsfulle lag:

```
SVV_<navn>_bim  (Feature Service)
  [0] bim_3d    (multipatch)  — kategori, fag_gruppe, ifc_klasse, navn
  [1] bim_plan  (polygon)     — kategori, fag_gruppe, ifc_klasse, navn
```

Spatial reference: EPSG:25833 (ETRS89 / UTM 33N), som resten av prosjektet.

---

## Feilhåndtering

Gjenbruker eksisterende `ArcpyProcessorError`-koder. Nye situasjoner:

| Situasjon | Håndtering |
|---|---|
| IFC-GlobalId-felt mangler i GDB | Logg advarsel, bruk `classify_from_fields`-fallback |
| Element uten kategori-treff | `kategori="Uklassifisert"`, logg antall |
| `MultiPatchFootprint` feiler | `BIM_CONVERSION_FAILED` med tydelig melding |

---

## Testing

- **`tests/test_bim_classifier.py`** — parametriserte tester mot ekte
  `samples/m_f_veg_12200_Veg.ifc`:
  - hver IFC-klasse/PredefinedType havner i forventet kategori,
  - encoding-tolerant nøkkelordmatch (Bærelag→"Bærelag", Grøft→"Grøft"),
  - `classify` og `classify_from_fields` gir samme resultat for samme input,
  - ingen produkter med solid geometri ender som "Uklassifisert" i sample.
- **ArcPy-stegene mockes** som i `test_ifc_cl_to_agol.py` (MagicMock for arcpy).
  Verifiser at converter kaller Merge → AddField → MultiPatchFootprint og at
  kategori-feltene settes.

---

## Utenfor scope (denne iterasjonen)

- Webvisning i profilutforsker (3D SceneView + 2D C-plan MapView, renderer,
  lagvelger) — egen spec neste runde.
- Symbologi/tegnforklaring etter R700.
- Dissolve av fотavtrykk per kategori (vi beholder per-element-fотavtrykk).
- Batch av flere IFC-filer.
