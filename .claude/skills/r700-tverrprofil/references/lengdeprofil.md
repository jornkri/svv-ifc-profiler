# Lengdeprofil (upper half of C-tegning / D-tegning)

The C-tegning is the primary plan-and-profile sheet for primærveg (D-tegning is the same idea for sekundærveg). The sheet is split horizontally:

- **Lower half**: plan view with map background.
- **Upper half**: longitudinal profile (lengdeprofil) along the centreline.

This file covers only the upper-half profile. For plan-view rules see the handbook chapter 2.3 directly.

## Scales

- **Plan**: 1:1000 (1:500 for complex sections like crossings).
- **Profile**: horizontal scale matches plan (1:1000), **vertical scale 10× exaggerated (1:100)**. Always state both. The exaggeration is so vertical curvature is visible — without it, road grades look flat.
- Equidistance on the map background: 1 m (0.5 m at 1:500).

## What the profile shows

Plotted as graph lines against an elevation Y-axis on the left:

| Element | Style |
|---|---|
| Existing terrain (jord) along the centreline | Dashed line, jord pattern |
| Existing terrain (fjell) | Dashed line, fjell pattern (different from jord) |
| Designed road profile (profillinje) | Solid line, heavier weight |
| Crossing roads / rails / connecting roads (centrelines) | Solid vertical line at intersection, labelled |
| Bridges and underpasses | Drawn in profile with labelled fri høyde and bredde |
| Culverts (stikkrenner) | Symbol with diameter, inlet/outlet kote |
| Vertical curve points (vertikalvinkelpunkter) | Tick + label with profile number and elevation |
| Gradient labels (stigning) | Number with `%` and sign in the direction of increasing stationing, e.g. `+3.2 %` |

Plus, on regulering specifically, the technical data needed for cost estimates and to inform the public.

## The rubric block (under the profile graph)

Below the profile graph there is a stacked **rubric block** with a row for each of:

| Row | What it contains |
|---|---|
| **Profilnummer** | Stationing labels every 100 m (every 50 m at 1:500). |
| **Horisontalkurvatur** | Diagram showing horizontal curve points dropped vertically into the profile. Curve points are drawn as vertical dotted lines with curve direction and radius annotation. |
| **Breddeutvidelse** | Graphic showing width-of-carriageway expansion for curves; values labelled. Drawn at fixed (consistent) vertical position. |
| **Tverrfall** | Cross-fall diagram. Stepped profile drawn at scale **1 % = 2 mm**. Show + and – with the convention used in the project. |
| **Profilhøyde** | Designed road elevation at each station (table values). |
| **Terrenghøyde** | Existing terrain elevation at each station (table values). |

Profilnummer should be at the top of the rubric block (closest to the profile graph) and in agreement with the X-axis of the graph.

## Profile numbering

- Every **100 m** at 1:1000.
- Every **50 m** at 1:500.
- Mark vertical curve points (toppunkt, lavpunkt) regardless of the regular interval, with full elevation and stationing.

## Stigning convention

Slopes (`%`) are signed with `+` for uphill and `–` for downhill, **as seen in the direction of increasing stationing**. The `+` may be omitted; `–` must be shown.

## Reguleringsplan vs. konkurransegrunnlag

- **Reguleringsplan**: focus on geometry (centreline, vertical alignment, stigning) and major structures (bridges, underpasses) so the public and authorities can read the future road. Detailed culvert/drain info goes on G-tegninger.
- **Konkurransegrunnlag/arbeidstegninger**: full detail including stikkrenne dimensions and inlet/outlet kotes for simple culverts, where a separate G-tegning is not made. Existing terrain may be further differentiated (matjord, vegetasjonsdekke) with extra line types.

## Common mistakes to avoid

- Using the same vertical and horizontal scale. Vertical curves disappear and the profile looks like a pancake.
- Forgetting the tverrfall row in the rubric. It is *required*, not optional.
- Using non-distinct line types for jord vs. fjell terrain. The two materials must be visually distinguishable in B/W.
- Mislabelling stigning direction. The convention is in the direction of *increasing* stationing — not increasing elevation.
- Overlapping the profile graph and the rubric block. Keep them stacked, not overlapping.
