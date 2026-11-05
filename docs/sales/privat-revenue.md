# Dialogbot Privat – indtjening ud over abonnementet

Status: bygget ind i koden 6/11 2026. **Ikke juridisk gennemgået** – en advokat skal se punkt 1 og 2, før der tages
penge for leads eller partnerlinks.

## 1. Leads til virksomheder (Håndværker & tilbud, Flytning, Hus & vedligehold)

- Hver virksomhed, Dialogbot spørger om et tilbud, bliver en række i `private_business_referrals` (`asked`). Når
  brugeren vælger en, bliver den `chosen` og de andre `not_chosen`.
- Det giver salget et tal: «Dialogbot har sendt jer N kunder og M opgaver» – argumentet for, at virksomheden selv bliver
  kunde (telefonpasning) eller betaler pr. vundet opgave.
- Opkaldet til virksomheden siger altid «jeg ringer fra Dialogbot på vegne af …» (`calls.script`), og når ærindet er
  klaret, kan den faste salgslinje komme (`lead_pitch.py`, kræver `LEAD_PITCH_ENABLED` og juridisk gennemgang).
- **Rækkefølgen er Googles relevans – aldrig købt.** Skal en virksomhed kunne betale sig til en plads, skal det stå
  tydeligt ved den (markedsføringsloven og Omnibus-reglerne om betalt placering).

Forespørgsel til lead-regnskabet (salg):

```sql
select business_name, business_phone_e164, count(*) filter (where status = 'chosen') as valgt, count(*) as spurgt
from dialogbot.private_business_referrals group by 1, 2 order by valgt desc, spurgt desc;
```

## 2. Partnerlinks («Annonce»)

`PRIVAT_PARTNER_LINKS` (JSON pr. kategori: mobil, internet, el, streaming, forsikring, dyreforsikring, flyttefirma, fest,
hjem, garanti, dagligvarer, fitness). Vises i appens panel og i chatten, altid med «Annonce – Dialogbot kan få
provision, hvis du køber». Tom = intet vises. Kandidater: affiliate-netværk som Partner-ads og Adtraction (danske
mobil-, el-, forsikrings- og dagligvareselskaber).

- Madplan → indkøbsliste → «Bestil varerne hjem» (dagligvarer). **En kurv med ét klik** kræver en aftale med en
  dagligvarebutik: der findes ingen åben kurv-API i Danmark i dag. Browser-agenten kunne fylde kurven, men kun med
  butikkens accept og brugerens eget login – ikke bygget.
- Abonnementer → billigere mobil/internet/el/streaming; Flytning → el, internet, forsikring, flyttefirma;
  Kæledyr → dyreforsikring; Fitness → udstyr og fitnesscentre.

## 3. Dialogbots navn på alt, der deles

Opsigelser, reklamationer, invitationer og opgørelser over fælles udgifter slutter med
«– Sendt med Dialogbot, din personlige assistent · <adresse>/privat» (`brand.footer`). Fælles udgifter og Fest &
invitationer er gratis, så de kan sprede sig: hver gæst og hver ven ser, hvor det kom fra.
