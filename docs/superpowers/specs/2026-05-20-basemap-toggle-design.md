# Design: Bakgrunnskart-velger (basemap toggle)

**Dato:** 2026-05-20  
**Fil:** `web/profilutforsker.html`  
**Status:** Godkjent

---

## Mål

Gi brukeren mulighet til å bytte mellom fire bakgrunnskart. Mørkt bakgrunnskart skal aktiveres automatisk ved mørk modus og gå tilbake til forrige lyse kart når lys modus gjenopprettes.

---

## Bakgrunnskart

| id       | Navn        | Type          | URL                                                                                                          | Swatch   |
|----------|-------------|---------------|--------------------------------------------------------------------------------------------------------------|----------|
| `kanvas` | Kanvas      | VectorTile    | `https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheKanvas/VectorTileServer` | `#e8e4d8` |
| `graa`   | Gråtone     | VectorTile    | `https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheGraatoneTerreng/VectorTileServer` | `#c8c8c8` |
| `bilder` | Bilder      | Tile (MapServer) | `https://services.geodataonline.no/arcgis/rest/services/Geocache_UTM33_EUREF89/GeocacheBilder/MapServer` | `#2a3a2a` |
| `mork`   | Mørk        | VectorTile    | `https://vector.services.geodataonline.no/arcgis/rest/services/GeocacheVector/GeocacheKanvasMork/VectorTileServer` | `#1a2630` |

Bilder bruker `TileLayer` (ikke `VectorTileLayer`) fordi det er et MapServer-endpoint.

---

## Arkitektur

### State

```js
let activeBasemapId = 'kanvas';   // gjeldende kart
let lightBasemapId  = 'kanvas';   // siste lyse kart (brukes ved mørkt→lys-switch)
```

### `setBasemap(id)`

1. Slår opp i `BASEMAPS`-arrayen på `id`.
2. Oppretter riktig lag: `VectorTileLayer` for `vtl`, `TileLayer` for `tile`.
3. Setter `map.basemap = new Basemap({ baseLayers: [lag], title: label })`.
4. Oppdaterer `activeBasemapId = id`.
5. Hvis kartet er et lyst kart (`id !== 'mork'`), oppdateres `lightBasemapId = id`.
6. Oppdaterer UI: fjerner `.active`-klasse fra alle rader, legger til på valgt rad.

### `toggleTheme()` (utvidelse)

Eksisterende funksjon utvides med ett ekstra kall:
- Mørk modus aktivert → `setBasemap('mork')`
- Lys modus gjenopprettet → `setBasemap(lightBasemapId)`

Manuell kartbytte mens mørk modus er på er mulig (kartvelgeren viser alle 4 alternativene).

---

## HTML

Ny `.map-tool-group` legges til under eksisterende grupper i `#map-tools`:

```html
<div class="map-tool-group" style="position:relative">
  <button class="map-tool" id="btn-basemap" onclick="toggleBasemapPicker()" title="Bytt bakgrunnskart">
    <!-- layers SVG icon -->
  </button>
  <div id="basemap-picker" class="basemap-picker hidden">
    <!-- 4 rader generert av JS ved oppstart (buildBasemapPicker()) -->
  </div>
</div>
```

`#basemap-picker` er et barn av `.map-tool-group` (som har `position: relative`) og posisjoneres absolutt til venstre for gruppen.

### Popup-rad

Hver rad inneholder:
- Fargeswatch (16×16 px, `border-radius: 3px`)
- Kartnavn
- Hake (✓) hvis aktivt kart

---

## CSS

```css
.basemap-picker {
  position: absolute; top: 0; right: calc(100% + 8px);
  background: var(--card); border: 1px solid var(--line);
  border-radius: 6px; box-shadow: 0 4px 12px rgba(0,0,0,.1);
  padding: 4px; min-width: 140px; z-index: 10;
}
.basemap-picker.hidden { display: none; }
.basemap-option {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 8px; border-radius: 4px; cursor: pointer;
  font-size: 12px; color: var(--ink);
}
.basemap-option:hover { background: var(--paper); }
.basemap-option.active { font-weight: 600; }
.basemap-swatch {
  width: 16px; height: 16px; border-radius: 3px;
  border: 1px solid rgba(0,0,0,.15); flex-shrink: 0;
}
```

---

## Interaksjon

- Klikk på `#btn-basemap` åpner/lukker pickeren.
- Klikk på et alternativ: kaller `setBasemap(id)` og lukker pickeren.
- Klikk utenfor pickeren lukker den (`mousedown`-listener på `document`).
- `#btn-basemap` får `.active`-klasse mens pickeren er åpen.

---

## ArcGIS JS-import

`TileLayer` legges til i `$arcgis.import([…])`-listen (allerede importerer `VectorTileLayer` og `Basemap`).

---

## Ikke i scope

- Faktiske kartthumbnails (bruker fargeswatcher i stedet).
- Persistering av valgt kart mellom sessjoner.
- Basiskart-animasjon ved bytte.
