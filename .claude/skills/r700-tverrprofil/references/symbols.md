# R700 Vedlegg 3 — symboler, fargekoder og linjetyper

This is the distilled symbol/colour/line-type reference for the drawing types that matter for profile work (C/D plan-and-profile, F normalprofil, U tverrprofil). For O-tegninger (vegetation), W-tegninger (grunnerverv), L (skilt), M (signal), and others, see the handbook directly.

## General drawing conventions

The drawing background ("kartgrunnlag") should be toned down so the theme of the current drawing stands out. On a colour sheet the underlying topo/ortofoto is shown lighter than the foreground theme.

Standard sheet elements that almost always appear:

| Symbol | Meaning |
|---|---|
| North arrow (nordpil) | Always near the title block, north pointing up by default. |
| Scale bar (målestokklinjal) | Horizontal scale bar with metres marked, e.g. `0 10 20 30 40` for 1:1000. |
| Coordinate grid or coordinate crosses | Mandatory on any drawing on map background. |
| Title block (tittelfelt) | Lower right corner. 165 × 80 mm in A1. |
| Revision cloud + letter | New revisions get a cloud around the changed area and a letter (A, B, C…) in the title block revision table. Previous revision's clouds are erased on the next revision; only the letter and explanation stay. |
| Reference to note | Circle with a number inside, e.g. `③`. |
| Section reference | Letter (A, B, …) with arrow showing view direction. |
| Cross-reference to model/line | Pennant-shaped tag with line number, e.g. `68402`. |
| Property number | Red text `gnr/bnr`, e.g. `12/297`. |
| Spot height (kotehøyde topp asfalt) | Number with arrow pointing to the point, e.g. `123,59`. |
| Slope arrow (fallpil) | Arrow with percentage, e.g. `3%`. |
| Polygon point | `Pp` with number. |
| Demolish / remove | Crossed out with `X X X X` running line. |

## Colour codes (filled areas, plan view)

These are the canonical area fills on C/D plan drawings. Use the same colours when a tverrprofil shows the same areas in section.

| Area | Colour | Notes |
|---|---|---|
| Eksisterende veg | Light grey | The existing carriageway. |
| Kjøreveg (designed) | Darker grey | The designed carriageway. |
| Gangveg / sykkelveg | Magenta / pink | Foot/bike. |
| Skjæring, fylling, grøft | Yellow | Cut, fill, and ditch areas — all the same yellow. |
| Annet vegareal | Orange | Anything in the road footprint not covered by the above. |
| Vann | Light blue / cyan | Water. |
| Permanent erverv (W-tegn) | Yellow | Land permanently acquired. |
| Permanent klausulert areal | Orange | Permanent restriction. |
| Midlertidig beslaglagt areal | Green | Temporary. |
| Tilbakeført areal | Cyan | Land restored to original use. |

Colour is supplementary to line type. A B/W print must still be unambiguous.

## Line types — eksisterende vs. prosjekterte

R700 distinguishes existing features from designed features by line type. The pattern below holds across most drawing types: existing is thinner and often dashed; designed is solid and may be coloured.

| Feature | Eksisterende | Prosjektert |
|---|---|---|
| Senterlinje | Thin solid line | Thin solid line (same — context distinguishes) |
| Eiendomsgrense | Red long-dash | Red dashed double |
| Anleggsbelte / entreprisegrense | Black short-dash | Black dash-dot |
| Byggegrense | Solid line | Solid line + tick |
| Rekkverk (guardrail) | Solid black with dot beads `●—●—●` | Solid green with dot beads (designed) |
| Støyskjerm (noise barrier) | Solid line with vertical ticks | Same in green / heavier |
| Gjerde / viltgjerde (fence) | Thin solid with cross-tick `┬` | Same, designed colour |
| Mur (wall) | Solid double line | Solid double line, designed colour |
| Terrengprofil — jord | Dashed line in section | n/a (terrain is always existing) |
| Terrengprofil — fjell | Dashed line with rock-spike marks | n/a |
| Frisiktområde | Hatch pattern bordered area | n/a |
| Planeringsområde | Diagonal hatch | n/a |
| Riggområde | Crossed hatch | n/a |
| Avkjørsel | Tick marks across road | Tick marks across road |
| Avkjørsel stenges | Double bar across | n/a |
| Tunnelportal / tunnel | Double line with end caps | Double line with end caps, designed colour |

## Layer hatches for cross-sections (F/J/K-tegning)

Used in tverrprofil and normalprofil to show the materials in section. These patterns are defined by R700 — do not invent new ones.

### Dekketyper (surface/wear courses)

| Material | Hatch |
|---|---|
| Steinsetting | Stone-block pattern (irregular polygons) |
| Asfaltbetong | Solid black |
| Betong | Dotted fill |
| Grus | Coarse dotted fill |
| Bindlag generelt | (Specified per project) |

### Bærelagstyper (base courses)

| Material | Hatch |
|---|---|
| Bitumenmasser | Diagonal hatch (one direction) |
| Sementstabiliserte masser | Cross-hatch |
| Knuste masser | Angular fragment fill |

### Forsterkningslagstyper (reinforcement courses)

| Material | Hatch |
|---|---|
| Grusbasert | Round-pebble fill |
| Pukkbasert | Sharp-stone fill |
| Sprengt stein | Large angular block fill |

### Lette masser (lightweight fill)

| Material | Hatch |
|---|---|
| Glasopor / lette masser | Bubble-pattern fill |
| Isolasjonsmaterialer | Square block fill |

### Diverse

| Material | Hatch |
|---|---|
| Naturstein | Natural-stone polygons |
| Vekstjord (topsoil) | Light dot/dash fill |
| Tetningslag | Solid line band |
| Fiberduk | Long-dash line band |
| Jord-/asfaltarmering | Two-dash-with-dot band |
| Betongkonstruksjon | Concrete hatch (solid grey fill with ticks) |

## Lengdeprofil (longitudinal) line types

The terrain line in the upper half of a C-tegning differentiates jord and fjell with different dash patterns. Designed road profile is solid; existing is dashed. Vertical curve points (vertikalvinkelpunkter) are marked with a small vertical tick and labelled with profile number and elevation.

## Practical defaults for an SVG renderer

When rendering R700-style profiles in SVG (typical for a web app):

```
Designed road geometry:    stroke-width 0.5 mm, solid, black
Existing terrain (jord):   stroke-width 0.35 mm, dashed (4,2)
Existing terrain (fjell):  stroke-width 0.35 mm, dash-dot (4,2,1,2)
Reference line (kotehøyde): stroke-width 0.5 mm, solid, black
Centreline (vertical):     stroke-width 0.25 mm, dash-dot (2,2,0.5,2)
Grid (1 m at 1:200):       stroke-width 0.1 mm, light grey
Profile number text:        font-size 3.5 mm, sans-serif, plain
Kotehøyde label:            font-size 2.5 mm, sans-serif, plain
```

These are starting points sized for A1 print; scale proportionally for A3 reduction.
