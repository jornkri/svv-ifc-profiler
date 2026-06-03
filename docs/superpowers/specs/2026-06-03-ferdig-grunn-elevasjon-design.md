# Ferdig-grunn-elevasjon for Profilutforsker 3D («cut & fill»)

**Dato:** 2026-06-03
**Status:** Design godkjent — klar for implementeringsplan
**Tilnærming:** A — ren-Python ferdig-grunn-DEM + klient-side `BaseElevationLayer` (ingen AGOL-publisering)

## Problem

I 3D-scenen i Profilutforsker bruker `Ground` i dag `GeocacheTerreng`
(Esri ImageServer) som elevasjonskilde — dette er **eksisterende/naturlig
terreng**. Vegmodellen (i3s SceneLayer) ligger på sin **prosjekterte kote**.
Resultatet:

- I **skjæring** stikker det naturlige terrenget opp *gjennom* vegen.
- På **fylling** *svever* vegen over det naturlige terrenget.

Den gamle løsningen var ArcPy `Multipatch To Raster` + mosaikk + publisert
elevasjonstjeneste. Vi erstatter dette med en ren-Python-rutine.

## Mål og prinsipp

Lag en **ferdig-grunn-flate** = bearbeidet terreng der korridoren er skåret/fylt
til vegens prosjekterte flate, og glir mykt over i naturlig terreng utenfor.
Flaten legges som et **ekstra elevasjonslag oppå `GeocacheTerreng`** i scenen, så
bare korridoren endres; resten av scenen er urørt.

**Nøkkelinnsikt:** IFC-en inneholder allerede `skjaering`/`fylling`/`groft`-flatene
som binder vegen til dagline. Tar vi **øverste z per celle** over alle veg-TIN-er
(unntatt eksisterende terreng-TIN), får vi cut *og* fill «gratis» — toppen av
skjæringsskråningen og fyllingsskråningen ER den graderte grunnen.

Ingenting publiseres til AGOL. Elevasjonen lever som en jobb-fil i backend og
konsumeres av en custom `BaseElevationLayer` i klienten.

## Komponenter

### a) `src/ifc_processor/finished_ground.py` (ny — ren Python, ingen ArcPy)

Input:
- TIN-er fra eksisterende `read_ifc_tins()` (trekanter `(N,3,3)` + `road_class`).
- `source_epsg` (fra alignment-metadata; default 25833).
- Korridor-bbox utledet fra senterlinjens punkter + en margin (dekker
  skråningenes uttrekk til dagline).

Steg:

1. **Mesh-z-buffer (erstatning for Multipatch To Raster):**
   - Definer et regulært rutenett over korridor-bbox, cellestørrelse `cell_m`
     (default **0,5 m**; konfigurerbar).
   - For hver trekant i veg-TIN-ene (ekskluder `road_class == "terreng"`):
     projiser til xy-planet, finn dekkede celler, interpoler z barysentrisk i
     hver celle, og skriv z **kun hvis høyere** enn nåværende celleverdi
     (z-buffer → topp-flate). Buried lag (planum/bærelag) tapes automatisk under
     slitelaget.
2. **Naturlig terreng:** sample DTM over rutenettet via `terrain_sampler`
   (Kartverket Høydedata, EPSG:25833). `terrain_sampler.py` utvides med en
   rutenett-/punktbatch-funksjon (≤50 punkter per kall, chunkes).
3. **Mosaikk + feather:** celler med veg-dekning = modell-z; celler uten = terreng-z.
   I en kantsone på `feather_cells` (default 2–3 celler) rundt korridor-dekningen
   vektes modell↔terreng lineært, så det ikke blir en vertikal klippe der modellen
   ikke når dagline.
4. **Output:**
   - `terrain_dem.bin` — Float32, row-major (nord→sør, vest→øst), NoData-verdi
     for celler uten data (utenfor korridor etter feather).
   - `terrain_dem.json` — header: `{ wkid: 25833, xmin, ymin, xmax, ymax,
     cell_m, ncols, nrows, nodata }`.

### b) Pipeline-wiring

Kalles fra `src/ifc_processor/pipeline.py` (har allerede TIN-er, senterlinje og
`terrain_sampler` tilgjengelig). Skriver til
`uploads/<job>/output/terrain_dem.{bin,json}`. Best-effort: feiler generering,
logges og hoppes over (ingen DEM → ingen regresjon i scenen).

### c) API (`src/api/server.py`)

- Nytt endpoint som serverer DEM-filene for en jobb, analogt med dagens
  `/api/jobs/{job_id}/svg/{filename}`:
  - `GET /api/jobs/{job_id}/terrain-dem` → `terrain_dem.json`
  - `GET /api/jobs/{job_id}/terrain-dem.bin` → `terrain_dem.bin`
    (`application/octet-stream`)
- Nytt felt `terrain_dem_url` i `JobState` + begge persist-dicts (`job_runner.py`)
  + begge API-responser (`get_job`, `list_jobs`). `null` når DEM mangler.

### d) Frontend (`web/profilutforsker.html`)

- **Custom `BaseElevationLayer`-subklasse** (`CorridorElevationLayer`):
  - `load()`: hent `terrain_dem.json` + `.bin` én gang; bygg en `TileInfo` med
    **det vedlagte cache-skjemaet** (se under) og sett `this.tileInfo`,
    `this.spatialReference = {wkid:25833}`, `this.fullExtent` = korridor-bbox.
  - `fetchTile(level, row, col)`: regn ut tile-ekstenten fra `tileInfo`, bilineær-
    sample korridor-DEM-en på (tileSize+1)² post-punkter, returner
    `{ values, width, height, noDataValue }`. Post-punkter utenfor korridoren får
    `noDataValue` → `GeocacheTerreng` vises gjennom.
- **Komposittrekkefølge:** `ground.layers = [GeocacheTerreng, korridorElevasjon]`
  (korridor sist → vinner der den har gyldige data; NoData faller gjennom).
- Feiler DEM-fetch → hopp over korridorlaget, behold `GeocacheTerreng` (ingen
  regresjon).

## Tiling-skjema (må matches)

Fra `Config_tile_scheme_Geocache_ETRS89_UTM33.xml` (terreng-/bakgrunns-cachen):

- **SpatialReference:** EPSG:25833 (ETRS89 / UTM33N).
- **TileOrigin:** `X = -2500000`, `Y = 9045984`.
- **Tile-størrelse:** 256 × 256, **DPI:** 96, **BandCount:** 1, **LERCError:** 0.
- **18 LOD-er (0–17):**

  | Level | Resolution (m/px) | Scale     |
  |-------|-------------------|-----------|
  | 0     | 21674.710016      | 81920000  |
  | 1     | 10837.355008      | 40960000  |
  | 2     | 5418.677504       | 20480000  |
  | 3     | 2709.338752       | 10240000  |
  | 4     | 1354.669376       | 5120000   |
  | 5     | 677.334688        | 2560000   |
  | 6     | 338.667344        | 1280000   |
  | 7     | 169.333672        | 640000    |
  | 8     | 84.666836         | 320000    |
  | 9     | 42.333418         | 160000    |
  | 10    | 21.166709         | 80000     |
  | 11    | 10.5833545        | 40000     |
  | 12    | 5.29167725        | 20000     |
  | 13    | 2.645838625       | 10000     |
  | 14    | 1.3229193125      | 5000      |
  | 15    | 0.66145965625     | 2500      |
  | 16    | 0.33072982813     | 1250      |
  | 17    | 0.16536491406     | 625       |

Klientens `TileInfo` bygges med nøyaktig denne `origin`, `size=[256,256]`,
`dpi=96` og LOD-listen (`level`, `resolution`, `scale`). Da ber scenen om de
samme tile-rutene som `GeocacheTerreng`, og korridoren komposit­terer pikselnøyaktig.

> Merk: skjemaet er også det vi ville brukt hvis vi senere publiserer en ekte
> LERC-elevasjonstjeneste (tilnærming B). Det er bevisst utenfor scope nå.

## Dataflyt

```
IFC → read_ifc_tins → finished_ground.build_dem()
    → terrain_dem.{bin,json}  (uploads/<job>/output/)
    → backend-endpoint (/api/jobs/{id}/terrain-dem[.bin])
    → JS CorridorElevationLayer (BaseElevationLayer, matchende tileInfo)
    → scenens Ground (oppå GeocacheTerreng)
    → vegmodellen hviler riktig (skjæring stikker ikke opp, fylling svever ikke)
```

## Feilhåndtering / degradering

- **Kartverket utilgjengelig / utenfor Norge:** DEM får kun korridor-data,
  terreng-celler = NoData → faller tilbake til `GeocacheTerreng` (som i dag).
- **Ingen veg-TIN-er / tom geometri:** ingen DEM skrives, `terrain_dem_url=null`,
  scenen oppfører seg som i dag.
- **Frontend DEM-fetch feiler:** korridorlaget hoppes over, `GeocacheTerreng`
  beholdes.
- All generering er best-effort i pipelinen og blokkerer ikke øvrig jobb-output.

## Testing

- **Enhetstester `finished_ground`:**
  - Z-buffer: kjent trekant → forventede celle-z; topp-vinner ved overlapp.
  - Mosaikk/feather: kant glir mykt fra modell til terreng (ingen vertikalt sprang).
  - NoData settes utenfor korridor.
  - Header-geometri: `xmin/ymin/cell_m/ncols/nrows` konsistent med rutenettet.
- **API-test:** nytt endpoint gir 200 + riktig content-type; 404 når DEM mangler.
- **Manuell 3D-verifisering** i scenen: skjæring stikker ikke opp, fylling svever
  ikke; korridoren aligner med GeocacheTerreng i kantene.

## Antakelser å bekrefte under planlegging

1. IFC-ens `fylling`/`skjaering`-flater når dagline. Hvis ikke, bærer feather-sonen
   overgangen (håndtert defensivt uansett).
2. Samme jobb produserer både scene-laget (AGOL) og DEM-en (backend). Hvis
   BIM-publisering (`bim_to_agol`) og IFC-prosessering (`pipeline.py`) er ulike
   jobber, knyttes DEM-en til den jobben scenen faktisk lastes fra.
3. `read_ifc_tins`-koordinatene er i `source_epsg`; ved `source_epsg != 25833`
   transformeres rutenettet til 25833 (samme mønster som `terrain_sampler`).

## Bevisst utenfor scope (YAGNI)

- AGOL-publisering av elevasjonstjeneste (tilnærming B).
- COG/geotiff.js-servering (vi bruker kompakt binær heightfield).
- Korridorflate fra tverrprofil-/korridorgeometri (vi bruker BIM-multipatchen).
