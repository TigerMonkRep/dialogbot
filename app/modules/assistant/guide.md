# Dialogbot – fakta til assistenten i appen

Denne fil er hele assistentens produktviden. Den læses ind i assistentens instruktion ord for ord. Ret den, når
produktet ændres – assistenten må ikke sige noget om Dialogbot, der ikke står her eller i kundens egen tilstand.
Priserne står også i `app/modules/billing/prices.py` og `docs/pricing.md`; de skal passe sammen.

## Hvad Dialogbot er
- En digital receptionist til danske virksomheder: tager telefonen og chatten på hjemmesiden døgnet rundt, svarer
  kun ud fra viden, virksomheden selv har godkendt, kan booke tider og giver virksomheden en kort, skrevet
  opsummering af hver henvendelse og en dagsrapport.
- Den gætter aldrig. Kan den ikke svare, siger den det og tager en besked (en henvendelse med en opgave).
- Den siger altid ærligt, at den er en digital assistent.

## Priser (alle ekskl. moms; 25 % moms lægges på fakturaen)
- Abonnement: 2.495 kr. om måneden. Telefon, webchat, booking og opsummeringer er med. Ingen pris pr. henvendelse.
- 300 påbegyndte minutter pr. kalendermåned er med – én pulje til både indgående opkald og udgående
  kampagneopkald, brugt i den rækkefølge opkaldene sker. Derudover 1,50 kr. pr. påbegyndt indgående minut og 2 kr.
  pr. påbegyndt udgående minut. Forbruget ses under Konto.
- Udgående kampagneopkald: ingen pris pr. opkald – et ubesvaret opkald koster intet. Samtaleminutterne trækker på
  pakken. En kontakt ringes højst 2 gange og taler højst 3 minutter; før start vises den højeste mulige pris.
- Minutter krediteres kun, når kunden klager over et opkald (ingen automatisk kreditering).
- Opsætning: gør-det-selv er med (tre trin, ca. 30 minutter). Skræddersyet opsætning fra Dialogbots specialister
  koster 5.000 kr. én gang (valgfrit).
- Ingen binding. Opsigelse til udgangen af måneden: skriv det til assistenten (så sendes det til Dialogbot-teamet)
  eller til info@dialogbot.dk.
- Betaling: kort gemmes hos Stripe under Konto; hver måned faktureres bagud. Uden kort faktureres måneden ikke.
  Fakturaer ses under Konto. Betaling starter aldrig opkald.

## Opsætning (byggevejledningen, tre trin)
1. Om virksomheden (/opsaetning/1): hjemmeside-adresse, CVR eller navn, telefonnummer. Dialogbot læser hjemmesiden
   og foreslår beskrivelse, åbningstider, ydelser og priser som kladder – man godkender eller retter. Priser gættes
   aldrig.
2. Kalender (/opsaetning/2): forbind Google Kalender eller Microsoft 365, eller spring over. Dialogbot skriver kun nye
   aftaler i kalenderen og rører aldrig eksisterende aftaler. Start-regler: aftaler på 45 minutter, 15 minutters
   pause, tidligst i morgen.
3. Test og tænd (/opsaetning/3): vælg stemme, forbind telefonen med viderestilling, lav et prøveopkald og tænd.
- Man kan springe trin over og finde alt igen under Alle indstillinger.

## Viden (/app/viden)
- Ydelser og priser (ekskl. moms), åbningstider, kørselsområde, faste svar på spørgsmål, tilbud, og emner den ikke
  må svare på.
- Alt starter som en kladde. Kun en ejer eller administrator kan godkende; først derefter bruger assistenten det.
  Sletter man godkendt viden, holder den straks op med at bruge den.
- «Test mig som kunde» i assistentpanelet svarer kun ud fra godkendt viden.

## Telefon (Alle indstillinger → Telefon)
- Virksomheden beholder sit nummer og sit teleselskab. Dialogbot giver et Dialogbot-nummer, som man viderestiller til.
- Nummeret bekræftes med et opkald, der læser en kode på 6 cifre op (gyldig i 10 minutter).
- Hvornår Dialogbot tager den: altid, eller kun når man ikke selv tager den (optaget / ingen svar).
- Viderestillingskoder på mobil (virker hos de fleste danske teleselskaber, nummer med +45):
  optaget **67*nummer#, ingen svar **61*nummer#, slukket **62*nummer#, altid **21*nummer#, slå alt fra ##002#.
  Status: *#67# eller *#61#. Fastnet og IP-telefoni: brug teleselskabets app/selvbetjening eller spørg teleselskabet.
- Prøveopkald: start testen og ring inden for 15 minutter fra en anden telefon. Derefter kan telefonen tændes.
  Dialogbot kan sættes på pause igen; viderestillingen slås fra på telefonen.
- Opkald med udskrift og opsummering ses under Opkald.

## Hilsen og receptionsmanuskript (Alle indstillinger → Hilsen)
- Hilsen (det den siger først), navnet den præsenterer sig med, du eller De, hvad den spørger kunden om, hvornår en
  medarbejder skal overtage, hvad den skal undgå, og hvordan den afslutter. Gælder telefon og chat.
- Hilsenen nævner altid, at det er en digital assistent; ellers tilføjes det automatisk.

## Stemme og sprog
- Standardstemmer: Camilla (kvinde, rolig rigsdansk) og Peter (mand, let jysk klang). Man kan altid skifte.
- Egen stemme: optages i browseren; indtaleren giver samtykke, og Dialogbot gennemgår samtykket før brug.
- Udtale: forkert udtalte ord (fx firmanavnet) rettes under Stemme.
- Samtalesprog: dansk, engelsk, tysk, spansk, fransk, italiensk, norsk og svensk. Ét standardsprog, som skal være
  blandt de slåede-til sprog. Andre sprog end dansk får en indfødt stemme af samme køn som den valgte standardstemme.
- Appens sprog vælges af hver bruger under Konto.

## Booking (Aftaler og Alle indstillinger → Booking)
- Ledige tider følger godkendte åbningstider og bookingreglerne: pause mellem aftaler, tidligste tid (timer frem) og
  hvor mange dage frem man kan booke. Aftaletyper med varighed.
- Optaget tid fra Google/Outlook kan også læses via kalenderens hemmelige iCal-adresse (kun start og slut, hvert kvarter).
- Hvilke systemer der er forbundet (kalender, SMS m.m.), står under Alle indstillinger → Kalender og integrationer.
  Står et system ikke som forbundet, virker det ikke endnu.

## Webchat (Alle indstillinger → Webchat)
- Med i abonnementet og bruger samme godkendte viden som telefonen. Slå den til, godkend jeres domæner og indsæt én
  kodelinje på hjemmesiden. Egen velkomsthilsen. Samtaler kan overtages af en medarbejder under Opkald.

## Kampagner (/app/kampagner)
- Dialogbot ringer ud til en liste. Kontakterne skal på forhånd have bedt om at blive ringet op (markedsføringslovens
  § 10) – også virksomheder; det er ikke nok, at de ikke står på Robinsonlisten.
- Tre trin: vælg kontakter, hør manuskriptet, godkend den højeste pris. Kun en administrator kan starte en kampagne.

## Rapporter (/app/ugen)
- Ugens tal: opkald, samtaler, henvendelser og forbrug. Dagsrapport på e-mail til et valgt klokkeslæt, kan slås fra.

## Team og roller (Konto)
- Ejer og administrator: godkender viden og ændrer indstillinger. Medarbejder: arbejder med henvendelser og kladder.
  Læser: kan kun se. Ejer/administrator inviterer nye under Konto.
- Alle godkendelser og ændringer logges (Alle indstillinger → Aktivitetslog).

## Kontakt
- Dialogbot-teamet: info@dialogbot.dk. Svar på hverdage, som regel inden for én arbejdsdag.
