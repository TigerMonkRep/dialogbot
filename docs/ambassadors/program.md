# Ambassadørprogrammet

Ambassadører anbefaler Dialogbot og tjener på de kunder, de skaffer. Mange af dem er unge på 17–20 år uden CVR, og derfor er ordningen bygget til privatpersoner med B-indkomst og forældregodkendelse. Virksomheder med CVR kan også være med.

Koden ligger i `app/modules/ambassadors/`. Tests ligger i `tests/test_ambassadors.py` og i E2E-rejse 26.

## Vilkår (standard – kan ændres pr. ambassadør)

| | |
|---|---|
| Startbonus | **500 kr.**, når en henvist kunde har betalt sin første faktura (én gang pr. kunde) |
| Løbende andel | **10 %** af kundens betalte fakturaer (netto, ekskl. moms) i **12 måneder** fra første betalte måned |
| Hold | Beløb er "optjent" i **30 dage** efter betaling og bliver derefter "klar til udbetaling" |
| Udbetaling | Fra **500 kr.** til ambassadørens bankkonto |
| Kunderabat | **50 %** på kundens første fakturerede måned (linje `ambassador_discount` i afregningen) |
| Alder | Mindst 15 år. Under 18 kræver det en forælders godkendelse, før der udbetales |

Der optjenes kun penge på fakturaer, der er **betalt**. En refusion, en kreditnota eller en annullering trækker det tilsvarende beløb tilbage:

- Er beløbet ikke udbetalt endnu, bliver posten nedskrevet eller annulleret.
- Er beløbet allerede udbetalt, oprettes en negativ post ("Modregning"), som trækkes fra næste udbetaling.
- Startbonussen trækkes kun tilbage ved fuld refusion.

## Sådan finder vi ud af, hvem der skaffede kunden

1. Ambassadøren deler `https://<frontend>/a/{slug}`. Linket tæller besøget, sætter en førsteparts-cookie `db_ref` (90 dage) og åbner forsiden med ambassadørens velkomst. Et link fra en godkendt ambassadør virker også som adgang forbi preview-låsen.
2. Når kunden opretter sit arbejdsrum, sendes `referral_link` fra cookien med. Kunden kan også skrive en `referral_code`.
3. **Koden vinder over linket.** Man kan ikke henvise sig selv (ambassadørens egen bruger ignoreres). Tilknytningen sker én gang.
4. Har kunden glemt koden, kan ejeren tilføje den under **Fakturering** i de første 30 dage og før første faktura.
5. En operatør kan flytte eller fjerne en kunde. Det kræver en begrundelse og bliver logget.

## Skat og persondata

- **Privat (uden CVR):** Bonus er B-indkomst. Dialogbot trækker ikke skat. Udbetalt B-indkomst skal indberettes i eIndkomst senest 20. januar året efter, med ambassadørens CPR. Filen hentes under Operatør → Ambassadører → "B-indkomst til Skattestyrelsen" (CSV med navn, CPR og beløb). Hver hentning bliver logget.
- **Virksomhed (CVR):** Ambassadøren får et afregningsbilag. Er virksomheden momsregistreret, lægges 25 % moms oven i overførslen.
- CPR og bankoplysninger krypteres med AES-256-GCM med `CREDENTIALS_KEY` (samme nøgle som integrationerne). De vises kun for en operatør, der trykker "Vis oplysninger", og hver visning bliver logget.
- Ambassadøren ser kun kundens firmanavn, status og sin egen bonus. Ambassadøren ser aldrig samtaler, henvendelser eller kontaktdata.
- **Bør bekræftes af en revisor:** at B-indkomst er den rigtige indkomsttype (honorar) og ikke løn. Det gælder, så længe ambassadøren selv bestemmer hvornår og hvordan.

## Markedsføringsregler (quiz ved tilmelding)

Ambassadøren skal svare rigtigt på fire spørgsmål, før tilmeldingen accepteres (`RULES_VERSION` i `service.py`):

- ingen uopfordrede reklamemails eller -sms'er, heller ikke til virksomheder;
- reklame skal være markeret som reklame, og det skal fremgå, at ambassadøren får bonus;
- ingen AI- eller automatiske opkald uden forudgående samtykke (markedsføringsloven § 10);
- ingen reklame til virksomheder, der er reklamebeskyttet i CVR.

De færdige tekster på ambassadørens side er markeret som reklame.

## Salgsmateriale

Ligger i `web/public/materiale/` og er offentligt på `/materiale/…` (uden for preview-låsen). Ambassadøren finder links under **Del og tekster**.

| Fil | Indhold |
|---|---|
| `salgsmateriale.html` | Brochure, 6 A4-sider: funktioner, priser, kom i gang. Markeret som reklame. Personlig udgave med `?navn=…&link=…&kode=…&rabat=50` (navn, link og kode på forsiden og i oplysningen om bonus). |
| `dialogbot-salgsmateriale.pdf` | Samme brochure uden navn. |
| `opsaetningsmanual.html` / `dialogbot-opsaetningsmanual.pdf` | Byggevejledning i Lego-stil, 12 sider A4 på langs: 18 trin i 5 "poser", der følger opsætningsguidens faser. |

Ændrer I priser, trin eller vilkår, så ret HTML-filerne og lav PDF'erne igen (Chromium/Playwright: `page.pdf({ format: "A4", printBackground: true, preferCSSPageSize: true })`, manualen med en viewport på mindst 1200 px).

## Administration (for Dialogbot)

Siden findes under **Kontomenuen → "Operatør: ambassadører"** (`/app/operator/ambassadors`). Den kræver `is_platform_operator`, som gives med `python -m scripts.grant_operator <email>`.

1. **Godkend nye.** Listen viser som standard dem, der venter. Åbn en ambassadør og tjek alder, forælder, motivation og hilsen. Tryk *Godkend* eller *Afvis* (med en note). Ambassadøren får besked på mail. Linket virker først, når ambassadøren er godkendt.
2. **Sæt på pause.** Hvis reglerne brydes, sættes ambassadøren på pause med en begrundelse. Linket holder op med at virke, men den bonus, der allerede er optjent, bliver stående. Ambassadøren kan genaktiveres.
3. **Særaftaler.** Bonus, andel og antal måneder kan ændres pr. ambassadør. Ændringen gælder fakturaer, der betales fra nu af.
4. **Udbetaling (fx den 1. i måneden):**
   1. Tryk *Opret udbetalinger*. Der oprettes én udbetaling pr. ambassadør med mindst 500 kr. klar. Ambassadører, der mangler noget (bank, CPR, forældregodkendelse), springes over, og årsagen vises.
   2. Åbn ambassadøren, tryk *Vis oplysninger*, og overfør beløbet i netbanken.
   3. Skriv bankens reference, og tryk *Markér betalt*. Ambassadøren får en mail og et afregningsbilag på sin side.
   4. Er noget forkert, så *Annullér*. Posterne bliver klar til næste kørsel igen.
5. **Januar:** hent B-indkomst-CSV'en for året før, og indberet den i eIndkomst.

Arbejdsprocessen frigiver automatisk beløb efter de 30 dage (`release_held`). Bonus bliver optjent, når Stripe-webhooken `invoice.paid` kommer. `charge.refunded`, `credit_note.created` og `invoice.voided` trækker beløb tilbage.

## Ambassadørens egne sider

| Side | Indhold |
|---|---|
| `/ambassador/bliv` | Programmet med regneeksempel, regler og tilmelding (kræver konto og bekræftet e-mail). Tilmelding er undtaget fra preview-låsen. |
| `/ambassador` | Overblik (saldi, link, kode, besøg), kunder, kontoudtog, udbetalinger, oplysninger (CPR og bank), færdige tekster. |
| `/ambassador/udbetalinger/{id}` | Afregningsbilag. |
| `/ambassador/foraelder?token=…` | Forælderen godkender aftalen fra linket i mailen (ingen konto nødvendig). |

## Næste version (fase 2–3)

- QR-kode og fysisk ambassadørkort med NFC.
- Personlig side med foto.
- Automatisk udbetaling (fx Stripe Connect, når ambassadøren er fyldt 18).
- Bonusstige.
- Partner-niveau til bureauer og revisorer.
