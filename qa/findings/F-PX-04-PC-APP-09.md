---
id: F-PX-04-PC-APP-09
scenario: PC-APP-09
reported_by: integrations-qa (PX)
severity: S2
status: needs-decision
owner_fix: ui-ux-engineer
related: []
---

## Kort
Rejser: «Book»-linket fra Travelpayouts/Aviasales bærer Dialogbots partner-marker (`marker=…`, provision), men kortet er hverken markeret «Annonce» eller `rel="sponsored"` – i modsætning til indkøbs-/husstandspartnerlinks.

## Trin til at genskabe
1. Med TRAVELPAYOUTS_TOKEN + TRAVELPAYOUTS_MARKER: søg CPH → BCN.
2. Se resultatkortet i web/src/components/privat/travel.tsx (l. ~67).

## Forventet
PC-APP-09: «"Book"-link har partner-marker og «Annonce»-markering hvis affiliate». cards.tsx/household.tsx bruger `rel="sponsored"` + «Annonce» for partnerlinks.

## Faktisk
`<a href={o.book_url} rel="noopener noreferrer">Book</a>`; disclaimeren siger kun «Du bestiller og betaler hos udbyderen – Dialogbot booker ikke» – intet om provision.

## Evidens
- Test: tests/qa/test_qa_pd_x.py::test_px_app_09_travelpayouts_link_carries_marker (grøn: markøren er der)
- Kode: web/src/components/privat/travel.tsx

## Beslutning (Fürster)
Markering af affiliate-links (markedsføringsloven) – foreslået: «Annonce · Dialogbot får provision» ved Travelpayouts-resultater og `rel="sponsored"`. Duffel-links (ingen provision) uden mærke.

## Rodårsag / Rettelse / Verifikation
