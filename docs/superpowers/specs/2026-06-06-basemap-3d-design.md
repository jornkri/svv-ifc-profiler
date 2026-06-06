# Bakgrunnskart-velger virker også i 3D

**Dato:** 2026-06-06
**Status:** Godkjent av bruker

## Problem

Bakgrunnskart-velgeren (5 valg: Trafikk, Kanvas, Gråtone, Bilder, Mørk) styrer kun
2D-kartet. 3D-scenen får et hardkodet flyfoto (`SCENE_BASEMAP_URL` = GeocacheBilder)
ved init og påvirkes aldri av velgeren — selv om knappen er synlig og klikkbar i
3D-modus.

## Løsning

Felles bakgrunnskart-valg for 2D og 3D, med ett unntak: første gang brukeren åpner
3D settes Bilder som felles valg, slik at dagens flyfoto-utseende i 3D beholdes til
man aktivt velger noe annet.

### Endringer (alle i `web/profilutforsker.html`)

1. **`makeBasemap(cfg, for3d = false)`** — nytt flagg for 3D-bruk:
   - Hopper over Kartverket-topo-ekstralaget (auto-topo er bundet til 2D-`view.scale`;
     i 3D varierer skala med tilt og ville flimre).
   - Rører ikke `trafikkBaseLayer`/`kvTopoLayer`-globalene (skal fortsatt peke på
     2D-lagene).

2. **`setBasemap(id)`** — setter i tillegg `map3d.basemap = makeBasemap(cfg, true)`
   når 3D-scenen er bygget. Egen `Basemap`-instans per kart (samme instans kan ikke
   leve i to kart). Mørk modus følger automatisk med i 3D siden `toggleTheme()` går
   via `setBasemap`.

3. **Første 3D-åpning** (`setViewMode`) — engangs-flagg: kaller `setBasemap('bilder')`
   før `initScene()`, så scenen bygges med riktig valg. Unntak: i mørk modus beholdes
   Mørk aktiv, kun `lightBasemapId` settes til `'bilder'`.

4. **`initScene()`** — hardkodet flyfoto erstattes med
   `makeBasemap(<aktivt valg>, true)`. `SCENE_BASEMAP_URL`-konstanten fjernes
   (samme URL som Bilder-oppslaget i `BASEMAPS`).

## Antagelser / risiko

Vektortile-bakgrunnene (Kanvas, Gråtone, Mørk) ligger i EPSG:25833 — samme SR som
scenen (`viewingMode: 'local'`, wkid 25833). `VectorTileLayer` støttes i lokal
SceneView når SR matcher. Verifiseres live i appen.

## Testing (manuelt i appen)

- Bytt bakgrunn i 2D → veksle til 3D: samme bakgrunn vises (etter første åpning).
- Bytt bakgrunn mens man står i 3D: både 2D og 3D oppdateres.
- Første 3D-åpning: Bilder settes som felles valg.
- Mørk modus-veksling mens 3D er aktiv: scenen bytter til/fra Mørk.
- Trafikk i 2D ved dyp zoom: Kartverket-topo-veksling fungerer fortsatt (uendret).
