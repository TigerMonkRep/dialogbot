"""Recording manuscripts for customers who record their own voice.

    python -m voice_pipeline.manuscripts.build          # writes da_kort.json and da_standard.json next to this file

Two manuscripts:
- `kort` (~2–3 min): enough for a reference-conditioned voice right away.
- `standard` (~30 min, 400 sentences): enough material for a voice trained on the speaker (fine-tuning).

Every sentence has an `id`, a `category`, the `text` the speaker reads, and the `spoken` form the normaliser turns it
into (numbers, dates and amounts written out), which is what a training transcript needs. `{firma}`, `{ydelse}` and
`{by}` are filled in with the customer's own details when the manuscript is shown, so people read about their own
business. The categories follow docs/voice/recording-brief.md. The sentences are new: none is in the evaluation test
set (voice_pipeline/eval/testset_da.jsonl), which the build checks.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent

INSTRUCTIONS = [
    "Optag i et stille rum med bløde flader, fx gardiner, tæpper eller et klædeskab. Undgå køkken og badeværelse.",
    "Hold telefonen eller mikrofonen 15–20 cm fra munden og samme afstand hele vejen.",
    "Læs i dit eget tempo med din normale telefonstemme: venlig og rolig. Du skal ikke lyde som en oplæser.",
    "Tag en ny optagelse af sætningen, hvis du siger forkert, griner eller bliver forstyrret.",
    "Tal og datoer læser du, som du selv ville sige dem i telefonen. Forslaget under teksten viser én måde.",
    "Hold en kort pause efter hver sætning.",
]

KORT = [
    ("hilsen", "Hej, og tak fordi du ringer til {firma}. Du taler med en digital assistent, og jeg hjælper gerne."),
    ("hilsen", "Godmorgen. Hvad kan jeg gøre for dig i dag?"),
    ("fortælling", "I weekenden var vi en tur ved stranden. Det regnede lidt om formiddagen, men om eftermiddagen kom "
                   "solen frem, og så blev det en rigtig dejlig dag."),
    ("fortælling", "Vi har haft travlt i denne uge, men det går fint. De fleste opgaver bliver klaret samme dag, og "
                   "resten tager vi fat på i morgen tidlig."),
    ("spørgsmål", "Passer det dig bedst om formiddagen eller om eftermiddagen?"),
    ("spørgsmål", "Må jeg spørge, hvad det drejer sig om?"),
    ("spørgsmål", "Kan du give mig et nummer, jeg kan ringe tilbage på?"),
    ("tal", "Vi kan komme tirsdag den fjerde november klokken kvart over ni."),
    ("tal", "Prisen er 2.350 kroner, og det er inklusive moms."),
    ("tal", "Mit nummer er 42 36 18 29."),
    ("steder", "Vi har kunder i Esbjerg, Randers, Næstved, Svendborg og Frederikshavn."),
    ("forbehold", "Det kan jeg desværre ikke love dig i dag, men jeg skal nok undersøge det."),
    ("forbehold", "Nej, der er ingen ekstra gebyrer, og det er helt uforpligtende."),
    ("forbehold", "Aftalen er ikke bekræftet endnu. Du får en besked, så snart den er på plads."),
    ("afslutning", "Tusind tak for snakken. Hav en rigtig god dag, og på gensyn."),
]

HILSNER = [
    "Hej, du har ringet til {firma}. Hvad kan jeg hjælpe dig med?",
    "Goddag, og velkommen til {firma}.",
    "Godeftermiddag, du taler med {firma}s assistent.",
    "Hej igen, dejligt at høre fra dig.",
    "Tak fordi du ventede. Nu er jeg her.",
    "Hej, det er {firma}. Jeg er en digital assistent, men jeg kan godt hjælpe dig videre.",
    "Godaften. Vi har lukket for i dag, men du kan lægge en besked hos mig.",
    "Velkommen til. Du er kommet til den rigtige, hvis det handler om {ydelse}.",
    "Hej, hvad kan jeg gøre for dig?",
    "Tak for din henvendelse til {firma}.",
    "Farvel, og hav en god weekend.",
    "Tak for i dag. Vi ses snart.",
    "Du må have en rigtig god dag.",
    "Tak for opringningen, og god aften.",
    "Det var så lidt. Ring endelig igen, hvis der er mere.",
    "Så har jeg alt, hvad jeg skal bruge. Tak for det.",
    "Fint, så siger vi det. Hej hej.",
    "God tur hjem, og pas godt på dig selv.",
    "Tak skal du have. Du hører fra os.",
    "Jeg ønsker dig en rigtig god dag.",
]

SPØRGSMÅL = [
    "Hvad hedder du til fornavn?", "Og hvad er dit efternavn?", "Hvor bor du henne?", "Hvornår passer det dig?",
    "Er det en privat bolig eller en virksomhed?", "Hvor mange kvadratmeter drejer det sig om?",
    "Har du været kunde hos os før?", "Hvordan har du hørt om {firma}?", "Må jeg sende dig en bekræftelse på sms?",
    "Skal jeg stave det tilbage til dig?", "Er det i orden, at en medarbejder ringer dig op?",
    "Har du et ordrenummer ved hånden?", "Hvilken dag i næste uge kunne passe?", "Er der noget, vi skal være særligt opmærksomme på?",
    "Kan du beskrive problemet lidt nærmere?", "Hvor længe har det stået på?", "Er der adgang for en varebil?",
    "Skal vi ringe på, eller er der en nøgleboks?", "Vil du hellere have et tilbud på mail?", "Er der mere, du gerne vil vide i dag?",
    "Hvad er den bedste måde at fange dig på?", "Må jeg bede om din mailadresse?", "Er det akut, eller kan det vente til i morgen?",
    "Passer torsdag bedre end fredag?", "Kan du høre mig tydeligt nu?", "Er det dig, der skal være hjemme, når vi kommer?",
    "Hvilket postnummer er det?", "Har du billeder af det, du kan sende os?", "Ønsker du at blive ringet op i dag?",
    "Må jeg notere det i din sag?", "Hvor mange personer er I?", "Hvornår er du selv hjemme?",
    "Skal jeg reservere tiden til dig?", "Vil du have en påmindelse dagen før?", "Er det første gang, du bestiller {ydelse}?",
    "Har du spørgsmål til prisen?", "Er der parkering i nærheden?", "Hvad er dit telefonnummer?",
    "Kan du vente et øjeblik, mens jeg tjekker?", "Er det dit eget nummer, du ringer fra?", "Passer klokken otte for tidligt?",
    "Hvad synes du om det forslag?", "Vil du have, at vi tager det gamle med?", "Kender du din kundekode?",
    "Må jeg spørge, hvad budgettet er?", "Er det i orden, at jeg gentager det?", "Skal fakturaen sendes til en anden adresse?",
    "Hvilken ydelse er du interesseret i?", "Har du set vores åbningstider?", "Hvor hurtigt skal det være klar?",
    "Hvem skal vi spørge efter?", "Er det en hel dag eller kun et par timer?", "Kan vi ringe tilbage i løbet af eftermiddagen?",
    "Er du stadig der?", "Vil du have et fast tidspunkt hver uge?", "Er det en gave?", "Hvilken farve foretrækker du?",
    "Har du nogen allergier, vi skal kende til?", "Skal vi tage skoene af, når vi kommer ind?", "Hvad er vigtigst for dig?",
]

FORKLARINGER = [
    "Når du har booket en tid, får du en bekræftelse på sms. Dagen før sender vi en påmindelse, så du ikke glemmer det.",
    "Vi starter altid med en kort gennemgang, så vi er sikre på, at vi har forstået opgaven rigtigt, inden vi går i gang.",
    "Hvis du bliver forhindret, kan du flytte tiden gratis frem til dagen før. Derefter beder vi dig ringe til os.",
    "Prisen afhænger af, hvor stort området er, og hvilken stand det er i. Derfor giver vi et fast tilbud, når vi har set det.",
    "{firma} har arbejdet med {ydelse} i mange år, og vi dækker hele området omkring {by}.",
    "Vores medarbejdere har alle den nødvendige uddannelse, og vi rydder altid op efter os, når vi er færdige.",
    "Hvis du ikke er tilfreds med resultatet, så ring til os inden for fjorten dage, så finder vi en løsning sammen.",
    "Jeg er en digital assistent, så jeg kan ikke træffe aftaler om pris, men jeg kan give din besked videre til en kollega.",
    "Du kan betale med kort, MobilePay eller bankoverførsel, og fakturaen kommer på mail, når opgaven er udført.",
    "I højsæsonen kan der være lidt længere ventetid, men vi gør altid vores bedste for at finde en tid, der passer.",
    "Det er en god idé at fjerne møbler og løse ting, inden vi kommer, så vi kan komme til med det samme.",
    "Vi bruger miljøvenlige produkter, og de er godkendt til brug i hjem med børn og dyr.",
    "Hvis det haster, kan vi i nogle tilfælde komme samme dag. Det koster et lille tillæg, som jeg fortæller dig om først.",
    "Når opgaven er færdig, gennemgår vi den sammen med dig, så du kan se, at alt er i orden.",
    "Tilbuddet er gyldigt i tredive dage, og det er helt uforpligtende for dig at sige ja eller nej.",
    "Vi kører ud i hele regionen, men uden for vores normale område lægger vi et kørselstillæg på.",
    "Hvis du har en forsikringssag, kan vi hjælpe med dokumentation og billeder til dit forsikringsselskab.",
    "Du er altid velkommen til at ringe, hvis du er i tvivl om noget. Vi vil hellere svare én gang for meget.",
    "Vores åbningstid er på hverdage, men assistenten tager imod beskeder hele døgnet.",
    "Der kan gå et par dage, før vi har alle materialer hjemme, og så ringer vi dig op med en endelig dato.",
    "Hvis vejret er dårligt, kan vi blive nødt til at flytte udendørs opgaver. Så kontakter vi dig så hurtigt som muligt.",
    "Til første besøg afsætter vi omkring en time, så der er god tid til spørgsmål.",
    "Vi har en fast kontaktperson til hver kunde, så du ikke skal forklare det hele forfra, hver gang du ringer.",
    "Det tager typisk to til tre arbejdsdage, men det afhænger af, hvor meget der skal laves.",
    "Hvis du vil se eksempler på vores arbejde, kan du finde billeder på vores hjemmeside.",
    "Vi har lukket i uge 29 og 30, men beskeder bliver besvaret, så snart vi er tilbage.",
    "Materialerne har fem års garanti, og selve arbejdet har vi to års garanti på.",
    "Vi kan desværre ikke give en pris over telefonen, før vi har set opgaven, men besigtigelsen er gratis.",
    "Du får en skriftlig ordrebekræftelse, hvor alle aftaler står, så der ikke opstår misforståelser.",
    "Hvis du har kæledyr, er det rart, hvis de er i et andet rum, mens vi arbejder.",
    "Når vi har modtaget din betaling, sender vi en kvittering med det samme.",
    "Vi arbejder normalt mellem syv og femten, men efter aftale kan vi også komme om aftenen.",
    "Det er gratis at få et tilbud, og du binder dig ikke til noget ved at sige ja til et besøg.",
    "Hvis du fortryder, kan du afbestille uden omkostninger indtil otteogfyrre timer før.",
    "Vi ringer altid en halv time før, vi er fremme, så du ved, hvornår du kan forvente os.",
    "Opgaven kræver strøm og vand, så det er fint, hvis der er adgang til begge dele.",
    "Hvis du ønsker det, kan vi også bortskaffe det gamle, og det står så som en særskilt linje på fakturaen.",
    "Vores kunder giver os i gennemsnit en høj bedømmelse, og det er vi rigtig glade for.",
    "Jeg har skrevet alt ned, og en medarbejder vender tilbage til dig i løbet af i morgen.",
    "Det er helt normalt at have spørgsmål, så tag dig bare god tid.",
    "Vi har mange års erfaring med netop den slags opgaver, så du er i gode hænder.",
    "Hvis du vil ændre noget i ordren, er det nemmest at gøre det, inden vi bestiller materialerne.",
    "Ved større opgaver deler vi betalingen op i to rater, én ved start og én ved aflevering.",
    "Vi overholder alle gældende regler, og vi har selvfølgelig en erhvervsforsikring.",
    "Du kan også skrive til os, hvis det er nemmere for dig end at ringe.",
    "Hvis der opstår noget uforudset undervejs, stopper vi og aftaler det med dig, før vi fortsætter.",
    "Vi er et lille firma, og det betyder, at du taler med dem, der rent faktisk udfører arbejdet.",
    "Til sidst får du et par gode råd om vedligeholdelse, så resultatet holder længst muligt.",
    "Vi kan tilbyde en fast aftale, hvor vi kommer igen hver sjette måned.",
    "Tak for din tålmodighed. Jeg har fundet en løsning, som jeg tror, du bliver glad for.",
    "Hvis linjen er optaget, kan du trygt lægge en besked, så ringer vi tilbage samme dag.",
    "Vi har åbent for nye kunder i hele {by} og omegn.",
    "Hos {firma} lægger vi vægt på, at du får en ordentlig og ærlig pris.",
    "Mange af vores kunder kommer igen år efter år, og det er den bedste anerkendelse, vi kan få.",
    "Jeg kan se i kalenderen, at der er et par ledige tider i starten af næste uge.",
    "Vi sender en faktura efter endt arbejde med fjorten dages betalingsfrist.",
    "Hvis du har en gammel aftale, kan jeg finde den frem, når du giver mig dit navn.",
    "Det er en god idé at læse vejledningen, inden du tager det i brug første gang.",
    "Vi kan ikke garantere et bestemt tidspunkt på dagen, men vi kan love et tidsrum på to timer.",
    "Hvis du ønsker det, sender vi en kopi af tilbuddet til din samlever eller din udlejer.",
    "Når vi er færdige, får du en mail med billeder af det udførte arbejde.",
    "Vores medarbejdere bærer altid tøj med logo, så du kan se, hvem vi er.",
    "Hvis der er noget, du er i tvivl om i tilbuddet, gennemgår jeg det gerne punkt for punkt.",
    "Vi bruger kun materialer, som vi selv ville bruge i vores egne hjem.",
    "Det er lidt svært at sige præcist, men de fleste opgaver af den type tager en halv dag.",
    "Vi kan starte allerede i næste uge, hvis du bekræfter i dag.",
    "Du skal ikke gøre noget særligt, inden vi kommer, andet end at være hjemme.",
    "Vi har desværre ikke mulighed for at tage imod kontanter.",
    "Hvis du har brug for hjælp uden for åbningstiden, kan du ringe til vores vagttelefon.",
    "Vi afslutter altid med at spørge, om du er tilfreds, og om der er noget, vi kan gøre bedre.",
    "Vores assistent kan booke tider, svare på spørgsmål og tage imod beskeder, men ikke ændre i betalinger.",
    "Jeg har fundet din sag. Den er modtaget, og en tekniker kigger på den i dag.",
    "Du kan altid bede om at tale med et menneske, så sørger jeg for, at en medarbejder ringer dig op.",
    "Det er vigtigt for os, at du føler dig godt behandlet, fra du ringer, til opgaven er færdig.",
    "Tidspunktet er foreløbigt, indtil du har fået en bekræftelse fra os.",
    "Vi har ingen binding, så du kan stoppe aftalen med en måneds varsel.",
    "Hvis du vil høre mere om {ydelse}, kan jeg sende dig en kort beskrivelse på mail.",
    "Mange spørger om det samme, så du er langt fra den eneste.",
    "Vi vender tilbage senest på fredag med et endeligt svar.",
]

FORBEHOLD = [
    "Det har jeg desværre ikke adgang til.", "Nej, den tid er ikke ledig længere.", "Vi kan ikke komme i weekenden.",
    "Prisen er ikke endelig, før vi har set opgaven.", "Jeg kan ikke bekræfte tiden, før en medarbejder har godkendt den.",
    "Nej, vi tager ikke opgaver uden for landets grænser.", "Det er desværre ikke noget, vi tilbyder.",
    "Du er ikke blevet opkrævet noget endnu.", "Nej, du skal ikke betale for besigtigelsen.",
    "Jeg er ikke sikker, så jeg spørger lige en kollega.", "Aftalen er ikke gennemført, før du har fået en bekræftelse.",
    "Det må vi desværre ikke udlevere over telefonen.", "Nej, der er ingen binding.", "Jeg kan ikke se nogen ordre i dit navn.",
    "Tilbuddet gælder ikke sammen med andre rabatter.", "Vi har ikke modtaget din betaling endnu.",
    "Det er ikke sikkert, at vi kan nå det i denne uge.", "Nej, det er ikke for sent at ændre det.",
    "Jeg kan ikke love noget, men jeg giver beskeden videre.", "Nej, du behøver ikke at være hjemme hele dagen.",
    "Det er ikke muligt at booke mere end tre måneder frem.", "Der er ikke nogen skjulte omkostninger.",
    "Nej, vi har ikke lukket. Vi har bare travlt lige nu.", "Jeg kan desværre ikke give rabat.",
    "Vi kan ikke garantere, at farven bliver helt den samme.", "Nej, tiden er ikke flyttet. Den står stadig på tirsdag.",
    "Det er ikke dig, der skal betale for fejlen.", "Jeg har ikke fået et svar fra leverandøren endnu.",
    "Nej, vi kommer ikke uden at ringe først.", "Den ydelse har vi desværre stoppet med.",
    "Det kan jeg ikke svare på, men en medarbejder ringer dig op.", "Nej, du har ikke misset noget.",
    "Vi arbejder ikke med den type materiale.", "Det er ikke nødvendigt at sende billeder.",
    "Jeg beklager, men vi er fuldt booket i dag.", "Nej, prisen stiger ikke, hvis det tager længere tid.",
    "Vi har desværre ikke plads til flere kunder i den uge.", "Den oplysning har jeg ikke.",
    "Nej, det er ikke et abonnement.", "Du bliver ikke trukket noget, før opgaven er udført.",
]

NAVNE = [
    "Aabenraa", "Ringkøbing", "Skive", "Holstebro", "Viborg", "Silkeborg", "Horsens", "Vejle", "Kolding", "Haderslev",
    "Sønderborg", "Tønder", "Ribe", "Varde", "Herning", "Thisted", "Hjørring", "Brønderslev", "Aalborg", "Hobro",
    "Grenaa", "Ebeltoft", "Odder", "Skanderborg", "Fredericia", "Middelfart", "Odense", "Nyborg", "Faaborg",
    "Svendborg", "Rudkøbing", "Nakskov", "Maribo", "Nykøbing Falster", "Vordingborg", "Næstved", "Slagelse",
    "Korsør", "Kalundborg", "Holbæk", "Roskilde", "Køge", "Hillerød", "Helsingør", "Frederikssund", "Ballerup",
    "Glostrup", "Hvidovre", "Valby", "Nørrebro", "Amager", "Rønne", "Nexø", "Læsø", "Samsø", "Ærøskøbing",
]
FORNAVNE = ["Mette", "Søren", "Anne", "Jens", "Lone", "Niels", "Hanne", "Mads", "Karen", "Rasmus", "Birgitte", "Kasper",
            "Pia", "Morten", "Lise", "Anders", "Camilla", "Thomas", "Susanne", "Mikkel", "Tove", "Frederik", "Inger", "Jonas"]
EFTERNAVNE = ["Nielsen", "Jensen", "Hansen", "Pedersen", "Andersen", "Christensen", "Larsen", "Sørensen", "Rasmussen",
              "Jørgensen", "Madsen", "Kristensen", "Olsen", "Thomsen", "Poulsen", "Johansen", "Møller", "Mortensen"]
GADER = ["Østergade", "Vestergade", "Nørregade", "Søndergade", "Kirkevej", "Skovvej", "Møllevej", "Stationsvej",
         "Bøgevej", "Egevej", "Strandvejen", "Havnegade", "Bakkedraget", "Engvej", "Rosenvænget", "Algade"]
UGEDAGE = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag"]
MÅNEDER = ["januar", "februar", "marts", "april", "maj", "juni", "juli", "august", "september", "oktober",
           "november", "december"]


def generated(rng: random.Random) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for _ in range(40):  # amounts, quantities
        kr = rng.choice([rng.randrange(95, 995, 5), rng.randrange(1000, 25000, 25), rng.randrange(25000, 250000, 500)])
        out.append(("tal", rng.choice([
            f"Det koster {kr:,} kroner inklusive moms.", f"Prisen ligger på omkring {kr:,} kroner.",
            f"Beløbet er {kr:,} kr., og det skal betales inden fjorten dage.", f"Tilbuddet lyder på {kr:,} kroner i alt.",
            f"Du har {rng.randrange(2, 40)} dage til at betale.", f"Vi skal bruge {rng.randrange(2, 120)} kvadratmeter materiale.",
            f"Der er {rng.randrange(2, 19)} ledige tider i næste uge.", f"Ordrenummeret er {rng.randrange(1000, 99999)}.",
        ]).replace(",", ".")))
    for _ in range(40):  # dates and times
        d, mo = rng.randrange(1, 29), rng.choice(MÅNEDER)
        h, mi = rng.randrange(7, 18), rng.choice([0, 15, 30, 45])
        out.append(("tid_dato", rng.choice([
            f"Vi har en tid {rng.choice(UGEDAGE)} den {d}. {mo} klokken {h}.{mi:02d}.",
            f"Montøren kommer den {d}. {mo} mellem kl. {h} og kl. {h + 2}.",
            f"Din aftale er flyttet til {rng.choice(UGEDAGE)} kl. {h}.{mi:02d}.",
            f"Fakturaen forfalder den {d}. {mo}.", f"Vi har lukket fra den {d}. til den {min(28, d + 7)}. {mo}.",
            f"Kan du {rng.choice(UGEDAGE)} klokken {h}?", f"Vi åbner kl. {h}.{mi:02d} i morgen.",
        ])))
    for _ in range(25):  # phone numbers and e-mail
        n = " ".join(f"{rng.randrange(10, 100)}" for _ in range(4))
        fn, en = rng.choice(FORNAVNE).lower(), rng.choice(EFTERNAVNE).lower().replace("ø", "oe").replace("å", "aa")
        out.append(("telefon_email", rng.choice([
            f"Mit nummer er {n}.", f"Du kan ringe til os på {n}.", f"Jeg gentager lige nummeret: {n}.",
            f"Du kan skrive til {fn}@{en}.dk.", f"Mailen er {fn}.{en}@mail.dk.",
        ])))
    for _ in range(40):  # names and places
        out.append(("navne_steder", rng.choice([
            f"Adressen er {rng.choice(GADER)} {rng.randrange(1, 120)} i {rng.choice(NAVNE)}.",
            f"Kunden hedder {rng.choice(FORNAVNE)} {rng.choice(EFTERNAVNE)}.",
            f"Vi har en opgave i {rng.choice(NAVNE)} og en i {rng.choice(NAVNE)} i dag.",
            f"Spørg efter {rng.choice(FORNAVNE)}, når du kommer.",
            f"Jeg sætter {rng.choice(FORNAVNE)} {rng.choice(EFTERNAVNE)} på sagen.",
        ])))
    return out


def build() -> dict:
    from app.modules.voices import danish

    rng = random.Random(2026)
    testset = {json.loads(x)["text"] for x in (HERE.parent / "eval" / "testset_da.jsonl").read_text().splitlines() if x}
    std: list[tuple[str, str]] = [("hilsen", t) for t in HILSNER] + [("spørgsmål", t) for t in SPØRGSMÅL]
    std += [("forklaring", t) for t in FORKLARINGER] + [("forbehold", t) for t in FORBEHOLD] + generated(rng)
    std += KORT  # the short manuscript is part of the standard one
    seen, rows = set(), []
    for cat, text in std:
        if text in seen:
            continue
        seen.add(text)
        rows.append((cat, text))
    while len(rows) < 400:  # top up with more generated numbers/names (still deterministic)
        for cat, text in generated(rng):
            if text not in seen and len(rows) < 400:
                seen.add(text)
                rows.append((cat, text))
    out = {}
    for name, items in (("kort", KORT), ("standard", rows)):
        sentences = []
        for i, (cat, text) in enumerate(items, 1):
            assert text not in testset, text
            spoken = danish.normalize(text.format(firma="Firma", ydelse="ydelsen", by="byen"))
            sentences.append({"id": f"{name}-{i:03d}", "category": cat, "text": text, "spoken_hint": spoken})
        out[name] = {"id": f"da_{name}", "language": "da-DK", "version": 1, "instructions": INSTRUCTIONS,
                     "placeholders": ["firma", "ydelse", "by"], "sentences": sentences,
                     "estimated_minutes": round(sum(len(s["text"]) for s in sentences) / 14 / 60, 1)}
        (HERE / f"da_{name}.json").write_text(json.dumps(out[name], ensure_ascii=False, indent=1) + "\n")
    return out


if __name__ == "__main__":
    o = build()
    print({k: (len(v["sentences"]), v["estimated_minutes"]) for k, v in o.items()})
