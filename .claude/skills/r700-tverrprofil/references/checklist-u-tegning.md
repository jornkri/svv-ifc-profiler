# Checklist: validating a U-tegning (tverrprofil) against R700

Walk this checklist top-to-bottom when reviewing a generated or hand-drawn tverrprofil sheet. Mark each as Pass / Fail / N/A and report concrete pointers (which profile, which feature) for failures.

## Sheet-level

- [ ] Sheet is in A1 format (or scaled-down A3 derived from A1).
- [ ] Title block is in the lower right corner.
- [ ] Title block is rotated 90° if the drawing reads from the right (and only then).
- [ ] Title block contains: project name, parsell, drawing title (`Tverrprofiler profil X – Y`), drawing number (U101, U102, …), scale (e.g. `Målestokk A1 1:200`), status word (`Reguleringsplan` / `Konkurransegrunnlag` / `Arbeidstegninger` / `Som utført`), date, drawn-by / checked-by / approved-by initials.
- [ ] A `Tegnforklaring` (legend) appears once on the sheet.
- [ ] Every symbol in the legend appears on the drawing, and vice versa.
- [ ] Background is graph paper (`ruteark`); grid is visible but not overpowering.
- [ ] Scale is one of 1:200, 1:100, 1:400. Stated in title block.
- [ ] All text is readable from either bottom *or* right of the sheet — not a mix.

## Per-profile

For each profile on the sheet:

- [ ] Profile number is written above the profile, plain text, no decoration.
- [ ] A solid horizontal reference line marks the chosen kotehøyde, snapped to a whole metre.
- [ ] Kotehøyde value is labelled at the left end of the reference line.
- [ ] The designed road geometry is drawn as **solid** lines.
- [ ] The existing terrain is drawn as **dashed** lines and extends beyond the road footprint up the cut slope and down the fill slope.
- [ ] Jord terrain and fjell terrain (where both apply) use distinct dash patterns.
- [ ] The profile is projected forward in the line; reading direction is consistent across the sheet.
- [ ] Profiles do not overlap with their neighbours.

## Konkurransegrunnlag / arbeidstegninger only

- [ ] Mass-type layers are shown with the correct hatch patterns (vegetasjonsdekke, matjord, myr, jord, fjell, dypsprengning).
- [ ] Layer thicknesses come from the model (not fabricated).
- [ ] Road equipment intersecting the section is shown: rekkverk, støyskjerm, gjerde, mur, light masts, kabler, ledninger, vegetation if relevant.
- [ ] Houses/fences near (but not on) the section are projected onto the nearest profile and shown dashed.

## Naming and ordering

- [ ] Profile numbers are in increasing stationing order, bottom-to-top on the sheet.
- [ ] Stationing range in the title block matches the first and last profile actually shown.
- [ ] Adjacent sheets (U101, U102, …) overlap in profile numbers or are perfectly contiguous — no gaps.

## Colour and weight

- [ ] Drawing is readable in B/W (test by desaturating).
- [ ] Pale line colours are not used.
- [ ] Line thickness ≥ 0.25 mm at A1; letter heights ≥ 2.5 mm; line thickness ≈ 10 % of letter height.

## Common automated-generation pitfalls

When the source is a programmatic generator (e.g. SVG from IFC), check specifically:

- [ ] The grid is rendered, not skipped.
- [ ] The reference line is per profile and snapped, not a single global line.
- [ ] Existing-vs-designed is differentiated by line type, not colour alone.
- [ ] The cross-section is perpendicular to the centreline at the station — verify by checking that two adjacent profiles 10 m apart give consistent road-edge offsets on a straight.
- [ ] Centreline vertical mark is included on every profile.
- [ ] Layer hatches are from R700 Vedlegg 3, not invented.
- [ ] Title block is regenerated per sheet (not copy-pasted with stale stationing range).
