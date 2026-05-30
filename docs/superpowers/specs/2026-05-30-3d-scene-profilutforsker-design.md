# 3D-scene i Profilutforsker — Design

**Dato:** 2026-05-30
**Status:** Godkjent design, klar for implementasjonsplan
**Fil som endres:** `web/profilutforsker.html` (enkeltfil, ingen backend-endringer)

## Mål

Vise den publiserte 3D-vegmodellen (3D Object Scene Layer) i profilutforsker-appen,
med ArcGIS JS SDK, slik at brukeren kan veksle mellom dagens 2D-kart og en 3D-scene
av vegen — naturlig integrert og brukervennlig.

## Kontekst (eksisterende tilstand)

- `web/profilutforsker.html` er en enkeltfil-app på **ArcGIS JS 5.0** med en **2D `MapView`**.
- Den laster fra AGOL per jobb: senterlinje (`centerline_url`), stasjonspunkter
  (`sections_url`) og 2D BIM-planlag (`bim_plan_url`) som `FeatureLayer`-objekter.
- OAuth-token hentes fra backend (`/auth/token`) og registreres via
  `IdentityManager.registerToken` for hele AGOL-org-en.
- Backend `/api/jobs` returnerer allerede **`bim_scene_url`** (SceneServer for 3D Object
  Scene Layer), `bim_url` (3D-feature-layer / multipatch) og `bim_plan_url` per jobb.
- Data finnes altså allerede; dette er rent frontend-arbeid.

## Beslutninger (fra brainstorming)

1. **Integrasjon:** 2D/3D-veksler i samme kartflate (ArcGIS-standard).
2. **Synk:** Full synk — valgt stasjon, navigering, søk og lengdeprofil styrer også
   3D-kameraet; klikk i 3D åpner tverrprofil; valgt stasjon beholdes ved veksling.
3. **3D-innhold:** Terreng (ImageServer som ground) + bakgrunnsbilder, senterlinje +
   stasjonspunkter drapert, og vegmodell med farger fra SceneServer.

## Arkitektur

Alt i `web/profilutforsker.html`. Ny **`SceneView`** ved siden av dagens `MapView` —
to separate views med hvert sitt `Map`, stablet i samme `#map-container`:

```
#map-container
 ├─ #map-2d   (MapView)    ← dagens, uendret
 └─ #map-3d   (SceneView)  ← ny, skjult til man trykker 3D
```

To views (fremfor å bytte `container` på ett kart) fordi SceneView trenger eget
`ground`/elevasjon og scene-laget, mens 2D bruker flate FeatureLayers. To views som
lever side om side og synkes via felles tilstand er enklere/raskere å veksle.

## Komponenter

### Scene-oppsett (`Map` for SceneView)

Bygges programmatisk i kode (ingen lagret WebScene-item på AGOL):

- **Ground / høyde:** `ElevationLayer` fra
  `https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheTerreng/ImageServer`.
- **Bakgrunn:** `TileLayer` fra
  `https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer`.
- **Vegmodell:** `SceneLayer` fra jobbens `bim_scene_url`, vist med SceneServer-farger.
  - **Fallback:** mangler `bim_scene_url` → last `bim_url`/`bim_3d` som `FeatureLayer`
    (multipatch) i scenen. Mangler begge → pen «ingen 3D-modell»-melding; 2D upåvirket.
- **Senterlinje + stasjonspunkter:** samme to FeatureLayers som i 2D, lagt i scenen med
  `elevationInfo: { mode: "on-the-ground" }`. Egen `GraphicsLayer` for valgt/hover i 3D.

Gjenbruker eksisterende URL-er fra `loadJob`; ingen nye API-kall.

### Veksler + lazy init

- Segmentert `[2D][3D]`-knapp i topbaren (stil som dagens `top-btn`).
- `setViewMode('2d'|'3d')` viser riktig container; scenen lazy-initialiseres første gang
  3D velges (ingen kostnad før den trengs).

### Synk-logikk (felles tilstand `currentIdx` / `stations`)

- `selectStation(idx)` utvides: gjør som nå **pluss** — er 3D aktivt, flyr SceneView-
  kameraet til valgt tverrprofil (skrå vinkel, tilt ~65°, ser langs senterlinja) og
  markerer punktet i 3D-graphics-laget. Er 3D ikke aktivt, lagres valget til veksling.
- Piltaster, stasjonssøk og lengdeprofil treffer allerede `selectStation` → virker i 3D.
- **Klikk i 3D:** `hitTest` på stasjonspunkter → `selectStation(idx)` → åpner tverrprofil.
- **Veksling beholder kontekst:** synk kamera til omtrent samme senter/utsnitt via
  `view.viewpoint` begge veier. Valgt stasjon beholdes.
- Drawers (tverrprofil/lengdeprofil) ligger oppå `#map-area` og virker uendret over begge.

## Feilhåndtering

- Scene-lasting er best-effort og ikke-blokkerende (som dagens BIM-lag): feiler
  `bim_scene_url`, prøv fallback, ellers meldingsboks — 2D påvirkes aldri.
- Token/auth gjenbrukes; `registerToken` dekker også SceneServer.

## Testing / verifisering

Ingen frontend-testrigg finnes i prosjektet. Verifiseres manuelt ved å kjøre appen:
kjør backend + `vite`, velg et prosjekt med publisert 3D-lag, veksle 2D/3D, klikk
stasjon, naviger med piltaster, og bekreft at kameraet følger valgt profil. Bekreft også
fallback (jobb uten `bim_scene_url`) og at 2D fungerer uendret.

## Utenfor scope (YAGNI)

- Ny R700-fargelegging av scene-laget i klienten (bruker SceneServer-farger som de er).
- Lagring av scenen som WebScene-item på AGOL.
- Nye automattester / testrigg for frontend.
- Backend-endringer.
