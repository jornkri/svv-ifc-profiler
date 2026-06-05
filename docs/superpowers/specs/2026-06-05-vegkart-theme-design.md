# Design: Vegkart-tema for profilutforskeren

**Dato:** 2026-06-05
**Status:** Godkjent i brainstorming
**Berørt fil:** `web/profilutforsker.html` (eneste fil som endres)

## Mål

Tilpasse profilutforskerens look and feel til Statens vegvesens Vegkart
(https://vegkart.atlas.vegvesen.no/), slik at appen leses som del av samme
visuelle familie. Ingen funksjonalitet fjernes; all endring er tema/layout.

Designtokens er hentet live fra Vegkarts CSS custom properties (2026-06-05).

## Hovedvalg (avklart med bruker)

| Valg | Beslutning |
|---|---|
| Omfang | **Mellomting (C):** slank topbar beholdes, sidebar → flytende lag-kort, kart fyller flaten under |
| Aksent | **Oransje `#ff9600` på interaksjon, grønn kun som semantikk** (suksess, «eksisterende veg») |
| Dark mode | **Beholdes** og re-tunes til ny palett |
| Font | **Mulish** (Google Fonts) erstatter Inter Tight; JetBrains Mono beholdes for tall |

## Del 1: Designtokens

Alle endringer skjer i CSS-variabelblokken (`:root` + `html[data-theme="dark"]`).
Verdier byttes; variabelstrukturen beholdes.

### Lys modus

| Rolle | Ny verdi | Erstatter |
|---|---|---|
| Kort/panelflate | `#ffffff` | beige `--paper #f4f3ee` |
| Bakgrunn | `#f5f5f5` | beige-varianter |
| Hover/inaktiv | `#ececec` | div. rgba |
| Mørk flate (topbar, aktiv) | skifer `#444f55` | navy `#062948` |
| Tekst primær | `#444f55` | mørkblå |
| Tekst sekundær | `#697277` | grå |
| Interaksjon (knapper, brytere, valg, fokus) | oransje `#ff9600` | grønn `#1f8a4a` |
| Suksess | `#158925` (bg `#e8f3e9`) | — |
| Feil | `#b63434` (bg `#fedfe1`) | — |
| Info | `#077197` (bg `#e6f1f5`) | — |
| Varsel | `#e27500` (bg `#fff5e6`) | `--warn #c25a1f` |
| Border svak | `#dadada` | rgba-verdier |
| Border tydelig | `#858d90` | rgba-verdier |
| Hjørner | `--r-sm: 2px`, `--r: 2px`, `--r-lg: 4px` | 5/8/12px |
| Skygge (flytende kort) | `0 2px 2px rgba(0,0,0,.3)` | div. |

**Urørt:** R700-fargene (`--road-gray #BBBCBC`, `--road-yellow #FFE080`,
`--road-existing #9aac98`), signal-rosa `#e0228e` (snap-markør).
Grønn `#1f8a4a` beholdes som semantisk farge der den bærer mening
(suksess-status, «eksisterende veg»-linja i profilene).

### Mørk modus (`html[data-theme="dark"]`)

| Rolle | Verdi |
|---|---|
| Bakgrunn | `#231f20` |
| Kort/panelflate | `#353e43` |
| Topbar | `#231f20` |
| Tekst primær / sekundær | `#ececec` / `#9aa4a9` |
| Interaksjon | oransje `#ff9600` (uendret — god kontrast på mørkt) |
| Border svak / tydelig | `#4a555c` / `#697277` |

### Typografi

- `--font-sans: "Mulish"` — humanistisk sans, nærmeste frie slektning av
  SVVs lisensierte LFT Etica (som ikke kan brukes). Google Fonts-lenken i
  `<head>` byttes fra Inter Tight til Mulish (vekter 400/600/700).
- `--font-mono: "JetBrains Mono"` — uendret (stasjonstall, koordinater).

## Del 2: Layout

### Topbar (beholdes, slankes)

- `--topbar-h: 52px` → `44px`, bakgrunn skifer `#444f55`.
- Innhold som i dag: brand, prosjektvelger, søk, 2D/3D-toggle, tema-knapp.
- Kontroller i Vegkart-stil: hvite/oransje flater, 2px hjørner.

### Sidebar → flytende lag-kort

- Dagens faste 280px-sidebar fjernes; kartet fyller hele bredden under topbaren.
- Lag-listen flyttes til et flytende hvitt kort oppe til venstre:
  - ~300px bredt, skygge `0 2px 2px rgba(0,0,0,.3)`, 2px hjørner.
  - Kollapsbar header («Lag» + chevron); minimert tilstand = knapp.
    Tilstand persisteres i `localStorage` (samme mønster som tema-valget).
  - Samme lag-rader som i dag (synlighet, navn, zoom-til) i ny drakt;
    synlighet vises som pille-toggle (se Del 3).
  - `max-height` med intern scroll så kortet aldri dekker hele kartet.

### Drawere (beholdes, restyles)

- Lengdeprofil (bunn) og tverrprofil (høyre) beholder dagens oppførsel og
  dimensjoner (`--drawer-bottom-h: 480px`, `--drawer-right-w: 460px`).
- Ny drakt: hvit bakgrunn, `#dadada`-kant mot kartet, skygge ut mot kartet —
  leses som «kort som skyves inn».

### Kartverktøy, info og legend

- map-tools (oppe til høyre): hvite kvadratiske 40×40-knapper i vertikal
  stabel med skygge — Vegkarts verktøy-rail.
- legend (nede til høyre) og map-info (koordinater/stasjon): små hvite kort
  med 2px hjørner og skygge.

### Snap-preview

- Glassmorphism (blur/transparens) erstattes av solid hvitt kort med skygge.
  Vegkart har ingen glasseffekter.

### 3D-scenen

- Arver samme CSS-variabler automatisk; ingen egen behandling.

## Del 3: Komponenter

- **Knapper:** primær = oransje fylt, hvit tekst; sekundær = hvit med
  `#858d90`-border; lenke-knapper = understreket tekst (à la Vegkarts
  «+ Legg til filter»).
- **Brytere:** pille-toggles (oransje på / grå av) der semantikken er av/på —
  lag-synlighet, 2D/3D-toggle.
- **Inputfelt/søk:** hvite, 2px hjørner, `#858d90`-border, oransje fokusring.
- **Statusmeldinger/toasts:** tintede bakgrunner per semantikk-tabellen over.
- **Diagrammer** (lengde-/tverrprofil): akser/tekst følger nye teksttokens;
  R700-flater urørt.
- **SVG-ikoner i dark mode:** eksisterende invert-filter
  (`invert(0.88) hue-rotate(180deg)`) beholdes.

## Feilhåndtering

Ingen ny logikk. Eksisterende feilmeldinger får kun ny stil. Eneste nye
JavaScript er kollaps-toggle for lag-kortet (én state-variabel + CSS-klasse,
persistert i `localStorage`).

## Testing

Manuell visuell verifisering (ingen pytest berøres — ren frontend):

- Begge temaer (lys/mørk) × 2D/3D × åpne/lukkede drawere.
- Lag-kort: kollaps/ekspander, persistens over reload, intern scroll ved
  mange lag.
- ArcGIS-widgetenes egne flater (popup, attribution, navigasjon) skjærer
  ikke mot ny palett.
- Snap-preview, legend, map-info og map-tools i begge temaer.

## Eksplisitt utenfor scope

- Ingen endring i datapipeline, AGOL-lag eller API-kall.
- Ingen endring av basemap (Geodata Kanvas beholdes).
- Ingen fjerning av funksjonalitet (dark mode, drawere, 3D beholdes).
- LFT Etica brukes ikke (lisensbelagt).
