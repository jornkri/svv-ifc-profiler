# IFC-senterlinje (IFC4X3 IfcAlignment) som alternativ til LandXML

**Status:** Spec — godkjent for implementasjon
**Dato:** 2026-05-28
**Forfatter:** jorn.kristiansen (m. Claude)

## Sammendrag

Utvid pipeline og web-app til å akseptere `IfcAlignment` fra en IFC4X3-fil
som senterlinje-kilde, parallelt med eksisterende LandXML-støtte. Bakgrunnen
er nye SVV-leveranser (eksempel: `samples/m_f-veg_12200_CL.ifc`) der senterlinjen
distribueres som egen IFC-fil i tillegg til vegmodell-IFC-en.

IFC-CL-formatet er rikere enn LandXML — det inneholder eksplisitte
horisontal-segmenter (linje/sirkel/klotoide), vertikalsegmenter
(rett/parabel/sirkel) og `IfcReferent`-stasjoneringsmerker. Vi utnytter
disse til å gi mer presis lengdeprofil-rubrikk, riktige profilnummer
(P 100, P 200, …) og ekstra AGOL-attributter.

## Motivasjon

- SVV-leveranse 12200 har senterlinjen i IFC, ikke LandXML
- LandXML-veien er bevart for prosjekter som FV229 og 70400 som ikke har IFC-CL
- IFC-CL gir oss klotoidegrenser og vertikalradier som i dag rekonstrueres fra
  retningsendringer (mindre presist)
- IfcReferent gir offisielle stasjoneringsnumre som vi i dag genererer fra 0

## Ikke-mål

- Støtte for IFC-CL i andre schema-versjoner enn IFC4X3
- Skrive IFC-CL ut (kun lesing)
- IfcAlignment med flere parallelle representasjoner (kun første velges)

## Arkitektur

```
src/ifc_processor/
  alignment_parser.py     ← NY. IFC4X3 → IfcAlignmentData.
  centerline.py           ← Utvid load_centerline() med .ifc-gren.
  pipeline.py             ← Format-agnostisk metadata via _load_alignment_metadata().

src/arcpy_processor/
  ifc_cl_to_agol.py       ← NY. Parallell CLI til landxml_to_agol.
  _polyline_publisher.py  ← NY. Felles publish-flyt.
  landxml_to_agol.py      ← Tynnes ut til CLI + parser-kall.

src/api/
  server.py               ← cl_file: UploadFile godtar .xml ELLER .ifc.
  job_runner.py           ← Router til riktig AGOL-CLI basert på filending.

web/src/main.js + index.html
                          ← Dropzone 2 godtar nå .xml,.ifc.
```

**Felles datakontrakt nedstrøms for parser:**
- `Centerline` — eksisterer
- `HorizontalAlignment` — eksisterer (`horizontal_alignment.json`); IFC-veien produserer den nå også
- `VerticalProfile` — matcher LandXML-veiens `load_vertical_profile()`-output
- `StationLabels` — nytt; tom liste for LandXML, fylt for IFC-CL

## Datamodell (alignment_parser.py)

```python
@dataclass
class HorizontalSegment:
    start_station: float
    length: float
    start_point: tuple[float, float]
    start_direction: float
    segment_type: str            # "LINE" | "CIRCULARARC" | "CLOTHOID"
    start_radius: float | None = None
    end_radius: float | None = None
    is_ccw: bool | None = None

@dataclass
class VerticalSegment:
    start_station: float
    length: float
    start_height: float
    start_gradient: float        # m/m
    segment_type: str            # "CONSTANTGRADIENT" | "PARABOLICARC" | "CIRCULARARC"
    radius: float | None = None  # signert: + dal, − topp

@dataclass
class StationLabel:
    station: float
    name: str                    # IfcReferent.Name, f.eks. "P 100"
    position: tuple[float, float, float]

@dataclass
class IfcAlignmentData:
    name: str
    points_3d: np.ndarray         # (M, 3), samplet fra IfcGradientCurve
    stations: np.ndarray          # (M,)
    horizontal_segments: list[HorizontalSegment]
    vertical_segments: list[VerticalSegment]
    station_labels: list[StationLabel]
    source_epsg: int = 25833

    def to_centerline(self) -> Centerline: ...
    def vertical_profile_pvi(self) -> list[tuple[float, float]]: ...
```

**Sampling-tetthet `points_3d`:** ~1 m, tettere ved kurver (parametrisert).

## Parser-implementasjon (`load_alignment_from_ifc`)

1. **Velg alignment.** Først `IfcAlignment` med Curve3D-representasjon. Hvis flere,
   velg lengste; logg navnene som ble forkastet. Senere CLI-flagg `--alignment-name`
   for overstyring.
2. **Horisontalsegmenter.** Iterer `IfcAlignmentHorizontal.IsNestedBy` →
   `IfcAlignmentSegment` → `DesignParameters` (`IfcAlignmentHorizontalSegment`):
   - `LINE` → rett, ingen radius
   - `CIRCULARARC` → konstant radius, `is_ccw` fra fortegn
   - `CLOTHOIDCURVE` → `start_radius`/`end_radius` fra IFC
   - Ukjent type → warning, fall tilbake til klotoid/linje basert på radius
3. **Vertikalsegmenter.** Tilsvarende fra `IfcAlignmentVertical`:
   - `CONSTANTGRADIENT` → rett
   - `PARABOLICARC` → radius m. tegn fra `StartGradient`/`EndGradient`
   - `CIRCULARARC` → radius direkte
4. **3D-sampling.** `ifcopenshell.geom.create_shape()` på selve `IfcAlignment`
   med `INCLUDE_CURVES=True`. Resampling til ønsket tetthet.
5. **IfcReferent.** Iterer referenter under alignment via `IfcRelNests`. Hent
   `Name` og station fra `ObjectPlacement.Distance`.

### Feilmoduser

| Feil | Respons |
|---|---|
| IFC < 4X3 | `ValueError("IFC4X3 kreves for senterlinje-IFC")` |
| Ingen `IfcAlignment` | `ValueError` med liste over tilgjengelige typer |
| Ingen Curve3D | Fall tilbake til Curve2D + Z=0, `vertical_pvi=[]`, warning |
| Ukjent segment-type | Warning, behandle som klotoid/linje |
| Referent uten linear placement | Hopp over enkeltreferent |
| `create_shape` feiler | Re-raise med alignment-navn-kontekst |

## Pipeline-integrasjon

### `centerline.load_centerline()` — ny `.ifc`-gren

```python
if suffix == ".ifc":
    from .alignment_parser import load_alignment_from_ifc
    return load_alignment_from_ifc(source).to_centerline()
```

### `pipeline.run_pipeline()` — `_load_alignment_metadata`

Ny intern helper som returnerer `AlignmentMetadata`-dataklasse uavhengig av
kilde:

```python
@dataclass
class AlignmentMetadata:
    vertical_pvi: list[tuple[float, float]]
    horizontal_segments: list[HorizontalSegment]
    station_labels: list[StationLabel]
    source_epsg: int
```

`.xml` → bygget fra eksisterende `load_vertical_profile()` + horisontal-extractor.
`.ifc` → fra `IfcAlignmentData`.

### Stasjons-alignment til IfcReferent

```python
if metadata.station_labels:
    s0 = metadata.station_labels[0].station % interval_m
    stations = arange(s0, total_length, interval_m)
else:
    stations = arange(0, total_length, interval_m)
```

Profilnummer blir dermed "rene" (P 100, P 110, …) når referenter finnes.
Hver `station_row` får ny nøkkel `referent_name` hvis stasjonen matcher en
`StationLabel` innen ±0.5 m.

### Nye output-filer

- `output/horizontal_alignment.json` — eksisterer, nå også produsert fra IFC-veien
- `output/station_labels.json` — nytt; tom liste for LandXML

## UI og API

### Webapp (`web/src/main.js`, `index.html`)

Dropzone 2 endres:

```
📐  Senterlinje (.xml LandXML, .ifc 4X3)
    referansesystem hentes automatisk

[etter valg] ✓ m_f-veg_12200_CL.ifc — 183 KB · IFC4X3 alignment
```

- `<input accept=".xml,.ifc">`
- Lokal badge "LandXML 1.2" eller "IFC4X3 alignment" basert på filending
- Variabelnavn: `xmlFile` → `clFile`
- **Schema-validering først på server.** Frontend kan ikke skille en vegmodell-IFC
  fra en alignment-IFC uten å parse den. Hvis brukeren ved uhell laster opp
  vegmodell-IFC her, returnerer `alignment_parser.load_alignment_from_ifc()`
  `ValueError("Ingen IfcAlignment funnet — er dette en vegmodell-IFC?")`,
  og jobben feiler med en klar feilmelding i status-API-et.

### API (`src/api/server.py`)

`POST /api/jobs`:

| Før | Etter |
|---|---|
| `xml_file: UploadFile` | `cl_file: UploadFile` |
| Validering: `.xml` | Validering: `.xml` eller `.ifc` |

Lagring: `uploads/<job_id>/centerline.xml` eller `centerline.ifc`.

**Nytt endepunkt:** `GET /api/jobs/{id}/station-labels` returnerer
`station_labels.json` (tom liste hvis ingen).

### Job runner (`src/api/job_runner.py`)

```python
if cl_path.suffix.lower() == ".ifc":
    publish_cmd = ["python", "-m", "src.arcpy_processor.ifc_cl_to_agol",
                   "--ifc-cl", str(cl_path), ...]
else:
    publish_cmd = ["python", "-m", "src.arcpy_processor.landxml_to_agol",
                   "--xml", str(cl_path), ...]
```

## AGOL-publisering

### Felles modul `_polyline_publisher.py`

```python
def publish_polyline_to_agol(
    points_dict: dict[str, list[tuple[float, float, float]]],
    *,
    source_epsg: int,
    service_name: str,
    folder: str,
    gis,
    lengdeprofil_path: Path | None = None,
    extra_fields: list[tuple[str, list]] | None = None,
) -> dict:
    """Felles publish-flyt: GDB → PolylineZ FC → reprojisér → vedlegg → AGOL."""
```

`landxml_to_agol.py` og `ifc_cl_to_agol.py` blir tynne CLI-er som parser inn,
deretter kaller felles publisher.

### Ekstra felter fra IFC-CL

- `alignment_name` (TEXT) — `IfcAlignment.Name`
- `n_horizontal_segments` (LONG)
- `n_vertical_segments` (LONG)
- `n_referents` (LONG)

Vises som popup-attributter i ArcGIS-kartet.

### CLI

```
python -m src.arcpy_processor.ifc_cl_to_agol \
    --ifc-cl samples/m_f-veg_12200_CL.ifc \
    --name "FV12200_Senterlinje" \
    --folder "" \
    --lengdeprofil output/lengdeprofil.svg
```

## Testing

### Unit (`tests/test_alignment_parser.py` — ny)
- `test_load_12200_alignment` — antall segmenter og total lengde
- `test_horizontal_segment_types` — LINE/CIRCULARARC/CLOTHOID-bryter
- `test_vertical_segment_signing` — radius-tegn for topp vs dal
- `test_referent_extraction` — IfcReferent → StationLabel
- `test_to_centerline_adapter` — gyldig `Centerline` ut
- `test_missing_alignment_raises` — `ValueError`
- `test_ifc4_schema_rejected` — klar feilmelding ved feil schema

### Pipeline (`tests/test_pipeline.py` — utvidelser)
- `test_run_pipeline_with_ifc_cl` — end-to-end med 12200
- `test_station_grid_aligns_to_referent` — grid starter ved første hele 100 m

### AGOL (`tests/test_ifc_cl_to_agol.py` — ny, mocket)
- `test_cli_parses_ifc_cl` — dry-run, populerer `points_dict`
- Felles `_polyline_publisher` testes mot begge grener

### Integrasjonstest (`pytest -m slow`)
- `test_12200_full_run` — full pipeline mot 12200-prøven

### Manuell verifisering
- Last opp 12200-paret via webappen, sjekk profilutforskeren
- Sjekk klotoide-overganger i lengdeprofil-rubrikken
- Sjekk AGOL-laget for nye attributter

## Bakoverkompatibilitet

- `xml_file`-feltnavnet i `POST /api/jobs` brytes til `cl_file`. Frontend
  oppdateres samtidig. Ingen kjente eksterne klienter.
- `landxml_to_agol.py` CLI uendret — fungerer fortsatt for
  `samples/FV229_Senterlinje.xml`.

## Estimat

| Steg | Tid |
|---|---|
| `alignment_parser.py` + tester | ~1 dag |
| Pipeline-integrasjon + tester | ~½ dag |
| AGOL-pipeline split + tester | ~½ dag |
| UI/API endring | ~½ dag |
| Manuell verifisering, polish | ~½ dag |
| **Sum** | **~3 dager** |

## Filer som touches

**Nye:**
- `src/ifc_processor/alignment_parser.py`
- `src/arcpy_processor/ifc_cl_to_agol.py`
- `src/arcpy_processor/_polyline_publisher.py`
- `tests/test_alignment_parser.py`
- `tests/test_ifc_cl_to_agol.py`

**Endret:**
- `src/ifc_processor/centerline.py`
- `src/ifc_processor/pipeline.py`
- `src/arcpy_processor/landxml_to_agol.py`
- `src/api/server.py`
- `src/api/job_runner.py`
- `web/src/main.js`
- `web/src/index.html`
- `tests/test_pipeline.py`
