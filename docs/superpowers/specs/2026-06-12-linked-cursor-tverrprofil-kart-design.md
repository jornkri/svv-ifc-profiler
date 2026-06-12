# Linked cursor: tverrprofil → kart/3D — design

**Dato:** 2026-06-12
**Status:** Godkjent av bruker (muntlig i økt), klar for implementasjonsplan
**Omfang:** Kun frontend (`web/profilutforsker.html`). Ingen backend-endringer.

## Mål

Når brukeren beveger cursoren horisontalt i tverrprofil-tegningen (høyre skuff),
skal tilsvarende posisjon vises som en markør i 2D-kartet — og som et punkt på
kotehøyde i 3D-scenen. Markøren glir langs den magenta snittlinjen som allerede
tegnes i kartet for valgt stasjon.

## Oppførsel

- Markøren følger **nøyaktig samme posisjon som dagens hover-overlay** i
  tverrprofilet: snappet til nærmeste linje når cursoren er nær geometri,
  ellers rå cursorposisjon. (Konsistens: det brukeren ser i tegningen er det
  som vises i kartet.)
- Markøren vises i **både 2D-kartet og 3D-scenen** (den av dem som er aktiv —
  det er billig å oppdatere begge ubetinget så lenge lagene finnes).
- Markøren fjernes når cursoren forlater SVG-området (`pointerleave`), når
  tegningen lukkes, og ved jobbytte.
- Måle-modus påvirkes ikke; hover-flyten kjører som før.

## Matematikk

Hoveren gir allerede reelle koordinater i snittplanet via
`currentCoordMap.svgToReal(svgX, svgY)`:

- `x_m` — signert offset fra senterlinja (negativ = venstre)
- `z_m` — kotehøyde (moh.)

Kartpunktet (EPSG:25833) beregnes som:

```
(x, y) = (x0 + px · x_m, y0 + py · x_m)
```

der `(x0, y0)` er stasjonspunktet (`stations[idx].x/y`) og `(px, py)` er
enhetsnormalen på senterlinja — samme matte som `drawCrossSectionLine()` og
`clTangent(idx)` (perp = `(-ty, tx)`).

3D-punktet er `(x, y, z_m)` med `elevationInfo: absolute-height`.

## Komponenter og endringer

Alle endringer i `web/profilutforsker.html`:

1. **Tilstand `csMapAxis`** — `{x0, y0, px, py}` settes i `selectStation(idx)`
   (gjenbruker `clTangent(idx)`), nulles ved jobbytte og når tegningen lukkes.
2. **2D-markør** — én gjenbrukbar `Graphic` i eksisterende `hoverLayer`
   (`listMode: hide`, ligger øverst): liten magenta sirkel (samme MAGENTA som
   snittlinjen) med hvit ring, `simple-marker`, ~9 px.
3. **3D-markør** — én gjenbrukbar `Graphic` i eksisterende `selected3dLayer`
   (har allerede `absolute-height`): magenta kule (`point-3d`, object-symbol,
   ~1 m diameter). Oppdateres kun hvis `view3d`/laget er initialisert
   (3D er lazy-init).
4. **Hook i hover-flyten** — `renderHoverOverlay(snap, coordMap)` beregner
   kartpunktet fra `x_m`/`z_m` og kaller `updateCsMapMarker(x_m, z_m)`;
   `clearHoverOverlay()` kaller `hideCsMapMarker()`.
5. **rAF-throttling** — geometri-oppdateringene buffres gjennom
   `requestAnimationFrame` slik at raske `pointermove`-events ikke gir mer enn
   én ArcGIS-oppdatering per frame.

## Feilhåndtering / kanttilfeller

- `csMapAxis === null` (ingen stasjon valgt / jobbytte underveis) → hooken gjør
  ingenting.
- `view3d` ikke bygget ennå → hopp over 3D-markøren stille.
- Stasjon med kun én nabo (første/siste) håndteres allerede av `clTangent`.
- Markør-grafikkene gjenbrukes (geometri muteres via `graphic.geometry = …`),
  aldri add/remove per move — unngår søppel i lagene.

## Testing

- Manuell verifisering i kjørende app (agent-browser): hover langs terreng og
  vegkant i tverrprofilet → markør glir langs snittlinjen i 2D; bytt til 3D →
  kule følger på kotehøyde; forlat SVG → markør borte; bytt stasjon → markør
  følger ny snittlinje; jobbytte → ingen etterlatt markør, ingen konsollfeil.
- Ingen automatiske tester (ren visuell frontend-interaksjon, mønster fra
  tidligere frontend-features i prosjektet).
