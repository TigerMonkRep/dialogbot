"""Writes voice_pipeline/eval/testset_da.jsonl: new, hand-written Danish test sentences for voice evaluation.

Each row: id, category, text (what the assistant would say), meaning (what the listener must understand)
and must_say (exact spoken forms that normalisation must produce – critical values). Re-run after editing:
    python -m voice_pipeline.eval.build_testset
"""
from __future__ import annotations

import json
from pathlib import Path

OUT = Path(__file__).with_name("testset_da.jsonl")

SETS: dict[str, list[tuple]] = {
    "kort_spørgsmål": [
        ("Hej, du taler med Dialogbots AI-assistent hos Fjord Gulvservice. Hvad kan jeg hjælpe med?", "Hilsen med AI-oplysning og åbent spørgsmål"),
        ("Hvad hedder du?", "Spørger om navn"),
        ("Må jeg få dit telefonnummer?", "Beder om telefonnummer"),
        ("Hvilken adresse drejer det sig om?", "Beder om adresse"),
        ("Passer det dig bedst om formiddagen eller eftermiddagen?", "Valg mellem to tidsrum"),
        ("Er det et trægulv eller et laminatgulv?", "Spørger om gulvtype"),
        ("Vil du have, at en medarbejder ringer dig op?", "Tilbyder opringning"),
        ("Har du et øjeblik?", "Spørger om tid"),
        ("Skal jeg gentage det?", "Tilbyder gentagelse"),
        ("Hvordan stavede du efternavnet?", "Beder om stavning"),
        ("Er der andet, jeg kan hjælpe med?", "Afsluttende spørgsmål"),
        ("Må jeg sende en bekræftelse på sms?", "Beder om samtykke til sms"),
    ],
    "langt_svar": [
        ("Vi sliber og behandler trægulve i hele Østjylland, og vi bruger et støvfrit anlæg, så du kan blive boende i huset, mens vi arbejder.", "Beskrivelse af ydelse"),
        ("En medarbejder kigger på din forespørgsel i løbet af i dag og ringer dig op, så I kan aftale det praktiske og få et konkret tilbud.", "Opfølgning fra medarbejder"),
        ("Før vi kan give en endelig pris, skal vi se gulvet, fordi prisen afhænger af træsorten, slidlaget og hvor mange kvadratmeter det drejer sig om.", "Pris kræver besigtigelse"),
        ("Jeg har noteret dit navn, dit telefonnummer og adressen, og du får en bekræftelse, når en medarbejder har set på det.", "Opsummering af registrering"),
        ("Hvis du vil aflyse eller flytte tiden, er du velkommen til at ringe igen, så hjælper jeg dig med det.", "Aflysning eller flytning"),
        ("Vores åbningstid er mandag til fredag fra klokken otte til seksten, og om lørdagen har vi lukket.", "Åbningstider"),
        ("Jeg kan desværre ikke svare på spørgsmål om garanti, men jeg kan bede en medarbejder om at ringe dig op med det samme.", "Afgrænsning og viderestilling", ["ikke svare"]),
        ("Samtalen bliver skrevet ned, så medarbejderen kan se, hvad vi har talt om, og du skal ikke gentage det hele igen.", "Oplysning om transskribering"),
        ("Når gulvet er slebet, lakerer vi det to gange, og det skal have et døgn til at hærde, før der må sættes møbler på.", "Arbejdsgang"),
        ("Jeg forstod ikke helt, hvad du sagde. Vil du sige det igen, lidt langsommere?", "Beder om gentagelse"),
        ("Tak fordi du ringede til Fjord Gulvservice. Du hører fra os senest i morgen, og hav en rigtig god dag.", "Afslutning"),
        ("Hvis det er akut, for eksempel en vandskade, stiller jeg dig direkte om til vagttelefonen.", "Akut eskalering"),
    ],
    "navne_steder": [
        ("Er adressen i Aarhus, Rødovre eller Sønderborg?", "Tre stednavne"),
        ("Du har fået en tid hos Søren Kjærgaard i Viborg.", "Navn og by"),
        ("Vi kører til Herning, Ikast, Brande og Silkeborg.", "Liste af byer"),
        ("Adressen er Abildgade 18 i Aarhus N.", "Adresse med husnummer", ["Abildgade atten"]),
        ("Kontaktpersonen er Mette Ørskov Jørgensen.", "Navn med æøå"),
        ("Er det Nørresundby eller Nørre Aaby?", "Forvekslelige stednavne"),
        ("Vi dækker hele Midt- og Østjylland samt Djursland.", "Område"),
        ("Min kollega Frederikke fra kontoret i Randers ringer dig op.", "Navn og by"),
        ("Gården ligger mellem Skjern og Tarm.", "Stednavne"),
        ("Hvordan skriver man Hjørring og Brønderslev?", "Stednavne"),
        ("Butikken ligger på Østerbrogade i København Ø.", "Adresse"),
        ("Du har talt med Anne-Sofie Bækgaard fra Kolding.", "Navn med bindestreg"),
    ],
    "tal_beløb": [
        ("Det koster 1.495 kroner om måneden eksklusive moms.", "Pris 1495 kr/md ekskl. moms", ["et tusind fire hundrede og femoghalvfems kroner", "eksklusive"]),
        ("Tilbuddet gælder ved mindst 40 kvadratmeter.", "Minimum 40 m²", ["mindst fyrre kvadratmeter"]),
        ("Prisen er 149 kr. pr. godkendt henvendelse.", "149 kr pr. henvendelse", ["et hundrede og niogfyrre kroner"]),
        ("En pakke koster 9 kroner og giver op til 2 forsøg.", "9 kr, 2 forsøg", ["ni kroner", "to forsøg"]),
        ("Afslibning koster 145 kr. pr. kvadratmeter.", "145 kr/m²", ["et hundrede og femogfyrre kroner"]),
        ("Med moms bliver det 186,25 kr.", "186,25 kr inkl. moms", ["et hundrede og seksogfirs kroner og femogtyve øre"]),
        ("Rabatten er 10 % ved over 100 m2.", "10 % ved over 100 m²", ["ti procent", "et hundrede kvadratmeter"]),
        ("Et gulv på 65 m² koster cirka 9.425 kr.", "65 m², ca. 9.425 kr", ["femogtres kvadratmeter", "ni tusind fire hundrede og femogtyve kroner"]),
        ("Depositum er 2.500 kroner, som du får tilbage.", "Depositum 2.500 kr", ["to tusind fem hundrede kroner"]),
        ("Vi har 3 ledige montører i næste uge.", "3 montører", ["tre ledige"]),
        ("Ordrenummeret er 1001.", "Ordre 1001", ["et tusind og en"]),
        ("Beløbet er 12.000 kr. inkl. moms.", "12.000 kr inkl. moms", ["tolv tusind kroner", "inklusive"]),
        ("Totalprisen er 1.000.000 kroner.", "1 mio. kr", ["en million kroner"]),
    ],
    "tid_dato": [
        ("Jeg har en ledig tid onsdag den 28. oktober klokken halv elleve.", "Onsdag 28/10 kl. 10.30", ["den otteogtyvende oktober", "halv elleve"]),
        ("Vi kommer den 1. december kl. 8.00.", "1/12 kl. 8", ["den første december", "klokken otte"]),
        ("Tiden er flyttet til 14:15.", "14.15", ["klokken fjorten femten"]),
        ("Vores åbningstid er kl. 8.00-16.30 på hverdage.", "8–16.30", ["klokken otte til seksten tredive"]),
        ("Fakturaen forfalder 01.12.2026.", "Forfald 1/12 2026", ["den første december to tusind og seksogtyve"]),
        ("Vi ringer dig op mellem kl. 10 og kl. 12.", "10–12", ["klokken ti", "klokken tolv"]),
        ("Kan du den 3. november om eftermiddagen?", "3/11 eftermiddag", ["den tredje november"]),
        ("Montøren er hos dig mandag den 2. marts klokken 7.30.", "Mandag 2/3 kl. 7.30", ["den anden marts", "klokken syv tredive"]),
        ("Svarfristen er 14 dage.", "14 dage", ["fjorten dage"]),
        ("Vi holder lukket fra 24/12 til 1/1.", "24/12–1/1", ["den fireogtyvende december", "den første januar"]),
        ("Tilbuddet gælder til og med den 31. januar 2027.", "31/1 2027", ["den enogtredivte januar to tusind og syvogtyve"]),
        ("Besigtigelsen tager cirka 45 minutter.", "45 minutter", ["femogfyrre minutter"]),
        ("Kl. 9.05 er der stadig en tid.", "kl. 9.05", ["Klokken ni nul fem"]),
    ],
    "email_telefon": [
        ("Jeg gentager telefonnummeret i grupper på to cifre: 20 30 40 50.", "20 30 40 50 i par", ["tyve tredive fyrre halvtreds"]),
        ("Du kan skrive til info@fyrster.dk.", "E-mail", ["info snabel-a fyrster punktum d k"]),
        ("Ring til os på +45 70 12 34 56.", "+45 70 12 34 56", ["plus femogfyrre", "halvfjerds tolv fireogtredive seksoghalvtreds"]),
        ("Dit nummer er 22334455, er det korrekt?", "22 33 44 55", ["toogtyve treogtredive fireogfyrre femoghalvtreds"]),
        ("Mailen er mette.hansen@hansenbyg.dk.", "E-mail med punktum", ["mette punktum hansen snabel-a hansenbyg punktum d k"]),
        ("Vagttelefonen har nummer 70 20 10 05.", "70 20 10 05", ["halvfjerds tyve ti nul fem"]),
        ("Send billederne til kontakt@fjord-gulv.dk.", "E-mail med bindestreg", ["kontakt snabel-a fjord bindestreg gulv punktum d k"]),
        ("Er dit nummer 40 00 12 34?", "40 00 12 34", ["fyrre nul nul tolv fireogtredive"]),
        ("Jeg har skrevet 51 62 73 84 ned.", "51 62 73 84", ["enoghalvtreds toogtres treoghalvfjerds fireogfirs"]),
        ("Svar gerne på ordre@firma.dk eller ring 33 12 45 67.", "E-mail og telefon", ["ordre snabel-a firma punktum d k", "treogtredive tolv femogfyrre syvogtres"]),
        ("Du kan også ringe på +45 20 30 40 50 efter klokken fire.", "+45 20 30 40 50", ["plus femogfyrre", "tyve tredive fyrre halvtreds"]),
        ("Nummeret er 12 34 56 78.", "12 34 56 78", ["tolv fireogtredive seksoghalvtreds otteoghalvfjerds"]),
    ],
    "afbrydelse": [
        ("Undskyld, jeg afbrød dig. Fortsæt bare.", "Giver ordet tilbage"),
        ("Ja, selvfølgelig. Hvad ville du sige?", "Lytter efter afbrydelse"),
        ("Okay, jeg stopper her. Hvad har du brug for?", "Stopper ved afbrydelse"),
        ("Det forstår jeg. Lad os tage det med det samme.", "Skifter emne"),
        ("Jeg hørte, at du sagde noget. Kan du gentage det?", "Beder om gentagelse"),
        ("Fint, så springer vi det over.", "Springer over"),
        ("Et øjeblik, jeg tjekker kalenderen.", "Venter på system"),
        ("Mm, ja. Og hvad mere?", "Kort bekræftelse"),
        ("Vent lige, sagde du onsdag eller torsdag?", "Afklaring af dag"),
        ("Undskyld, forbindelsen var dårlig. Hvad sagde du?", "Dårlig forbindelse"),
        ("Nej, det var ikke det, jeg mente. Jeg mente lørdag.", "Retter misforståelse", ["ikke det"]),
        ("Helt i orden, jeg venter.", "Venter"),
    ],
    "bookingfejl": [
        ("Tiden er endnu ikke bekræftet. Jeg undersøger, om den blev oprettet.", "Uafklaret booking", ["ikke bekræftet"]),
        ("Jeg kunne ikke nå kalenderen lige nu, så tiden er ikke booket. En medarbejder ringer dig op.", "Kalenderfejl, intet booket", ["ikke booket"]),
        ("Den tid er desværre lige blevet taget. Skal jeg finde en anden?", "Tid taget"),
        ("Din tid onsdag den 28. oktober klokken 10.30 er nu bekræftet.", "Bekræftet efter systemsvar", ["den otteogtyvende oktober", "klokken ti tredive"]),
        ("Jeg fik ikke svar fra systemet, så jeg ved ikke, om tiden er oprettet. Du får besked i dag.", "Timeout, uafklaret", ["ved ikke"]),
        ("Der er ingen ledige tider de næste fjorten dage.", "Ingen tider", ["ingen ledige tider"]),
        ("Bookingen blev ikke gennemført, og du er ikke blevet opkrævet noget.", "Fejl uden betaling", ["ikke gennemført", "ikke blevet opkrævet"]),
        ("Jeg har ikke booket noget endnu. Vil du have tiden klokken 13.00?", "Intet booket, tilbud", ["ikke booket", "klokken tretten"]),
        ("Aflysningen er registreret, men du får først en bekræftelse, når medarbejderen har set den.", "Aflysning uafklaret"),
        ("Systemet svarer ikke. Jeg noterer dit ønske, så en medarbejder kan bekræfte tiden.", "Systemfejl", ["svarer ikke"]),
        ("Tiden kunne ikke flyttes, så din oprindelige tid den 3. november gælder stadig.", "Flytning fejlede", ["den tredje november", "ikke flyttes"]),
        ("Det lykkedes ikke at sende sms'en, men din tid er bekræftet i kalenderen.", "Sms fejlede, tid bekræftet", ["ikke at sende"]),
    ],
    "negation": [
        ("Vi sliber ikke gulve om søndagen.", "Ikke søndag", ["sliber ikke"]),
        ("Det er ikke muligt at få en pris i telefonen.", "Ingen pris i telefon", ["ikke muligt"]),
        ("Du skal ikke betale noget for besigtigelsen.", "Gratis besigtigelse", ["ikke betale"]),
        ("Vi har aldrig lukket i juli.", "Aldrig lukket", ["aldrig"]),
        ("Der er ingen ekstra gebyrer.", "Ingen gebyrer", ["ingen ekstra"]),
        ("Tilbuddet gælder ikke for erhvervskunder.", "Undtagelse", ["gælder ikke"]),
        ("Jeg kan hverken love en pris eller en dato.", "Hverken-eller", ["hverken"]),
        ("Nej, vi kommer ikke før klokken 9.", "Ikke før kl. 9", ["ikke før klokken ni"]),
        ("Det er ikke nødvendigt at flytte møblerne.", "Ikke nødvendigt", ["ikke nødvendigt"]),
        ("Vi arbejder ikke med vinylgulve.", "Ingen vinyl", ["arbejder ikke"]),
        ("Du bliver ikke ringet op igen.", "Opt-out bekræftet", ["ikke ringet op igen"]),
        ("Ingen af vores montører er ledige i dag.", "Ingen ledige", ["Ingen af"]),
    ],
}


def rows() -> list[dict]:
    out = []
    for cat, items in SETS.items():
        for item in items:
            text, meaning = item[0], item[1]
            must = list(item[2]) if len(item) > 2 else []
            out.append({"id": f"da-{len(out) + 1:03d}", "category": cat, "text": text, "meaning": meaning, "must_say": must})
    return out


if __name__ == "__main__":
    data = rows()
    OUT.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in data), encoding="utf-8")
    print(f"wrote {len(data)} sentences to {OUT}")
