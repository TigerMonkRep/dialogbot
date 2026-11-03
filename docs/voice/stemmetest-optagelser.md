# Stemmetest: optagebrief

Hvad der skal indtales for at gøre de resterende målinger ægte. Hver sætning optages af et **menneske** (ikke syntetisk tale), som **mono 16-bit WAV**, helst på en rigtig telefonlinje (8 kHz) og mindst nogle af dem på 16 kHz. Gem filen som `<ID>.wav` i `tests/fixtures/stemmetest/audio/` (eller i mappen `STEMMETEST_AUDIO_DIR`). Så skifter casen fra *mangler optagelse* til *klar* på Stemmetest-siden – ingen kodeændring.

- Sig ordene, som der står (referencen er ordene, der **siges**). Rettelser ("fire … nej, seks") siges naturligt med en kort pause.
- Brug kun kontrollerede testdata: testnummeret `20 30 40 50`/`12 34 56 78` og mailen `test@eksempel.dk`. Ingen rigtige personers oplysninger.
- `tuning`-cases bruges til at vælge indstillinger; `final`-cases bruges kun til den afsluttende måling. Bland dem ikke.
- Optag dialekter, fart, lav stemme og støj, hvor feltet *variation* eller *støj* siger det. Mindst tre forskellige talere, hvis muligt.
- Samtalescenarierne (SC01–SC10) kan ikke optages på forhånd: et menneske skal svare på agentens spørgsmål, mens agenten kører.

| ID | Split | Gruppe | Sig | Bemærkning |
|---|---|---|---|---|
| K01 | final | steder | Hej, jeg vil gerne booke til Gastro Hall. |  |
| K02 | final | steder | Vi skal til Racehall i Aarhus på lørdag. |  |
| K03 | tuning | steder | Jeg ringer fra Dialogbot i Viby. |  |
| K04 | final | steder | Jeg bor i Højbjerg lige uden for Aarhus. |  |
| K05 | final | steder | Er det Racehall eller Gastro Hall, der har åbent søndag? |  |
| K06 | tuning | navne | Mit navn er Pernille Kjærgaard. |  |
| K07 | final | navne | Mit navn er André Thorsen. |  |
| K08 | final | navne | Mit navn er Søren Brøndum Mikkelsen. |  |
| K09 | tuning | navne | Mit navn er Jytte Ørum. |  |
| K10 | final | navne | Mit navn er Mads Fogh Nygaard. |  |
| K11 | final | navne | Mit navn er Gitte Skovgaard-Poulsen. |  |
| K12 | tuning | navne | Det er Birgitte med to t'er, Hvidbjerg. |  |
| K13 | final | rettelse_antal | Vi bliver fire … nej, seks personer. |  |
| K14 | final | rettelse_antal | Vi er fem, nej vent, syv personer. |  |
| K15 | tuning | rettelse_antal | Kan vi være otte, nej, ti personer? |  |
| K16 | final | dato_tid | På fredag klokken halv syv. |  |
| K17 | final | dato_tid | Lørdag den ottende november klokken fjorten. |  |
| K18 | tuning | dato_tid | I morgen klokken kvart over fem. |  |
| K19 | final | dato_tid | Mandag klokken otte om aftenen. |  |
| K20 | final | telefon | Mit nummer er tyve, tredive, fyrre, halvtreds. | langsomt med pauser |
| K21 | tuning | telefon | Nummeret er tolv, fireogtredive, seksoghalvtreds, otteoghalvfjerds. | langsomt med pauser |
| K22 | final | telefon | Min mail er test snabel-a eksempel punktum d k. | langsomt med pauser |
| K23 | final | taenkepause | Vi skal være, øh, lad mig se, syv personer. | 1-2 s midt i sætningen |
| K24 | tuning | taenkepause | Jeg vil gerne booke, øhm, ja, en bane til, øh, fredag. | 1-2 s midt i sætningen |
| K25 | final | variation | Kan jeg få booket en bane til seks personer på lørdag klokken seksten. | hurtig tale |
| K26 | final | variation | Jeg skal bruge et bord til fire personer på torsdag. | lav stemme, ca. 20 cm fra mikrofon |
| K27 | tuning | variation | Kan jeg få en tid i morgen klokken ti. | fynsk/jysk/sjællandsk/sønderjysk: indtal samme sætning hver for sig |
| K28 | final | variation | Jeg vil gerne bestille et bord på søndag klokken atten. | bornholmsk eller vestjysk |
| K29 | final | stoej | Jeg vil gerne have et bord til fem personer klokken nitten. | restaurantstøj i baggrunden |
| K30 | tuning | stoej | Vi er seks personer og kommer på lørdag. | en anden person taler i baggrunden (referencen er KUN kundens ord) |
| K31 | final | bekraeftelse | Ja. | må ikke afbryde agenten |
| K32 | final | bekraeftelse | Mhm. | må ikke afbryde agenten |
| K33 | tuning | bekraeftelse | Okay. | må ikke afbryde agenten |
| K34 | final | afbrydelse | Vent lige, det var ikke det, jeg mente. | skal afbryde agenten |
| K35 | final | afbrydelse | Nej nej, stop, jeg skulle bruge fredag. | skal afbryde agenten |
| K36 | tuning | rettelse_booking | Jeg vil gerne flytte min booking fra fredag til lørdag klokken seksten. |  |
| K37 | final | tavshed | (8 sekunders tavshed) | 8 sekunders tavshed (stuestøj); referencen er tom; tester at intet opfindes |

## Samtalescenarier (levende)

| ID | Scenarie | Kunden siger | Forventet handling |
|---|---|---|---|
| SC01 | Almindelig booking | Jeg vil gerne booke en bane til seks personer på lørdag klokken seksten. / Mit navn er Pernille Kjærgaard. / Ja, det er rigtigt. | booking_oprettet_én_gang |
| SC02 | Rettelse midt i bookingen | Vi bliver fire … nej, seks personer. / Fredag. Nej, lørdag. / Ja. | booking_oprettet_med_seks_og_lørdag |
| SC03 | Tvetydigt tidspunkt | På fredag klokken halv syv. / (svar på agentens afklaring) Den ottende, om aftenen. | agenten_afklarer_dato_og_klokkeslæt_før_booking |
| SC04 | Kunden tænker højt | Vi skal være, øh, lad mig se, ... syv personer, tror jeg. / Ja, syv. | agenten_venter_og_afbryder_ikke |
| SC05 | Baggrundssnak | (en anden taler i rummet) Jeg vil gerne have et bord på torsdag. / Til fire. | agenten_reagerer_kun_på_kunden |
| SC06 | Reel afbrydelse | (mens agenten forklarer priser) Vent lige, det var ikke det, jeg mente. | agenten_tier_inden_for_målt_tid_og_lytter |
| SC07 | Korte bekræftelser | (under agentens forklaring) Ja. … Mhm. … Okay. | agenten_afbrydes_ikke |
| SC08 | Kalenderen svarer ikke | Jeg vil gerne booke fredag klokken atten til fire. | timeout_undersøges_før_gentagelse_ingen_dobbeltbooking (fejl: kalender-timeout (testtilstand)) |
| SC09 | Tavshed og afbrudt netværk | (ingen tale i 8 s) / (forbindelsen afbrydes midt i en sætning) | graciøs_afslutning_ingen_booking_ingen_dobbelt_svar (fejl: netværksafbrud) |
| SC10 | Rettelse af tidligere aftalt booking | Jeg vil gerne flytte min booking fra fredag til lørdag klokken seksten. | eksisterende_booking_ændres_ikke_annulleres_ikke_ubegrundet |
