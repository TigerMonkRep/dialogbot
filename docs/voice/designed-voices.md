# Designede stemmer

En designet stemme er en dansk stemme, der ikke tilhører en bestemt person. Den er blandet af flere rigtige
oplæsere fra samme gruppe (køn, alder og region) i NST-korpusset (`alexandrainst/nst-da`, CC0-1.0, revision
`0f14ad2005e0aab8f56cf3213b7689da1faf23c2`). Dialogbot efterligner ikke enkeltpersoner fra åbne datasæt, fordi
oplæserne ikke har givet samtykke til at blive kommercielle stemmer (Røst-licensen punkt 4(b) og GDPR).

## Sådan bygges en stemme

`python -m voice_pipeline.design_voices build --catalog voice_pipeline/designed/catalog.json --nst <dir> --out <dir>`

For hver stemme i kataloget:

1. Oplæsere vælges ud fra NST's egne oplysninger om køn, alder og region, spredt over aldersspændet (typisk 8,
   mindst 4). Pr. oplæser bruges 25 klip på 2,5–9 sekunder uden overstyring.
2. Stemmen bygges af klip 0–14 fra hver oplæser:
   - stemmeaftrykket (speaker embedding) er gennemsnittet af oplæsernes aftryk;
   - klangaftrykket (x-vector) er gennemsnittet af oplæsernes;
   - prompten er lige store stykker fra hver oplæser, så ingen dominerer.

   Resultatet gemmes som en `conds.pt`-fil, som taletjenesten indlæser direkte (`method=designed_blend`).
   Filen indlæses med `torch.load(weights_only=True)`, efter at dens sha256 er tjekket mod stemmeversionen.
3. **Lighedskontrol.** En prøve af stemmen sammenlignes med klip 15–24 fra hver oplæser. Klippene er holdt ude af
   byggeriet. Stemmen må ikke ligne nogen enkelt oplæser mere, end to forskellige rigtige oplæsere i gruppen ligner
   hinanden (plus 0,03), og aldrig over 0,90. Hvis den fejler, prøves igen med flere oplæsere. API'et kører samme
   kontrol (`distinctness`) og godkender ikke en version uden den.
4. **Beskrivelse.** Den bygges kun af registrerede oplysninger og målinger: stemmeleje (median F0), tempo (tegn pr.
   sekund), antal oplæsere, regioner og aldersspænd. "Jysk" eller "københavnsk" beskriver, hvor oplæserne kommer fra.
   Om stemmen lyder regional, skal lyttere fra regionen vurdere. Indtil da står `dialect` som ukendt.
5. **Oprindelse.** `voice.json` indeholder hele oprindelseserklæringen: datasæt og revision, model og revision,
   oplæsere (id, køn, alder, region), alle brugte klip (fil, række, sha256), lighedsmålingen og checksummen for
   `conds.pt`.

## Registrering

`python -m scripts.voices_register_designed <out-dir>` gør følgende:
- uploader `conds.pt` til det private lager;
- opretter en rettighedspost for NST (status `unreviewed`);
- opretter profiler med `origin=designed` og en beskrivelse;
- opretter kladdeversioner med oprindelse og kører de automatiske kontroller.

Intet bliver godkendt automatisk. Platformstemmer kræver desuden en lyttetest (≥ 3 danske lyttere) og en rigtig
telefontest.

## Første forsøg (27/9 2026, CPU, Røst-v3)

| Stemme | Oplæsere | Stemmeleje | Nærmeste oplæser | Rigtige oplæsere indbyrdes (maks.) | Efterligning af én person (kontrol) |
|---|---|---|---|---|---|
| Jysk mand, 25–44 år | 8 (Vest-, Øst- og Nordjylland) | 120 Hz | 0,858 | 0,84 | 0,934 |
| Københavnsk kvinde, 21–34 år | 6 (Storkøbenhavn) | 229 Hz | 0,865 | 0,853 | 0,95 |

Kontrolklippene, der efterlignede én person, blev slettet efter målingen og er ikke udleveret.

## Forbehold

- Om en blandet stemme er uden for Røst-licensens forbud i punkt 4(b), skal en jurist bekræfte.
- NST er optaget ved 16 kHz. Klangen kan være lidt mere dæmpet end CoRal-stemmerne, men det betyder mindre i
  telefonen, der typisk kører 8–16 kHz.
