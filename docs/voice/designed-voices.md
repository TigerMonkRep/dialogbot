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

## Katalog v1 (27/9 2026, CPU, Røst-v3)

- 21 af 22 stemmer bestod lighedskontrollen.
- `designet-kvinde-oerne-55-90` fejlede og er ikke skrevet. Den lå på 0,917–0,921 mod grænsen 0,90 ved 8, 10 og 12 oplæsere.
- Beskrivelserne står i hver stemmes `voice.json`.
- Dialekten er ikke lyttevurderet.

| Stemme | Klang | Leje | Tempo (tegn/s) | Nærmeste oplæser / grænse |
|---|---|---|---|---|
| Mand · Fyn · 35–54 år | mellemdyb stemme, jævnt tempo | 108 Hz | 13.4 | 0.826 / 0.9 |
| Mand · Jylland · 55+ år | dyb stemme, jævnt tempo | 96 Hz | 13.6 | 0.856 / 0.9 |
| Mand · Nordjylland · 18–34 år | mellemdyb stemme, hurtigt tempo | 125 Hz | 15.7 | 0.855 / 0.9 |
| Mand · Storkøbenhavn · 18–34 år | mellemdyb stemme, hurtigt tempo | 115 Hz | 18.1 | 0.858 / 0.9 |
| Mand · Storkøbenhavn · 35–54 år | lys stemme, hurtigt tempo | 135 Hz | 15.2 | 0.877 / 0.881 |
| Mand · Sønderjylland · 18–34 år | mellemdyb stemme, hurtigt tempo | 123 Hz | 16.0 | 0.795 / 0.9 |
| Mand · Vest- og Sydsjælland · 35–54 år | mellemdyb stemme, jævnt tempo | 108 Hz | 13.9 | 0.869 / 0.887 |
| Mand · Vestjylland · 35–54 år | dyb stemme, jævnt tempo | 97 Hz | 14.3 | 0.883 / 0.9 |
| Mand · Øerne · 55+ år | lys stemme, hurtigt tempo | 130 Hz | 16.8 | 0.835 / 0.876 |
| Mand · Østjylland · 18–34 år | mellemdyb stemme, hurtigt tempo | 111 Hz | 17.4 | 0.848 / 0.896 |
| Mand · Østjylland · 35–54 år | lys stemme, hurtigt tempo | 136 Hz | 16.3 | 0.87 / 0.87 |
| Kvinde · Fyn · 35–54 år | mellemlys stemme, jævnt tempo | 208 Hz | 14.2 | 0.867 / 0.9 |
| Kvinde · Jylland · 55+ år | mellemlys stemme, jævnt tempo | 214 Hz | 13.8 | 0.872 / 0.9 |
| Kvinde · Nordjylland · 18–34 år | lys stemme, hurtigt tempo | 227 Hz | 17.3 | 0.831 / 0.9 |
| Kvinde · Storkøbenhavn · 18–34 år | mellemlys stemme, hurtigt tempo | 205 Hz | 16.2 | 0.89 / 0.9 |
| Kvinde · Storkøbenhavn · 35–54 år | lys stemme, hurtigt tempo | 219 Hz | 15.9 | 0.874 / 0.9 |
| Kvinde · Sønderjylland · 18–34 år | lys stemme, hurtigt tempo | 223 Hz | 15.0 | 0.881 / 0.9 |
| Kvinde · Vest- og Sydsjælland · 35–54 år | lys stemme, jævnt tempo | 226 Hz | 14.0 | 0.884 / 0.9 |
| Kvinde · Vestjylland · 35–54 år | mellemlys stemme, hurtigt tempo | 194 Hz | 15.7 | 0.862 / 0.891 |
| Kvinde · Østjylland · 18–34 år | lys stemme, hurtigt tempo | 220 Hz | 16.4 | 0.884 / 0.9 |
| Kvinde · Østjylland · 35–54 år | mellemlys stemme, hurtigt tempo | 213 Hz | 16.4 | 0.881 / 0.9 |

Lyd, `conds.pt` og `voice.json` ligger uden for Git. Stemmerne registreres som kladder med `scripts.voices_register_designed`, når taletjenesten og det private lager er i drift.

## Forbehold

- Om en blandet stemme er uden for Røst-licensens forbud i punkt 4(b), skal en jurist bekræfte.
- NST er optaget ved 16 kHz. Klangen kan være lidt mere dæmpet end CoRal-stemmerne, men det betyder mindre i
  telefonen, der typisk kører 8–16 kHz.
