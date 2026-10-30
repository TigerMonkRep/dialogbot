# Udkast: afsnit til /privatliv om Dialogbots eget salg

> **Status: UDKAST – skal godkendes af ejeren (og gerne en jurist), før det offentliggøres.** Teksten beskriver,
> hvad koden gør i dag (fase 1–4 af `docs/sales/intern-salgskanal.md`). Frister og lager følger miljøvariablerne
> `SALES_RETENTION_*` og `SALES_RECORDING_STORAGE`; ret tallene her, hvis de ændres.

## Når Dialogbot selv kontakter virksomheder

**Hvem er dataansvarlig?** Dialogbot (CVR-nr. 25632710, Abildgade 18, 8200 Aarhus) er dataansvarlig for de
oplysninger, vi bruger, når vi selv finder og kontakter virksomheder, der kan have gavn af Dialogbot. Det er adskilt
fra den behandling, vi foretager som databehandler for vores kunder.

**Hvilke oplysninger og hvorfra?**
- Offentligt tilgængelige virksomhedsoplysninger fra Google Maps (navn, adresse, branche, hjemmeside, hovednummer,
  åbningstider) og fra virksomhedens egen hjemmeside (ydelser, kundetyper, bookingsystem, kontaktoplysninger). Vi
  gemmer kilde og tidspunkt for hver oplysning. Oplysninger fra Google gemmer vi højst 30 dage, medmindre de hentes igen.
- CVR-oplysninger (navn, status, reklamebeskyttelse), når vi har adgang til CVR-registret.
- Navn, rolle, telefonnummer og e-mail på den kontaktperson, der har bedt om at blive kontaktet eller har givet samtykke,
  samt teksten de sagde ja til, og hvornår.
- Ved et opkald: tidspunkt, varighed, en skriftlig udskrift (transskription) og en kort opsummering af samtalen, og –
  kun hvis det er slået til og oplyst i starten af samtalen – en lydoptagelse.

**Formål og grundlag.** At tilbyde Dialogbot til virksomheder, hvor det er relevant (legitim interesse, GDPR art. 6,
stk. 1, litra f). Vi ringer kun med vores AI-assistent til personer, der forinden har bedt om det eller givet samtykke
(markedsføringslovens § 10, stk. 1). Vi kontakter ikke reklamebeskyttede virksomheder eller numre, der har frabedt sig
henvendelser.

**Hvem ser oplysningerne?** Kun Dialogbots egne medarbejdere med adgang til salgsværktøjet. Vores leverandører behandler
oplysninger på vores vegne: Google (virksomhedssøgning), Vapi (telefoni og transskription), Anthropic (AI-analyse af
hjemmesider og samtaler), Supabase (database og evt. lydlager i EU), Resend (e-mail) og Twilio (SMS).

**Hvor længe?** Transskriptioner slettes (anonymiseres) efter 90 dage, lydoptagelser efter 30 dage, og opsummeringer
efter 365 dage. Spærringer ("ring ikke igen") gemmes, så længe de skal respekteres. Bliver virksomheden kunde, gælder
kundeaftalen.

**Dine rettigheder.** Du kan få indsigt i, hvad vi har om dig eller din virksomhed, få det rettet eller slettet, og gøre
indsigelse mod at blive kontaktet. Skriv til os – vi svarer inden for 30 dage. Siger du i et opkald, at vi ikke må
ringe igen, registrerer vi det med det samme. Du kan klage til Datatilsynet (datatilsynet.dk).

**Lydoptagelse.** Optager vi en samtale, siger assistenten det i starten. Ønsker du ikke optagelse, så sig det; så
stopper vi optagelsen, eller sletter den, når samtalen er slut.
