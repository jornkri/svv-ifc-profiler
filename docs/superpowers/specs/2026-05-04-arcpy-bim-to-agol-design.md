# ArcPy BIM-til-ArcGIS-Online — designspesifikasjon

**Dato:** 2026-05-04
**Scope:** Konvertering av IFC-filer til 3D Object Layer i ArcGIS Online via ArcPy

---

## Mål

Et standalone Python-script som tar en IFC-fil som input, konverterer den til en georeferert 3D Object Layer og publiserer den til brukerens ArcGIS Online-konto. Scriptet er designet for å kjøres som subprocess fra FastAPI-backenden (samme Windows-maskin) og returnerer JSON med metadata om publiseringen.

---

## Arkitektur

Ny modul `src/arcpy_processor/` — helt adskilt fra `ifc_processor` for å isolere ArcPy-avhengigheten (Windows + ArcGIS Pro-lisens).

```
src/arcpy_processor/
  __init__.py
  bim_to_agol.py     ← CLI-inngangspunkt og arbeidsflyt-orkestrator
  auth.py            ← leser .env, autentiserer mot ArcGIS Online
  publish.py         ← publiserer feature dataset til AGOL som 3D Object Layer
```

---

## Arbeidsflyt

```
IFC-fil
  │
  ▼
[1] Autentiser mot ArcGIS Online (OAuth2 / credentials fra .env)
  │
  ▼
[2] Sjekk at tjenestenavn ikke finnes i AGOL → feile tydelig hvis det gjør
  │
  ▼
[3] BIMFileToGeodatabase → memory\ workspace (ingen lokal lagring)
  │
  ▼
[4] Slett tomme multipatcher (SelectLayerByAttribute + DeleteRows)
  │
  ▼
[5] Reproject til WKID 25833 (ETRS89 / UTM sone 33N)
  │
  ▼
[6] Publiser som 3D Object Layer til ArcGIS Online
  │
  ▼
[7] Print JSON til stdout → FastAPI parser resultatet
```

---

## Komponenter

### `auth.py`
- Leser `AGOL_CLIENT_ID`, `AGOL_CLIENT_SECRET` (eller `AGOL_USERNAME` / `AGOL_PASSWORD`) fra `.env`
- Returnerer en autentisert `arcgis.GIS`-instans
- Bruker `arcgis` Python-pakken (allerede i `requirements.txt`)

### `bim_to_agol.py`
CLI med `argparse`:
```
--ifc       Sti til .ifc-fil (påkrevd)
--name      Navn på tjenesten i ArcGIS Online (påkrevd)
--folder    Folder i ArcGIS Online (påkrevd)
```

Arbeidsflyt-steg:
1. **Valider navn**: sjekk AGOL for eksisterende item med samme navn → `SystemExit(1)` med tydelig melding
2. **BIMFileToGeodatabase**: `arcpy.conversion.BIMFileToGeodatabase(ifc_path, "memory", dataset_name)`
3. **Slett tomme**: iterer over feature classes i datasett, slett de med 0 features
4. **Reproject**: `arcpy.management.Project()` til spatial reference WKID 25833
5. **Publiser**: kall `publish.py`

### `publish.py`
- Bruker `arcgis.features.FeatureLayerCollection` eller sharing API for å publisere multipatch som 3D Object Scene Layer
- Tilknyttet feature layer opprettes automatisk av ArcGIS Online ved publisering
- Returnerer `dict` med publiseringsresultat

---

## Output

Ved suksess printer scriptet JSON til stdout:
```json
{
  "status": "ok",
  "url": "https://services.arcgis.com/.../FeatureServer",
  "item_id": "abc123...",
  "item_url": "https://www.arcgis.com/home/item.html?id=abc123",
  "feature_count": 142,
  "spatial_reference": "ETRS89 / UTM zone 33N (EPSG:25833)",
  "published_at": "2026-05-04T10:30:00Z"
}
```

Ved feil printer scriptet JSON til stderr og avslutter med exit code 1:
```json
{
  "status": "error",
  "code": "NAME_EXISTS",
  "message": "En tjeneste med navn 'Vei_Kleverud' finnes allerede i folder 'SVV-prosjekter'. Velg et annet navn."
}
```

---

## Feilhåndtering

| Situasjon | Håndtering |
|---|---|
| Tjenestenavn finnes allerede | Exit 1, `NAME_EXISTS` |
| IFC-fil ikke funnet | Exit 1, `IFC_NOT_FOUND` |
| ArcPy ikke tilgjengelig | Exit 1, `ARCPY_UNAVAILABLE` |
| Autentisering feiler | Exit 1, `AUTH_FAILED` |
| BIMFileToGeodatabase feiler | Exit 1, `BIM_CONVERSION_FAILED` |
| Ingen features igjen etter sletting | Exit 1, `NO_FEATURES` |
| Publisering feiler | Exit 1, `PUBLISH_FAILED` |

---

## In-memory strategi

All mellomlagring bruker ArcPy sin `memory\`-workspace. Ingen `.gdb`-filer skrives til disk. Dette betyr:
- Raskere prosessering
- Ingen opprydding nødvendig
- Begrensning: `memory\` tømmes når Python-prosessen avsluttes

---

## FastAPI-integrasjon (fremtidig)

FastAPI spawner scriptet som subprocess:
```python
result = subprocess.run(
    ["python", "-m", "src.arcpy_processor.bim_to_agol",
     "--ifc", ifc_path, "--name", name, "--folder", folder],
    capture_output=True, text=True
)
if result.returncode == 0:
    metadata = json.loads(result.stdout)
else:
    error = json.loads(result.stderr)
```

---

## Konfigurasjon (.env)

```
AGOL_CLIENT_ID=...
AGOL_CLIENT_SECRET=...
# eller:
AGOL_USERNAME=...
AGOL_PASSWORD=...
AGOL_ORG_URL=https://www.arcgis.com
```

---

## Utenfor scope (denne iterasjonen)

- 2D-tverrprofil-SVGer publiseres ikke her (håndteres av `ifc_processor`)
- Oppdatering av eksisterende tjenester
- Batch-prosessering av flere IFC-filer
- Frontend-integrasjon utover subprocess-kallet
