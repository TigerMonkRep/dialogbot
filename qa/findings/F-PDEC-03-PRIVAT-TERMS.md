---
id: F-PDEC-03-PRIVAT-TERMS
scenario: PC-SUB / PC-CALL / juridisk (Privat)
reported_by: qa-lead (beslutning Fürster 2026-11-11 «ja» til egne Privat-vilkår)
severity: S1
status: fixed
owner_fix: fix-engineer #11
related: [F-PDEC-01-PC-CALL-EXTRA]
---

## Kort
Dialogbot Privat (forbrugere) havde ingen egne vilkår: landingens «Handelsbetingelser» pegede på Erhvervs `/vilkaar`
(B2B, priser ekskl. moms, Retten i Aarhus, ingen fortrydelsesret), og Stripe Checkout for plan/optankning nævnte
ingen vilkår.

> **UDKAST.** Teksten er skrevet af fix-engineer ud fra Fürsters punkter og koden, ikke af en jurist. Den bør
> gennemlæses af en jurist (forbrugeraftaleloven, købeloven/digitalt indhold, markedsføringsloven, GDPR) før
> lancering. Siden er teknisk klar, men bør ikke annonceres som endelig før det er sket.

## Trin til at genskabe (før rettelsen, 5ca402c)
1. Åbn `/privat`, klik «Handelsbetingelser» i footeren → `/vilkaar` (Erhverv, B2B-tekst).
2. `grep privatTerms web/src/i18n/messages/*/legal.json` → intet.
3. Ny test `tests/test_prices.py::test_the_privat_terms_exist_in_every_language_with_every_price_from_prices_json`
   fejler på 5ca402c (`KeyError: 'privatTerms'`).

## Rodårsag (fix-engineer)
Ikke en kodefejl: der var aldrig skrevet forbrugervilkår. Privat genbrugte Erhvervs side via et hardkodet
`href="/vilkaar"` i `web/src/app/privat/page.tsx`. Accept af vilkår gemmes ikke nogen steder for Privat (eller for
Erhvervs tilmelding); kun salgstilbud har `terms_version`.

## Rettelse
- Tekst: `web/src/i18n/messages/{da,en,de,es,fr,it,no,sv}/legal.json` → `privatTerms` (`version: "1"`,
  `updated: "Version 1 · gældende fra 11. november 2026."`), 16 punkter + Kontakt, samme blokformat som Erhverv v2.
  Alle beløb er tokens: `{pBasis} {pPlus} {pFamilie}` (+ `Year`/`YearTotal`), `{pXAnswered} {pXVoicemail} {pXNoAnswer}
  {pXMinute} {pXMax}`, `{pTopup1-3}`, `{pWelcome} {pReferral} {pExtraTask}`, `{pTrialDays}`. Tiltale som resten af
  Privat: du / you / du / vous / tú / tu / du / du. Produktnavne som i appen («Ring for mig» = Call for me, Ruf für
  mich an …; Opkaldssaldo = Call balance, Anrufguthaben …; «Annonce» = Advertisement, Anzeige …).
- Side: `web/src/app/privat/vilkaar/page.tsx` (ny); `web/src/components/legal-page.tsx` (`audience="privat"`:
  `data-theme="privat"`, logo → `/privat`, «Vilkår» → `/privat/vilkaar`); `web/src/app/sitemap.ts`.
- Links: Privat-footer (`web/src/app/privat/page.tsx`), planvælgeren på Konto (`components/privat/account.tsx`),
  prøveperiode-arket og optanknings-arket (`components/privat/sheets.tsx`) → `/privat/vilkaar` (label
  `privat.landing.footer.terms`, ingen nye nøgler).
- Stripe Checkout: `app/modules/privat/market.py` (`TERMS_VERSION = "1"`, `TERMS_PATH`, `terms_note()`),
  `subscriptions.py` og `payments.py`: `metadata.terms_version` på plan (session + subscription_data) og optankning
  (session + payment_intent_data), og en linje «Handelsbetingelser for Dialogbot Privat (version 1): <url>» over
  betal-knappen (dansk for da, engelsk ellers – som den eksisterende prøveperiode-note). Det er den eneste «accept»,
  der gemmes: versionen står i Stripe-metadata; ingen DB-kolonne, ingen migration.
- Tests: `tests/test_prices.py` (ny test, fejler før/består efter), tilpasset eksakt metadata i
  `tests/test_privat_subscription.py::test_checkout_payload` (+ link-tjek), `tests/test_privat.py::test_payment_signal_twice`
  (+ link-tjek), `tests/qa/test_qa_pd_billing.py::test_pc_sub_01_…`.
- Kørt: test_prices, test_privat, test_privat_subscription, test_privat_apps_state, test_discount_codes,
  test_stripe_billing, test_markets, qa/test_qa_billing_x08, qa/test_qa_pd_billing, qa/test_qa_pd_sec på db qa_fix11 –
  grønne bortset fra 10 kendte røde QA-fund (5 i pd_billing, 5 i pd_sec), identiske på 5ca402c. `tsc --noEmit` og
  `i18n:check` grønne. ruff: kun 4 eksisterende fejl i tests/qa/test_qa_pd_billing.py (uændret).
- Commit: 7fb3b80

## Beslutninger (Fürster 2026-11-11, via qa-lead)
- **Pkt. 1 – saldo:** Ubrugt Opkaldssaldo refunderes **ikke** ved opsigelse eller sletning – hverken bonusser eller
  egne indbetalinger. Den lovpligtige fortrydelsesret bevares: inden for 14 dage efter en optankning kan den ubrugte
  del af den optankning refunderes (punkt 7). Saldoen udløber ikke, så længe kontoen findes. Rettet i
  `privatTerms.sections[7].body[5]` (8. Opkaldssaldo) på alle 8 sprog (sætningen om at skrive til info@ før sletning
  er fjernet); `tests/test_prices.py` låser det (fejler på teksten før, består efter).
- **Pkt. 5 – ODR:** Henvisningen til Forbrugerklagenævnet og Forbrugereuropa i stedet for ODR er **godkendt**.
- **Pkt. 6, 8, 10/11 – 18 år, dansk ret med forbrugerens hjemlandsbeskyttelse, 30 dages varsel:** **godkendt**.
- Commit: «fix(privat-terms): F-PDEC-03 ubrugt saldo refunderes ikke …» (fix-engineer #12, oven på merge 823f5e2).
- Stadig åbent: jurist-gennemlæsning (UDKAST-noten ovenfor gælder fortsat); punkterne nedenfor uden beslutning.

## Valg truffet af fix-engineer – Fürster/jurist skal bekræfte
1. ~~Ubrugt saldo refunderes ved opsigelse/sletning efter anmodning~~ – **afgjort 2026-11-11: refunderes ikke**
   (se Beslutninger). Kun fortrydelsesretten (14 dage efter en optankning, den ubrugte del) giver refusion.
2. **Fortrydelsesret, plan uden prøveperiode** (kortet har haft prøveperiode før): fuld refusion ved fortrydelse inden
   14 dage – vi trækker IKKE forholdsmæssigt for brugte dage (loven tillader det kun, hvis kunden udtrykkeligt har bedt
   om levering i fortrydelsesperioden, hvilket Checkout ikke indhenter). Følger «uden at det koster noget».
3. **Fortrydelse af optankning:** den ubrugte del refunderes; brugte, godkendte opkald er betalt.
4. **Prøveperiode og fortrydelsesfrist** løber fra samme dag; trækkes en betaling alligevel inden fristen udløber
   (prøveperioden kan slutte få timer før), refunderes alt.
5. **EU's ODR-platform er IKKE nævnt.** EU-forordningen om ODR blev ophævet, og platformen lukkede 20. juli 2025, så et
   link dertil ville være dødt. I stedet: Forbrugerklagenævnet (Nævnenes Hus, Toldboden 2, 8800 Viborg, via forbrug.dk)
   og Forbrugereuropa for forbrugere i andre EU-lande. **Godkendt af Fürster 2026-11-11.**
6. **Alder:** man skal være 18 år for at købe en plan eller fylde saldoen op (gratis konto/husstandsmedlem uden krav). **Godkendt 2026-11-11.**
7. **Sprog:** den danske version gælder ved uoverensstemmelse.
8. **Lovvalg/værneting:** dansk ret, men forbrugeren beholder sit hjemlands ufravigelige beskyttelse og kan bruge de
   domstole, loven giver ret til (ingen fast værneting som Erhvervs «Retten i Aarhus»). **Godkendt 2026-11-11.**
9. **Ansvar:** ingen beløbsgrænse (Erhvervs «3 måneders betaling» er ikke overført); kun undtagelser for tredjeparter
   (virksomheden der ringes til, teleselskaber/cloud) og force majeure, «intet begrænser dine rettigheder som forbruger».
10. **Vores opsigelse:** 30 dages varsel med forholdsmæssig refusion af forudbetalt periode; grov misbrug → uden varsel. **30 dages varsel godkendt 2026-11-11.**
11. **Ændringer:** 30 dages varsel på e-mail og i appen; også prisændringer; kunden kan opsige før ikrafttræden. **Godkendt 2026-11-11.**
12. **Mislykket betaling:** «lykkes den ikke, efter at Stripe har prøvet igen, ophører planen» (matcher
    past_due → canceled i koden).
13. **Ubrugte planopkald overføres ikke** til næste måned (kalendermåned); ubesvarede/fejlede tæller ikke.
14. **Antal opkald og personer pr. plan** står ikke i vilkårene (henvisning til prissiden/appen), fordi der ikke findes
    tokens for dem i prices.json, og tal ikke må hardkodes.
15. **Hjemmesidebooking under fair use** – tallet nævnes ikke; vi giver besked før en begrænsning.
    **OBS – kode og vilkår er uenige:** browser-workeren trækker i dag 2,90 kr. fra saldoen pr. booking (F-PDEC-01 pkt. 7).
    Vilkårene siger «med i alle planer». Koden skal rettes (eller vilkårene), før lancering → needs-decision/ny opgave.
16. **Annoncer/affiliate:** markeres «Annonce»; vi lover ikke, at prisen er den samme uden linket.
17. **Microsoft:** «vi sletter nøglerne hos os; du kan selv fjerne Dialogbot under din Microsoft-konto» (Microsoft har
    ingen revoke-endpoint).
18. **Dato:** «gældende fra 11. november 2026» – ret datoen (og evt. versionsnummer) til lanceringsdagen efter
    juristens gennemlæsning. Ændres versionen, skal `market.TERMS_VERSION` følge med (testen tjekker det).
19. **Stripe-noten** er dansk for da og engelsk for de øvrige sprog (som den eksisterende prøveperiode-note).

## Ikke gjort
- Accept gemmes ikke i vores DB (kun `terms_version` i Stripe-metadata). En kolonne på `private_subscriptions` kræver
  migration og er ikke bedt om.
- Privatlivspolitikkens Privat-afsnit er ikke gennemgået mod vilkårene ud over de punkter, der er citeret (90 dage,
  7 dage, Google/Microsoft).
- Ingen browser-/e2e-kørsel (ingen stak/build efter ordre). Siden er ikke set visuelt.

## Verifikation (udfyldes af verifier)
- Gentest:
- Fejler testen uden rettelsen? ja/nej
- Naboscenarier kørt:
- Dom: closed | reopened
