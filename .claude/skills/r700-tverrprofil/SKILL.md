---
name: r700-tverrprofil
description: Generate and validate Norwegian road cross-section drawings (tverrprofiler), longitudinal profiles (lengdeprofiler), and normalprofiler that follow Statens vegvesen håndbok R700 (Tegningsgrunnlag). Use this skill whenever the user is producing, reviewing, or styling road profile drawings — for example when extracting cross-sections from a BIM/IFC vegmodell, rendering tverrprofil SVGs from a centerline at fixed station intervals, building a viewer that shows R700-styled profiles next to a 2D plan, or checking that a generated drawing complies with R700. Trigger on any mention of "tverrprofil", "lengdeprofil", "normalprofil", "U-tegning", "F-tegning", "C-tegning", R700, "håndbok 139", veggeometri rendered as 2D, "kotehøyde", "stasjonering" / "profilnummer", or when the user uploads an IFC vegmodell and wants 2D drawings out of it. Use it even when the user does not explicitly mention R700 — if the deliverable is a Norwegian road cross-section, this skill applies.
---

# R700 Tverrprofil & Profil-tegninger

## What this skill is for

Statens vegvesens håndbok R700 *Tegningsgrunnlag* is the Norwegian standard for how road drawings must look — symbols, colours, line types, layout, scales, title block. This skill captures the rules you need to **render or validate** three drawing types that come up when working from a BIM/IFC road model:

- **Tverrprofil (U-tegning)** — cross-section perpendicular to the centreline, typically every 10–25 m. *This is the primary output.*
- **Normalprofil (F-tegning)** — a *typical* cross-section template per dimensjoneringsklasse (straight on fill, in cut, in tunnel, etc.).
- **Lengdeprofil (part of C-tegning)** — elevation along the centreline with rubrikker for stationing, curvature, cross-fall, etc.

The handbook is large and covers many drawing types (A–Z). The rules below are distilled to what governs the *visual output* of profile drawings. If you need other drawing types, see [`references/other-drawings.md`](references/other-drawings.md).

When in doubt, look at the visual examples in `assets/examples/` — those are the ground truth. The example page `assets/examples/U201-tverrprofil.png` is the single most important reference for tverrprofil layout.

## Core principles (read first)

1. **Drawings must be readable in B/W as well as colour.** Avoid pale line colours; rely on line type and weight, not colour alone, to carry meaning. Colour is icing.
2. **A1 is the design format.** Most drawings are produced in A1 and presented in A1 and/or A3. Letter heights ≥ 2.5 mm, line thickness ≥ 0.25 mm in A1; line thickness ≈ 10 % of letter height. Scale a generator's output so this still holds when reduced to A3.
3. **Every tegning has a tegnforklaring (legend) on the sheet itself** that explains every symbol used on *that* sheet. Never put a symbol in the legend that does not appear on the drawing.
4. **Title block (tittelfelt)** sits in the lower right corner. On U-tegninger only, the title block may be rotated 90° because the drawing reads from the side — that's the one exception.
5. **Skal / bør / kan** are the handbook's verbs. *Skal* = requirement, *bør* = recommendation, *kan* = option. For chapter 1.1 and chapter 2 (presentation/drawing rules), deviations are only allowed when they improve readability and must be approved by the same authority that approves the rest of the drawing set.

## Tverrprofil (U-tegning) — the primary output

### Layout on the sheet

- **Scale**: 1:200 by default. 1:100 and 1:400 are allowed. State the scale in the title block.
- **Paper**: graph paper background ("ruteark"). The grid is part of the look — do *not* hide it. At 1:200 a 1 m square = 5 mm on paper, so the visible grid should match.
- **Reading direction**: U-tegninger may read either *from below* or *from the right* (this is the only drawing type where right-reading is standard). Pick one for the project and be consistent across the sheet set. The title block rotates with the drawing.
- **Profiles are projected forward in the line**, drawn from the bottom of the sheet upward. The first profile (lowest stationing) goes at the bottom; later profiles step upward and to the right. Don't overlap — leave enough whitespace between profiles that terrain lines from one don't bleed into the next.
- Several profiles per sheet is the norm (the U101/U201 examples show 4–6 profiles per A1 sheet). Group profiles in stationing ranges, e.g. "Tverrprofiler profil 4900 – 4930".

### Anatomy of a single tverrprofil

Each profile must show, at minimum:

1. **Profile number above the profile**, e.g. `1700.00` or `4910`. Use the project's stationing convention. This is the single non-negotiable label.
2. **A horizontal solid reference line** at a chosen elevation, with the **kotehøyde** (e.g. `33`, `34`, or `123.59`) labelled at the left end. This is the "anchor" the profile is drawn against — without it a tverrprofil is unreadable.
3. **The road cross-section** — solid lines for the designed road geometry: top of asphalt, shoulders (skulder), edges of carriageway (kjørebanekant), ditches (grøft), and the slopes (skråninger) down to terrain.
4. **Existing terrain** — the natural ground surface, drawn as a **dashed line** that extends well beyond the road footprint up the cut slope and down the fill slope. The pre-existing terrain is the dashed signal; the designed road is the solid signal.
5. **Mass-type layers** (only on Konkurransegrunnlag/arbeidstegninger, not on regulering): vegetation cover, topsoil, peat, soil, rock, deep blasting (dypsprengning). Each gets its own hatch pattern — see [`references/symbols.md`](references/symbols.md).
6. **Road equipment** that intersects the section: guardrails (rekkverk), noise barriers (støyskjermer), fences (gjerder), retaining walls (murer), light poles, cables, ditches, culverts. House outlines or fences sitting near the section can be projected onto the nearest profile (dashed).
7. **No title or legend per profile.** The legend lives once per sheet, not once per profile.

### What goes in the title block

`Tverrprofiler profil <fra> – <til>` (e.g. `Tverrprofiler profil 4900 – 4930`), project name and parsell, scale (e.g. `Målestokk A1 1:200`), drawing number (e.g. `U101`, `U201`, …), status (`Reguleringsplan` / `Konkurransegrunnlag` / `Arbeidstegninger` / `Som utført`), date, who drew/checked/approved.

### Stationing intervals

R700 does *not* fix the interval between tverrprofiler — it is a project decision. Common practice in Norwegian road projects is **every 20 m on straights and every 10 m in curves and complex areas**. For a generator with a single user-controlled parameter, **default to 10 m**: it is denser than typical practice but always acceptable and gives the click-along-centreline UX a nice resolution. Make it configurable.

## Normalprofil (F-tegning)

A normalprofil is a *typical* cross-section template, not a measured profile. One per dimensjoneringsklasse used in the project, typically shown for: straight on fill, cut in soil, cut in rock, and tunnel (if applicable).

- **Scale 1:50** is standard. Use 1:10 for the pavement structure detail.
- Show: lane widths, shoulder widths, ditch geometry, slope gradients, guardrail room (rekkverksrom), light pole and cable trench positions, and the **layered pavement structure** (slitelag, bindlag, bærelag, forsterkningslag, frostsikringslag, undergrunn).
- Width expansion (breddeutvidelse), wedging at rock-cut/soil-cut transitions, counter fill (motfylling), and shoulder/ditch transitions belong on the F-sheet, not on every U-tegning.
- Pavement layer hatch patterns are defined in Vedlegg 3 of R700 — see `references/symbols.md` (section "Dekketyper / bærelag / forsterkningslag").
- For a roundabout, the F-sheet shows a section through the *whole* roundabout including side areas (sykkelveg, parallelle sideveger, murer).

For full F-tegning rules (technical drawing variant, tunnel specifics, etc.) see [`references/normalprofil.md`](references/normalprofil.md).

## Lengdeprofil (upper half of C-tegning)

- **Plan in 1:1000** (1:500 for complex areas), **profile vertical exaggeration is 10×** (i.e. horizontal 1:1000, vertical 1:100) — this is so vertical curvature is readable. Always state both scales.
- Below the profile graph, a **rubric block** with rows for: profilnummer, horisontalkurvatur, breddeutvidelse, tverrfall, profilhøyde, terrenghøyde. Tverrfall is shown as a small stepped diagram where **1 % = 2 mm** vertically.
- Profile numbers are written every 100 m (every 50 m at 1:500).
- **Horizontal curvature points** drop into the profile as **vertical dotted lines** (kurvepunktene stiples inn vertikalt).
- Show: existing terrain along the centreline (jord vs. fjell with different line types), the design profile line, vertical curve points (vertikalvinkelpunkter) with profile number and height, gradients (stigninger) in % with sign in the direction of increasing stationing, centerlines of crossing roads/rails/connecting roads, bridges and underpasses with free height/width, culverts with diameter and inlet/outlet kote.

For full lengdeprofil rules see [`references/lengdeprofil.md`](references/lengdeprofil.md).

## Symbols, line types, and colours

R700 Vedlegg 3 governs all symbols and colours. The full reference is in [`references/symbols.md`](references/symbols.md). Highlights you'll hit constantly on profile drawings:

- **Existing vs. designed line types** are different, and that distinction must be visible in B/W. *Eksisterende* lines are typically thinner / dashed; *prosjekterte* lines are typically solid / heavier and may be coloured.
- **Colour conventions** (plan colours):
  - Existing road: light grey
  - Carriageway (kjøreveg): darker grey
  - Pedestrian path (gangveg): magenta/pink
  - Skjæring/fylling/grøft (cut/fill/ditch areas): yellow
  - Annet vegareal: orange
  - Water: light blue
  - Designed guardrail (rekkverk): green dotted line
  - Property lines (eiendomsgrenser): red dashed
- **Terrain profile line types**: jord (soil) and fjell (rock) are drawn with *different* dash patterns, both visible in B/W. Differentiate further if the project distinguishes matjord, vegetasjonsdekke, etc.
- **Layer hatches** (pavement and base courses) are defined patterns — do not invent new ones. Use the patterns in `references/symbols.md`.

## When generating tverrprofiler programmatically (e.g. SVG from IFC)

This is the common build task. A few rules that fall out of R700 that are easy to get wrong in code:

1. **Render the grid first**, in light grey, with 1 m × 1 m cells at the chosen scale. The grid is part of the drawing.
2. **Pick one kotehøyde per profile**, snapped to a whole metre below the lowest point of the section, and draw the solid horizontal reference line at that elevation. Label the elevation at the left end. Do *not* float the profile in space.
3. **Solid for designed, dashed for existing.** Don't be tempted to use colour as the only distinguisher — drawings must hold up in B/W.
4. **Project the profile forward**, i.e. the cut plane is perpendicular to the centreline at the station, and "forward" (positive stationing) is into the page. Looking at the sheet, you are looking in the direction of increasing stationing. This affects which side of the profile is left vs. right — be consistent.
5. **Centreline vertical mark**: drop a thin vertical centreline mark through every profile so the reader can align them visually.
6. **Profile number above the profile**, plain text, no box. Don't wrap it in any decoration.
7. **Layer thicknesses come from the model** for arbeidstegninger; on regulering it is acceptable to omit them. Don't fabricate layer thicknesses.
8. **Don't crowd the sheet.** If profiles overlap, paginate — split into more U-sheets numbered U101, U102, …

A reference SVG template that follows these rules is in `assets/templates/tverrprofil-template.svg`. Use it as a starting point for any new generator and adapt — do not deviate from its line types and weights without a documented reason.

## Validating an existing drawing against R700

When asked to "check" or "review" a profile drawing:

1. Look at `assets/examples/U201-tverrprofil.png` and compare structurally — is the layout recognizable as a U-tegning?
2. Walk the checklist in [`references/checklist-u-tegning.md`](references/checklist-u-tegning.md). Don't skip items. Report findings as a list of pass/fail items with concrete pointers.
3. Be specific. "Existing terrain not dashed" is useful; "doesn't follow R700" is not.

## Status field on the title block

R700 prescribes the wording exactly, and it changes through the project lifecycle:

- During regulation: **"Reguleringsplan"**
- Tender drawings: **"Konkurransegrunnlag"**
- Once contract signed and used for construction: **"Arbeidstegninger"**
- After hand-over with measured updates: **"Som utført"**

For a tool generating drawings from an IFC, the status is whatever the *user uploading the IFC* declares — surface it as a parameter, do not hard-code.

## When you're unsure

- Open the example pages in `assets/examples/` and compare visually.
- The full handbook is published by Statens vegvesen — search "Håndbok R700 Tegningsgrunnlag" on vegvesen.no. Ask the user to attach the PDF if you need to look up an edge case not covered here; the file is too large to bundle in the skill.
- If a rule conflicts with what the IFC or the user provides, follow the IFC/user but note the deviation. R700 explicitly allows deviations when they improve readability — but they must be deliberate and noted.
