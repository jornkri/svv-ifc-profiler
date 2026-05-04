# Normalprofil (F-tegning)

A normalprofil is a *typical* (template) cross-section, drawn once per dimensjoneringsklasse (design class) used in the project. The handbook treats this separately from U-tegninger because it lives in a different part of the document set: F-tegningene establish what the road *should* look like, U-tegningene show what it *will* look like at every station.

If you are extracting cross-sections from an IFC model at a 10 m interval, those are U-tegninger. The normalprofil is the *template* the engineer designed against.

## Scale

- Cross-section view: **1:50** is standard. 1:25 or 1:100 may be used for special cases.
- Pavement structure detail: **1:10**, drawn alongside or below the main section.

## What the normalprofil shows

For each dimensjoneringsklasse, show typical sections at:

- **Straight road on fill** (rettlinje på fylling)
- **Cut in soil** (jordskjæring)
- **Cut in rock** (fjellskjæring)
- **Tunnel** (if any)
- **Roundabout** (full section through the whole roundabout including side areas like sykkelveger, sideveger, murer)

Each section must include:

- Lane widths (kjørebanebredde) and shoulder widths (skulderbredde) labelled in metres
- Cross-fall (tverrfall) labelled with arrow + percentage, e.g. `3 % →`
- Ditch geometry (grøftedybde, grøftebredde, indre/ytre skråning)
- Slope gradients (skråningsutslag), e.g. 1:2 or 1:1.5
- **Rekkverksrom** — the protected zone behind a guardrail, with the guardrail symbol placed correctly relative to the shoulder edge
- Position of road equipment: rekkverk, light masts, cable trenches, sign foundations
- **Layered pavement structure** with each layer's thickness and material — slitelag, bindlag, bærelag, forsterkningslag, frostsikringslag, undergrunn
- Where applicable: dypsprengning (deep blasting), wedging at jord/fjell transitions, breddeutvidelse, motfylling, shoulder-to-ditch transitions

## Tunnel normalprofil specifics

- Show the tunnel cross-section silhouette (typical Norwegian rounded-arch profile)
- Mark sign and luminaire positions and heights (frihøyde langgående markør, kjørebaneprofil høyre/venstre)
- Indicate vann- og frostsikring (water/frost protection liner)
- Show fjellsikring (rock support bolts), drenering (drainage), kabelgrøfter (cable trenches)
- Include the pavement structure at tunnel section
- Show typical sections from different parts of the tunnel if the geometry varies (portal, midt-tunnel, havarinisje)

## Pavement structure detail

This is a separate small drawing alongside the normalprofil, scale 1:10 or 1:20, showing each layer as a horizontal band with:

- **Layer name** (Slitelag, Bindlag, Bærelag, Forsterkningslag, Frostsikringslag, Undergrunn)
- **Thickness** in mm
- **Material** (e.g. Ab 11 70/100, Pukk 0/32, Sprengt stein)
- **Hatch pattern** matching the material type (see `symbols.md`, "Layer hatches")

Total tykkelse (total thickness) is typically annotated to the right of the layer stack.

## Reguleringsplan vs. konkurransegrunnlag

For **reguleringsplan**, the F-tegning is simpler: show the typical geometry with overall dimensions but the pavement layer detail can be omitted. Total overbygningstykkelse should still be considered (it affects ditch depth and cost).

For **konkurransegrunnlag/arbeidstegninger**, the full layer detail with material specs is required.

## Common mistakes to avoid

- Drawing only one normalprofil for the whole project — there are usually multiple dimensjoneringsklasser, and each gets its own.
- Forgetting the rekkverksrom — guardrails need lateral space behind them defined by the standard, and the normalprofil is where that's documented.
- Inventing layer hatches. Use the patterns from R700 Vedlegg 3 (`symbols.md`).
- Mixing cut and fill conventions on the same section. A "skjæringsprofil" shows cut on both sides; a "fyllingsprofil" shows fill on both sides; a "halvskjæring/halvfylling" is its own variant and gets its own template.
