# Lengdefall-påskrift i interaktiv lengdeprofil (R700)

**Dato:** 2026-06-09
**Status:** Design godkjent, klar for plan
**Gren:** `feat/lengdefall-paaskrift-lengdeprofil`

## Bakgrunn og mål

Statens vegvesen har gjennomgått profilutforskeren og bedt om at **lengdefall/stigning** vises
som påskrift i den interaktive lengdeprofilen, slik håndbok R700 krever. Den statiske R700-PNG-en
(`renderer.py` `_draw_gradient_labels`) tegner allerede slike merker, men den interaktive
SVG-grafen i `web/profilutforsker.html` mangler dem.

**Mål:** Tegne `+X,X %` / `–X,X %` langs designlinja i den interaktive lengdeprofilen, én verdi
per konstant-fall-strekk (tangent), i tråd med R700.

### Hva R700 sier

Stigningspåskriften hører til **vertikalgeometrien**, ikke til et fast meterintervall. Det skal
være **én %-verdi per tangent** (konstant-fall-strekk) mellom vertikalvinkelpunktene
(toppunkt/lavpunkt). Fortegnet følger retning økende stasjonering; `+` kan utelates, `–` skal
vises. Profilnummer hver 100 m er en egen rubrikk-rad, ikke der stigningen skrives.

Den statiske PNG-en bruker i dag en pragmatisk per-100m-approksimasjon. Dette designet erstatter
**ikke** PNG-en, men gir den interaktive grafen den ekte tangent-baserte påskriften.

## Avgrensning (YAGNI)

- **Kun** stigningspåskrift i den interaktive lengdeprofilen. Ikke tverrfall, ikke nye rubrikk-rader.
- `gradient_pct` per stasjon (endelig differanse) **røres ikke** — den lever videre i måle-panelet.
- Den statiske PNG-en endres ikke i denne omgangen.
- Vertikalkurver (`PARABOLICARC`/`CIRCULARARC`) får **ingen** påskrift — de er overganger mellom
  tangenter, ikke konstant-fall-strekk.

## Datagrunnlag (finnes allerede)

| Kilde | Hva vi har | Tangent-utledning |
|-------|-----------|-------------------|
| IFC4X3 | `IfcAlignmentData.vertical_segments` — `CONSTANTGRADIENT`-tangenter med eksakt `start_gradient` (m/m), pluss kurve-segmenter | Filtrer til `CONSTANTGRADIENT`; `gradient_pct = start_gradient*100` |
| LandXML | `vertical_pvi` — liste `[(stasjon, høyde)]` fra `ProfAlign` PVI-er | Mellom nabo-PVI-er er fallet konstant: `(z₁−z₀)/(s₁−s₀)*100` |

Begge reduseres til **samme utdata**: en liste konstant-fall-strekk. Frontend blir dermed
kilde-agnostisk.

## Arkitektur — fire lag

### 1. Datamodell (`pipeline.py`)

- Utvid `AlignmentMetadata` med `vertical_segments: list[VerticalSegment]`
  (føres inn fra IFC; tom for LandXML — der brukes `vertical_pvi`).
- Ny hjelpefunksjon som bygger en samlet liste konstant-fall-strekk fra `align_meta`:
  - **IFC** (har `vertical_segments`): ta `CONSTANTGRADIENT`-segmentene →
    `{sta_start, sta_end, gradient_pct}`. Hvis modellen ikke har noen `CONSTANTGRADIENT`-segmenter
    (rent PVI/parabel-basert vertikal), fall tilbake til PVI-utledning fra `vertical_pvi`
    (`vertical_profile_pvi()`), samme som LandXML.
  - **LandXML** (tom `vertical_segments`, har `vertical_pvi`): utled fra nabo-PVI-er.
  - Gradient avrundes til 1 desimal (samsvarer med R700-presisjon og PNG-en).

### 2. Utdata (`vertical_alignment.json`)

Speiler `horizontal_alignment.json`-mønsteret. Skrives til jobbens `output/`-mappe ved siden av
`horizontal_alignment.json`. Tom liste hvis ingen vertikalgeometri finnes.

```json
[
  { "sta_start": 0.0,   "sta_end": 240.0, "gradient_pct": 2.5 },
  { "sta_start": 280.0, "sta_end": 510.0, "gradient_pct": -1.8 }
]
```

### 3. API (`server.py`)

Nytt endepunkt `GET /api/jobs/{job_id}/vertical-alignment` — kopi av `get_horizontal_alignment`
(server.py:345): leser `vertical_alignment.json`, returnerer tom liste hvis fil mangler eller er
ugyldig.

### 4. Frontend (`web/profilutforsker.html`)

- Hent vertical-alignment der `horCurves` hentes i dag; lagre som `vertGrades`.
- I den interaktive lengdeprofil-SVG-en: for hvert tangent-strekk i `vertGrades`, tegn label ved
  **midt-stasjon på designlinja**:
  - x: `xOf((sta_start + sta_end) / 2)`
  - y: `yOf(designhøyde ved midt-stasjon)`, interpolert fra stasjonene; plassert **over** linja
    (liten hvit boks med lett gjennomsiktighet, slik PNG-en gjør).
  - Tekst: `+X,X %` / `–X,X %`.
- Robusthet: tom `vertGrades` ⇒ ingen labels (ingen feil). Strekk som faller utenfor synlig
  zoom-vindu hoppes over / klippes på vanlig vis.

## Formateringsvalg

- **Desimaltegn:** komma (`+2,5 %`) — norsk/R700-konvensjon. PNG-en bruker punktum i dag; den
  rettes heller senere enn å innføre punktum her.
- **Fortegn:** `–` (vises alltid for nedoverbakke), `+` for oppoverbakke. (Følger PNG-ens
  `_draw_gradient_labels`-logikk.)
- **Av/på:** alltid på. Stigning er et kjerneelement i R700-lengdeprofilen, ikke et valgfritt
  kartlag (til forskjell fra kurvaturmerkingen i 2D-kartet).

## Feilhåndtering

- Manglende `vertical_alignment.json` ⇒ endepunkt returnerer `[]` ⇒ frontend tegner ingenting.
- Senterlinje uten vertikalgeometri (f.eks. kun TIN-elevert) ⇒ tom liste ⇒ ingen labels.
- Ukjent vertikalt segment-type i IFC behandles allerede som `CONSTANTGRADIENT` i
  `_extract_vertical_segments` (eksisterende oppførsel, uendret).

## Test

- **Backend:** enhetstest for tangent-utledning fra (a) IFC `vertical_segments` med blandet
  tangent/kurve, (b) LandXML PVI-liste. Verifiser `gradient_pct`-fortegn og avrunding.
- **API:** endepunkt returnerer tom liste når fil mangler; returnerer parset liste når fil finnes.
- **Frontend:** manuell live-verifisering mot en kjent jobb (samme mønster som tidligere
  features) — sammenlign påskrift mot statisk PNG og mot forventet vegprofil.

## Filer som berøres

- `src/ifc_processor/pipeline.py` — `AlignmentMetadata`, ny tangent-bygger, skriv JSON.
- `src/api/server.py` — nytt endepunkt.
- `web/profilutforsker.html` — henting + tegning av påskrift.
- Tester under `tests/`.
