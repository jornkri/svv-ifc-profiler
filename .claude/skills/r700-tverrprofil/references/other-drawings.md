# Other R700 drawing types (quick reference)

The R700 handbook covers drawing types A–Z. This skill focuses on C (lengdeprofil), F (normalprofil), and U (tverrprofil) because those are what you build from a road BIM/IFC for a profile-viewer app. The rest are summarized below in case the user's request brushes against them — read the handbook directly for full rules.

| Code | Name | Purpose |
|---|---|---|
| A | Forside og tegningsliste | Cover sheet (location map + key data) and drawing list. Title is `Tekniske tegninger Reguleringsplan` / `… Konkurransegrunnlag` / `… Arbeidstegninger`. |
| B | Oversikt - plan og profil | Overview map, less detail than C. |
| C | **Primærveg - plan og profil** | Plan + lengdeprofil for the primary road. *Covered in `lengdeprofil.md`.* |
| D | Sekundærveg - plan og profil | Same as C, for secondary road / sideveg. |
| E | Vegkryss og avkjørsler | Junctions, accesses, busslommer, parkeringsplasser. |
| F | **Normalprofiler og overbygning** | Typical cross-section template + pavement structure. *Covered in `normalprofil.md`.* |
| G | Drenering og vannbehandling | Drainage and water handling. May be merged with H as GH. |
| H | VA-ledninger | Water/sewage pipelines. May be merged with G. |
| I | Kabler og linjer | Cables and lines. May be merged with N as IN. |
| J | Byggetekniske detaljer | Construction details: kantstein, rekkverk, mindre støttemurer, støyskjermer, gjerder. |
| K | Konstruksjoner | Structures: bruer, underganger, kulverter, store støttemurer, tunnelportaler. |
| L | Skilt og oppmerking | Signs and road markings. |
| M | Signalanlegg | Traffic signals. Special rule: full symbol table goes in the legend regardless of what's used. |
| N | Belysning | Lighting. May be merged with I. |
| O | Formgiving og vegetasjon | Landscaping and vegetation. |
| P | Mengder | Quantities, mass profiles, mass diagrams. |
| Q | Konflikttema | Conflict themes — used to surface conflicts between layers. Created when needed. |
| R | (For other agencies) | Available for non-SVV stakeholders. |
| S | (For other agencies) | Same. |
| T | Visuell presentasjon | Visualisations / renderings. |
| U | **Tverrprofiler** | Cross-sections at stations. *Covered in main `SKILL.md`.* |
| V | Geoteknikk og geologi | Geotech and geology. Includes its own cross-sections drawn similarly to U. |
| W | Grunnerverv | Land acquisition. |
| X | Ytre miljø og naturressurser | External environment and natural resources. |
| Y | Faseplaner | Phase / construction-stage plans. |
| Z | Risikofylte arbeider | High-risk work. |

## Drawing numbering convention

R700 uses a three-digit numbering system per drawing type, e.g.:

- `U101`, `U102`, `U103` … the 101–199 range usually means konkurransegrunnlag/arbeidstegninger.
- `U201`, `U202` … sometimes used for variants or different sections.

When generating a series of tverrprofil sheets from a long road, use sequential numbers within the U-range. Fill the title block's "Tegningsnummer" field with the full code.

## When the user asks for a drawing type not covered here

Ask the user to attach the R700 PDF (it is not bundled with the skill due to size) and read the relevant chapter. The chapters are numbered 2.1 (A) through 2.26 (Z) and follow a consistent structure: *Generelt* → *Tekniske tegninger for reguleringsplaner* → *Konkurransegrunnlag og arbeidstegninger*.
