# LandXML senterlinje til ArcGIS Online — designspesifikasjon

**Dato:** 2026-05-04
**Scope:** Les LandXML PlanFeature-polylinjer og publiser som hostet 3D PolylineZ feature service i ArcGIS Online via ArcPy

---

## Mål

Et standalone Python-script som tar en LandXML-fil som input, leser én eller flere navngitte `PlanFeature`-polylinjer, oppretter en georeferert `PolylineZ`-feature class med ArcPy, reprosjekterer ved behov til EPSG:25833, og publiserer til brukerens ArcGIS Online-konto som en hostet feature service.

Scriptet kjøres som subprocess fra FastAPI-backenden og returnerer JSON med metadata om publiseringen — identisk mønster som `bim_to_agol.py`.

---

## Arkitektur

To nye filer i `src/arcpy_processor/`:

```
src/arcpy_processor/
  landxml_parser.py     ← ren Python, ingen ArcPy-avhengighet
  landxml_to_agol.py    ← CLI-orkestrator

tests/
  test_landxml_parser.py
  test_landxml_to_agol.py
```

`errors.py` utvides med to nye feilkoder. Alle andre eksisterende filer (`auth.py`, `publisher.py`, `converter.py`) er uberørt.

---

## Komponenter

### `landxml_parser.py`

**Funksjon:** `parse_landxml(path, features=None, source_epsg=None) -> tuple[dict[str, list[tuple[float,float,float]]], int]`

- Åpner LandXML-fil (støtter med og uten namespace, iso-8859-1 og utf-8)
- Leser `<CoordinateSystem epsgCode="...">` for å bestemme kilde-EPSG
- Hvis `epsgCode` mangler i fil og `source_epsg` er `None`: raise `ArcpyProcessorError(LANDXML_PARSE_ERROR, ...)`
- Leser alle `PlanFeature/CoordGeom/Line`-elementer
- Koordinater i LandXML er (Northing, Easting, Z) — konverteres til (Easting, Northing, Z) = (X, Y, Z)
- Hvis `features` er oppgitt (liste med navn): behold kun PlanFeatures med matchende navn
- Hvis `features` er `None`: behold alle
- Kjeder `Line`-segmenter per PlanFeature til én sammenhengende polyline (dedupliserer konsekutive like punkter)
- Returnerer `({"L530": [(E,N,Z), ...]}, 5111)` — dict med navn→punktliste + kilde-EPSG som int

**Feilhåndtering:**
- Ugyldig XML → `ArcpyProcessorError(LANDXML_PARSE_ERROR)`
- Ingen Line-elementer funnet → `ArcpyProcessorError(LANDXML_PARSE_ERROR)`
- Ingen av de angitte `--features`-navnene finnes → `ArcpyProcessorError(LANDXML_PARSE_ERROR)` med liste over tilgjengelige navn

### `landxml_to_agol.py`

CLI med `argparse`:

```
--xml         Sti til .xml LandXML-fil (påkrevd)
--name        Tjenestenavn i ArcGIS Online (påkrevd)
--folder      Folder i ArcGIS Online (påkrevd)
--features    Kommaseparerte PlanFeature-navn (valgfri — default: alle)
--source-epsg Overstyr kilde-EPSG som heltall (valgfri)
```

**Arbeidsflyt:**

```
LandXML-fil
  │
  ▼
[1] load_dotenv() + logging
  │
  ▼
[2] Valider at --xml finnes → LANDXML_NOT_FOUND
  │
  ▼
[3] _check_arcpy() → ARCPY_UNAVAILABLE
  │
  ▼
[4] connect() til AGOL → AUTH_FAILED
  │
  ▼
[5] check_name_available() → NAME_EXISTS
  │
  ▼
[6] parse_landxml() → {name: [(E,N,Z),...]} + kilde-EPSG → LANDXML_PARSE_ERROR
  │
  ▼
[7] create_polyline_fc() → PolylineZ FC i scratchGDB (én rad per PlanFeature)
    → BIM_CONVERSION_FAILED (gjenbruk feilkode for konverteringsfeil)
  │
  ▼
[8] Reproject til EPSG:25833 hvis kilde-EPSG ≠ 25833
    → PUBLISH_FAILED ved feil
  │
  ▼
[9] upload_and_publish() → hostet feature service
  │
  ▼
[10] Print JSON til stdout, sys.exit(0)
```

**Hjelpefunksjoner:**
- `_check_arcpy()`: duplisert fra `bim_to_agol.py` (private funksjon, ikke eksportert — duplisering er bevisst for at modulene skal være uavhengige)
- `create_polyline_fc(points_dict, gdb_path, dataset_name) -> str`: oppretter scratchGDB, feature class med felt `name` (TEXT 100), `feat_length` (DOUBLE), og PolylineZ-geometri. Returnerer FC-sti.

---

## Feature class-struktur

```
PolylineZ feature class: <dataset_name>_centerline
  Felt:
    OBJECTID   (auto)
    SHAPE      (PolylineZ, EPSG:25833)
    name       TEXT 100   ← PlanFeature name-attributt
    feat_length DOUBLE    ← beregnet lengde (meter)
```

---

## Feilkoder (tillegg til `errors.py`)

```python
LANDXML_NOT_FOUND  = "LANDXML_NOT_FOUND"
LANDXML_PARSE_ERROR = "LANDXML_PARSE_ERROR"
```

Totalt 9 feilkoder etter utvidelse.

---

## Output

Ved suksess (stdout):
```json
{
  "status": "ok",
  "url": "https://services.arcgis.com/.../FeatureServer",
  "item_id": "abc123",
  "item_url": "https://www.arcgis.com/home/item.html?id=abc123",
  "layer_count": 1,
  "feature_count": 1,
  "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
  "source_epsg": 5111,
  "published_at": "2026-05-04T10:30:00Z"
}
```

`feature_count` er antall PlanFeature-rader publisert.

Ved feil (stderr) — samme format som `bim_to_agol.py`.

---

## Teststrategier

### `test_landxml_parser.py`
Ren Python, ingen mocks. Tester mot `samples/FV229_Senterlinje.xml`:
- Korrekt EPSG-lesing (5111 fra eksempelfilen)
- N/E-swap: første punkt skal ha E som X-koordinat
- `--features`-filtrering: kun L530 returneres
- Feil ved manglende epsgCode uten source_epsg
- Feil ved ukjent feature-navn

### `test_landxml_to_agol.py`
Mocker arcpy + arcgis (samme mønster som `test_arcpy_cli.py`):
- Suksess: JSON på stdout med exit code 0
- Feil: JSON på stderr med exit code 1
- LANDXML_NOT_FOUND ved manglende fil
- LANDXML_PARSE_ERROR videresendes korrekt

---

## Koordinathåndtering

LandXML-koordinater er (Northing, Easting, Z). Parseren bytter til (Easting, Northing, Z) = (X, Y, Z) slik at ArcPy behandler dem korrekt som geografiske koordinater i kilde-CRS.

Reprojeksjon:
```python
if source_epsg != 25833:
    out_fc = fc_path + "_projected"
    arcpy.management.Project(fc_path, out_fc, arcpy.SpatialReference(25833))
    arcpy.management.Delete(fc_path)
    fc_path = out_fc
```

Hvis kilde-EPSG allerede er 25833: ingen reprojeksjon, ingen kopi.

---

## Utenfor scope

- Curve/Spiral-elementer i CoordGeom (kun Line-elementer støttes)
- Alignment-elementer (kun PlanFeature)
- Oppdatering av eksisterende tjenester
- Batch-prosessering av flere LandXML-filer
