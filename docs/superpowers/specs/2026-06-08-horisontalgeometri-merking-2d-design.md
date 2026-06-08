# Horisontalgeometri-merking (R / A) i 2D-kartet

**Dato:** 2026-06-08
**Status:** Godkjent design, klar for implementeringsplan
**Komponent:** Profilutforsker (web/profilutforsker.html)

## Bakgrunn

På R700 C-tegninger (plantegninger) er horisontalgeometrien påskrevet langs
vegmodellen: kurveradius `R=<verdi>` på sirkelbuer, klotoideparameter
`A=<verdi>` på overgangskurver, og `R=∞` (liggende åttetall) der vegen er rett.
Disse verdiene er de samme som rubrikkene i lengdeprofilen.

Profilutforskeren tegner i dag senterlinja i 2D-kartet, men uten disse
geometripåskriftene. Målet er å legge R/A-merkene oppå senterlinja i 2D-kartet,
i C-tegning-stil.

## Datagrunnlag (finnes allerede)

`horizontal_alignment.json` genereres av pipelinen
(`src/ifc_processor/pipeline.py`, ~linje 449–466) fra IFC4X3-alignmenten
(`src/ifc_processor/alignment_parser.py`) og serveres via
`GET /api/jobs/{job_id}/horizontal-alignment` (`src/api/server.py` ~345–354).
`profilutforsker.html` henter den allerede.

Hvert segment har bl.a.:

| Felt | Betydning |
|------|-----------|
| `station` | startstasjon (m) langs senterlinja |
| `length` | segmentlengde (m) |
| `direction` | retning/bæring (grader) ved start |
| `kind` | `"line"` \| `"curve"` \| `"spiral"` |
| `radius` | kurveradius R (m), kun på `curve` |
| `dir` | +1 / −1 (CCW/CW fortegnskonvensjon) |
| `A` | klotoideparameter A (m), kun på `spiral` |

JSON-en inneholder **ikke** kartkoordinater per segment. Posisjon i kartet
hentes derfor fra senterlinje-polylinjas geometri (se §2).

## Valgt tilnærming

**Frontend-only.** All endring skjer i `web/profilutforsker.html`. Ingen
backend-, pipeline- eller AGOL-endring. Virker umiddelbart på allerede
publiserte jobber, og posisjon/vinkel leses rett fra den faktiske
kartgeometrien (mest nøyaktig).

Avviste alternativer:
- **FeatureLayer + Arcade-labeling:** native dekluttering, men per-segment-
  rotasjon i Arcade er klønete og label-motoren kan droppe merker vi vil vise.
- **Backend legger koordinater + labeltekst i JSON:** renest datakontrakt, men
  krever pipeline-endring og reprosessering/republisering før eksisterende
  jobber får merkene.

## Design

### 1. Labeltekst

For hvert segment i `horizontal_alignment.json`:

- `kind === "curve"` → `R=<radius>` der radius avrundes til nærmeste meter.
- `kind === "spiral"` → `A=<A>` der A avrundes til nærmeste meter.
- `kind === "line"` → `R=∞` (Unicode U+221E).

### 2. Plassering og rotasjon

For hvert segment:

1. **Mid-stasjon** = `station + length/2`.
2. **Posisjon:** finn punktet på senterlinje-polylinja ved mid-stasjon ved å gå
   langs polylinjas vertekser og akkumulere 2D-lengde i kartkoordinater, så
   interpolere lineært i det verteks-intervallet stasjonen faller i.
   Polylinje-geometrien hentes med én `clLayer.queryFeatures` (returnGeometry)
   etter at laget er lastet; geometrien caches.
3. **Rotasjonsvinkel:** tangenten til polylinja i punktet (vektoren mellom de to
   nærmeste verteksene) → `angle = atan2`-basert vinkel konvertert til
   `TextSymbol.angle` (grader, klokkeretning, y-akse flippet fordi kart-y peker
   opp). Normaliseres til [−90°, 90°] (legg til 180° ved behov) så teksten aldri
   står opp-ned.
4. **Offset:** liten loddrett offset (noen få punkt) så teksten ligger like over
   linja, ikke oppå den.

Tangenten fra polylinjas vertekser brukes fremfor `direction`-feltet fordi den
er robust i projiserte kartkoordinater (EPSG:25833) uavhengig av IFC-ens
bæringskonvensjon.

### 3. Rendering og av/på-knapp

- Eget `GraphicsLayer` (`geomLabelLayer`) med ett `TextSymbol`-`Graphic` per
  segment som skal merkes.
- Av/på-knapp i samme stil som de eksisterende kartkontrollene; styrer
  `geomLabelLayer.visible`. **Standard: av** (unngå rot ved oppstart).
- Stil (R700-aktig, lesbar i farge og s/h): liten font (~10–11 pt), mørk tekst
  med tynn hvit halo (`haloColor`/`haloSize`) så den er lesbar mot både gult
  vegareal og bakgrunnskart.

### 4. Zoom-oppførsel

- Merkene får `minScale` (f.eks. synlig først når zoomet inn nærmere enn
  ~1:5000) så laget ikke blir tekstgrøt på oversiktsnivå. Konkret terskel
  finjusteres mot ekte data.

### 5. Grensetilfeller

- Segmenter uten `radius`/`A` (manglende data) på henholdsvis `curve`/`spiral`
  hoppes over.
- Veldig korte segmenter (`length` < terskel, f.eks. 3 m) merkes ikke for å
  unngå overlapp.
- Hvis `clLayer`-geometrien ikke er tilgjengelig (query feiler / tom), logges
  det og `geomLabelLayer` blir tomt — resten av kartet påvirkes ikke.

## Avgrensning (YAGNI)

- Ingen dekluttering/kollisjonshåndtering utover `minScale` + minimum
  segmentlengde + av/på-knappen.
- Ingen visning av A→R-overgang eller fortegn/retning i teksten; kun R og A som
  valgt.
- Ingen 3D-ekvivalent i denne omgang (kun 2D-kartet).
- Ingen backend-/AGOL-endring.

## Berørte filer

- `web/profilutforsker.html` — eneste fil som endres (label-bygging, GraphicsLayer,
  av/på-knapp, posisjon-/rotasjonshjelpefunksjoner).

## Suksesskriterier

1. Med en publisert jobb med kurvet senterlinje vises `R=<verdi>` på sirkelbuer,
   `A=<verdi>` på klotoider og `R=∞` på rette strekk når geometri-laget er på.
2. Tekstene følger vegens retning og står aldri opp-ned.
3. Av/på-knappen skjuler/viser hele laget; standard av.
4. På oversiktsnivå (utzoomet forbi terskel) vises ikke merkene.
5. Ingen regresjon på eksisterende senterlinje-/stasjonsvisning.
