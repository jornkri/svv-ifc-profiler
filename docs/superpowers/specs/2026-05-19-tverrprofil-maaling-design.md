# Måleverktøy i tverrprofil-viewer

**Dato:** 2026-05-19  
**Status:** Godkjent

## Sammendrag

Legger til to interaktive målefunksjoner i tverrprofil-draweren i `profilutforsker.html`:

1. **Hover-avlesning** — viser x fra CL, z m.o.h. og % fall live mens brukeren beveger musa over tegningen
2. **Punkt-til-punkt måling** — klikk to punkter og få horisontal avstand, høydeforskjell, % fall og skrå avstand

Begge bruker ekte snap til SVG-geometri og målingen følger med når brukeren navigerer mellom stasjoner.

---

## Valgt tilnærming: Inline SVG

SVG-teksten hentes allerede i `loadSvg()` for x-tick-parsing. I stedet for å sette `img.src` injiseres `<svg>`-elementet direkte i DOM-en. Dette gir:

- Ekte snap via `getPointAtLength()` / `getTotalLength()` på SVG-paths
- Direkte hover-koordinater uten ekstra koordinat-transformasjon
- % fall og ΔZ naturlig fra SVG-koordinater konvertert til meter

---

## Seksjon 1 — SVG-lasting og infrastruktur

### HTML-endringer

`<img id="cs-img">` erstattes av `<div id="cs-svg-host">`.

```html
<!-- før -->
<img id="cs-img" alt="Tverrprofil">

<!-- etter -->
<div id="cs-svg-host"></div>
```

### loadSvg() — endret flyt

```
1. Fetch SVG-tekst (allerede gjort)
2. Parse <svg>-rotelementet ut av teksten
3. Sett width="100%" height="100%" på <svg>
4. Injiser i #cs-svg-host
5. Appended et <g id="cs-overlay"> i <svg> for måle-elementer
6. Bygg koordinatmap fra x- og y-tikk-posisjoner (se under)
7. Kall resetCsZoom() (identisk som før)
```

### applyTransform()

Uendret logikk — `svgScale`, `svgPanX`, `svgPanY` bevares. CSS-transform settes på det injiserte `<svg>`-elementet i stedet for `<img>`.

### Koordinat-mapping

Matplotlib-SVG bruker SVG-piksler som enhet. Konvertering til real-world:

- **X-akse:** `parseSvgXTicks()` refaktoreres til å returnere `{svgX, realX}[]` par (meter fra CL) i stedet for dagens interne format. Den eksisterende kalleren oppdateres tilsvarende.
- **Y-akse:** Ny funksjon `parseSvgYTicks()` — parser y-tikk-tekstelementer og deres `y`-posisjon i SVG-koordinater.
- Resultat: lineær funksjon `svgToReal(x_svg, y_svg) → {x_m, z_m}` via to-punkt interpolasjon på hver akse.

### Dark mode

CSS `filter: invert(0.88) hue-rotate(180deg)` på `#cs-svg-host` når `darkMode === true`. Identisk visuell effekt som matplotlib-SVG invertert.

### renderer.py — data-cs-tagging

Alle data-path-elementer i `render_cross_section_svg()` får et `data-cs`-attributt:

| Element | Verdi |
|---------|-------|
| Planum/vegdekke | `kjørefelt` |
| Skulder | `skulder` |
| Skjæring | `skjaering` |
| Fylling | `fylling` |
| Terrengprofil | `terreng` |
| Senterlinje | `cl` |
| Kantstein | `kantstein` |
| Gang/sykkelvei | `gang_sykkel` |

Grid-linjer og akse-linjer tagges **ikke** — disse ekskluderes automatisk fra snap.

**Fallback for eldre SVG-er (uten data-cs):** Snap-logikken faller tilbake til alle `<path>`-elementer der stroke-farge ikke er `#aaaaaa` eller `#dddddd` (grid-farger). Snap fungerer, men tooltip viser ikke elementnavn.

---

## Seksjon 2 — Hover-avlesning

### Trigger

`pointermove` på `#cs-svg-host`. Deaktivert når `svgDragging === true`.

### Flyt

```
1. Konverter (e.clientX, e.clientY) → SVG-brukerkoordinater:
     svgX = (clientX - hostRect.left - svgPanX) / svgScale
     svgY = (clientY - hostRect.top  - svgPanY) / svgScale

2. Snap:
   - Iterer over alle <path data-cs> i det injiserte SVG-et
   - For hvert element: binærsøk med getPointAtLength() for å finne
     nærmeste punkt langs banen
   - Velg elementet med minst avstand (terskel: 20 SVG-px)
   - Hvis ingen treff innen terskel: bruk musepunktet direkte (ingen snap)

3. Konverter snap-punkt → real-world via svgToReal()

4. Beregn % fall til CL:
     fall_pst = (z_snap - z_cl) / |x_snap| * 100
     (der z_cl hentes ved x_m = 0 fra koordinatmap)

5. Oppdater SVG-overlay (<g id="cs-overlay">):
   - Fjern eksisterende hover-elementer (class="hover-el")
   - Tegn: vertikal + horisontal strek til akser (crosshair)
   - Tegn: <rect> + <text> tooltip med x, z, % fall, elementnavn
```

### Tooltip-innhold

```
x = +3.4 m fra CL
z = 87.45 m.o.h.
fall = 3.0 %
Kjørefelt
```

Tooltip forsvinner på `pointerleave` fra `#cs-svg-host`.

---

## Seksjon 3 — Punkt-til-punkt måling

### UI

En målingsknapp (linjal-ikon) legges til i `.svg-zoom-ctrl`-gruppen. Aktiv tilstand markeres med grønn bakgrunn.

Kursor: `crosshair` når aktiv.

### Tilstandsmaskin

```
IDLE
  → [klikk på måleknapp]  → WAIT_A
WAIT_A   (crosshair-kursor, "Klikk punkt 1" i header)
  → [klikk i SVG]        → WAIT_B  (lagre punkt A, tegn prikk A)
WAIT_B   ("Klikk punkt 2" i header)
  → [klikk i SVG]        → RESULT  (lagre punkt B, vis resultat)
  → [Escape / ny knapp]  → IDLE
RESULT
  → [klikk på måleknapp] → IDLE    (nullstill)
  → [Escape]             → IDLE
```

### Snap ved klikk

Identisk snap-logikk som hover, men lavere terskel (40 SVG-px) siden klikk er mer intensjonelt.

### Overlay-elementer (tegnes i `<g id="cs-overlay">`)

- Prikk A og prikk B: `<circle r="4" fill="#c25a1f"/>`
- Linje A–B: `<line stroke="#c25a1f" stroke-dasharray="6 3"/>`
- Bjelke/label midtpunkt: `<rect>` + `<text>` med horisontal avstand

### Resultpanel

En ny `<div id="measure-panel">` vises under den eksisterende `#panel-meta` (stasjonsmetadata forblir synlig). Vises kun når måling er aktiv (tilstand WAIT_B eller RESULT).

| Felt | Formel |
|------|--------|
| Horisontal avstand | `\|x_b - x_a\|` m |
| Høydeforskjell (ΔZ) | `z_b - z_a` m |
| % fall | `(ΔZ / \|ΔX\|) × 100` |
| Skrå avstand | `√(ΔX² + ΔZ²)` m |

Knapper: **Nullstill** · **Kopier** (kopierer resultater til clipboard som CSV-linje).

### Persistens ved navigasjon

Måling lagres som `{a: {x_m, z_m}, b: {x_m, z_m}}` i real-world koordinater.

Når `selectStation()` lastes ny SVG:
1. For hvert av punktene A og B: finn nærmeste `data-cs`-path-punkt til `(x_m, z_m)` i den nye SVG-en
2. Terskel: 2 m. Hvis utenfor terskel: det aktuelle punktet markeres som "løst" (åpen sirkel, gul farge) — brukeren ser at snap ikke traff
3. Overlay og resultpanel oppdateres automatisk med nye verdier

---

## Seksjon 4 — Kanttilfeller

| Situasjon | Håndtering |
|-----------|------------|
| Ingen snap innen terskel (hover) | Vis koordinater uten snap og uten elementnavn |
| Ingen snap innen terskel (klikk) | Klikket ignoreres; hint: "Ingen geometri her" vises kortvarig |
| Én snapende punkt ved stasjonsskift | Kun den ene enden markeres som "løs", resultatpanel skjules |
| Begge punkter utenfor terskel | Måling nullstilles automatisk |
| Normalprofil-drawer | Måling er utenfor scope — ingen endringer der |
| SVG ikke lastet | Hover og måleknapp er deaktivert |

---

## Filer som endres

| Fil | Endring |
|-----|---------|
| `web/profilutforsker.html` | Erstatt `<img>` med `<div>`, inline SVG-loading, hover + måle-logikk |
| `src/ifc_processor/renderer.py` | Legg til `data-cs`-attributter på path-elementer i `render_cross_section_svg()` |

Ingen endringer i backend-API, AGOL-opplasting eller andre filer.

---

## Utenfor scope

- Normalprofil-drawer
- Lengdeprofil-canvas
- Lagring av måleresultater til server
- Eksport av måling som bilde
