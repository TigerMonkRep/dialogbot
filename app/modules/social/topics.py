"""What Dialogbot may say about itself on social media.

Everything here mirrors what dialogbot.dk already claims (web/public/llms.txt, web/src/lib/industries.ts): the facts
are the only source of numbers and promises, for both the hand-written fallback copy and the AI generator. Change a
price or a promise on the website and change it here too; `tests/test_social.py` pins the prices.

A `Topic` is a brief, not a finished post. `content.py` turns it into three different posts (Facebook, Instagram,
TikTok), either by asking the AI provider or, when that is unavailable or its answer fails the checks, from the
hand-written hooks and points below.
"""
from __future__ import annotations

from dataclasses import dataclass

# Verified facts. The AI prompt contains exactly these lines and nothing else about the company.
FACTS: tuple[str, ...] = (
    "Dialogbot er en dansk AI-receptionist, AI-telefonsvarer og chatbot til små og mellemstore virksomheder.",
    "Den tager telefonen og chatten døgnet rundt.",
    "Den svarer kun ud fra den viden, virksomheden selv har godkendt, og gætter aldrig på priser, tider eller vilkår.",
    "Den booker, flytter og aflyser tider og sender SMS-bekræftelser.",
    "Den giver en kort opsummering af hver henvendelse.",
    "Pris ekskl. moms: fast abonnement 1.495 kr. om måneden, eller 149 kr. pr. godkendt henvendelse.",
    "Ingen binding og intet opstartsgebyr.",
    "Gratis personlig opsætning, cirka en halv time.",
    "Virksomheder kan beholde deres eget telefonnummer og viderestille til Dialogbot.",
    "En AI-telefonsvarer taler med kunden i stedet for at bede om en besked.",
    "Chatbot til hjemmesiden med samme godkendte viden som telefonen.",
    "På dialogbot.dk kan man bede om at blive ringet op af Dialogbot for at høre, hvordan den tager telefonen (kræver samtykke).",
    "Dialogbot hører til i Aarhus, Danmark.",
)

# The only kroner amounts a post may mention (as written on the website).
ALLOWED_AMOUNTS: frozenset[str] = frozenset({"1.495", "149"})

PLATFORMS = ("facebook", "instagram", "tiktok")


@dataclass(frozen=True)
class Topic:
    key: str
    path: str  # on dialogbot.dk
    angle: str  # one sentence for the AI: what this post is about
    hooks: dict[str, str]  # per platform: the line that stops the scroll (also the big text on the first image)
    points: tuple[str, str, str]  # three short, true statements (one per carousel slide)
    proof: str  # one sentence that makes the call to action safer to click
    tags: tuple[str, ...]  # topic hashtags, without '#'
    kicker: str  # small label above the headline on the images


TOPICS: tuple[Topic, ...] = (
    Topic(
        key="missed_calls", path="/ai-receptionist", kicker="Ubesvarede opkald",
        angle="Når ejeren er optaget, ringer kunden videre til en anden. Dialogbot tager telefonen i stedet.",
        hooks={"facebook": "Hvem tager telefonen, når du står midt i en opgave?",
               "instagram": "Hver gang telefonen ringer ud, ringer kunden til en anden.",
               "tiktok": "Ringer din telefon, mens du har hænderne fulde?"},
        points=("Dialogbot tager telefonen og chatten døgnet rundt",
                "Svarer kun ud fra den viden, du selv har godkendt",
                "Du får en kort opsummering af hver henvendelse"),
        proof="Ingen binding og intet opstartsgebyr.", tags=("ubesvaredeopkald", "telefonpasning")),
    Topic(
        key="how_it_works", path="/viden/viderestil-telefonen", kicker="Kom i gang",
        angle="Tre enkle trin fra opsætning til en telefon, der passer sig selv.",
        hooks={"facebook": "Sådan kommer du i gang med Dialogbot på cirka en halv time",
               "instagram": "Tre trin fra ringende telefon til rolig hverdag",
               "tiktok": "3 trin, og din telefon passer sig selv"},
        points=("Gratis personlig opsætning sammen med dig",
                "Du godkender den viden, Dialogbot må svare ud fra",
                "Du beholder dit nummer og viderestiller til Dialogbot"),
        proof="Opsætningen tager cirka en halv time.", tags=("opsætning", "digitalisering")),
    Topic(
        key="pricing", path="/priser", kicker="Priser",
        angle="Åbenhed om prisen: abonnement eller betaling pr. godkendt henvendelse, ingen binding.",
        hooks={"facebook": "Priser uden overraskelser",
               "instagram": "1.495 kr. om måneden. Eller 149 kr. pr. henvendelse.",
               "tiktok": "Hvad koster en AI-receptionist? Det her."},
        points=("Fast abonnement: 1.495 kr. om måneden ekskl. moms",
                "Eller 149 kr. pr. godkendt henvendelse ekskl. moms",
                "Ingen binding og intet opstartsgebyr"),
        proof="Alle priser er ekskl. moms.", tags=("pris", "ingenbinding")),
    Topic(
        key="approved_knowledge", path="/ai-receptionist", kicker="Du bestemmer",
        angle="Dialogbot svarer kun ud fra det, ejeren har godkendt, og gætter aldrig.",
        hooks={"facebook": "En AI, der ikke gætter",
               "instagram": "Din AI-receptionist siger kun det, du har godkendt.",
               "tiktok": "Kan en AI-receptionist finde på noget? Ikke her."},
        points=("Du godkender viden: priser, åbningstider og tilbud",
                "Dialogbot svarer kun ud fra den viden",
                "Ved tvivl lover den, at en medarbejder vender tilbage"),
        proof="Ingen gæt på priser, tider eller vilkår.", tags=("trygai", "kundeservice")),
    Topic(
        key="booking", path="/ai-receptionist", kicker="Booking",
        angle="Dialogbot booker, flytter og aflyser tider og sender SMS-bekræftelse, mens ejeren arbejder.",
        hooks={"facebook": "Book, flyt og aflys – uden at du løfter røret",
               "instagram": "Tider bliver booket, mens du arbejder.",
               "tiktok": "Kunden ringer. Tiden bliver booket. Du gjorde ingenting."},
        points=("Booker, flytter og aflyser tider",
                "Sender SMS-bekræftelse til kunden",
                "Du får en kort opsummering af hver henvendelse"),
        proof="Dialogbot tager telefonen og chatten døgnet rundt.", tags=("booking", "onlinebooking")),
    Topic(
        key="summaries", path="/ai-receptionist", kicker="Overblik",
        angle="Hver samtale ender i en kort opsummering, så intet ryger i glemmebogen.",
        hooks={"facebook": "Slut med at gætte, hvad kunden ringede om",
               "instagram": "En kort opsummering af hver eneste henvendelse",
               "tiktok": "Sådan ser en henvendelse ud, når en AI har taget den"},
        points=("Hver samtale ender i en kort opsummering",
                "Du får besked om nye henvendelser",
                "Intet ryger i glemmebogen"),
        proof="Du ringer tilbage til en kunde, hvor sagen allerede er forstået.", tags=("overblik", "kundeservice")),
    Topic(
        key="voicemail_vs_ai", path="/viden/ai-telefonsvarer-eller-telefonpasning", kicker="AI-telefonsvarer",
        angle="En AI-telefonsvarer taler med kunden i stedet for at bede om en besked.",
        hooks={"facebook": "Telefonsvarer eller telefonpasning? Der findes en tredje vej.",
               "instagram": "Hvorfor lægge en besked, når man kan få et svar?",
               "tiktok": "Ingen gider tale med en telefonsvarer"},
        points=("En AI-telefonsvarer taler med kunden i stedet for at bede om en besked",
                "Kunden får hjælp med det samme",
                "Du får opsummeringen bagefter"),
        proof="Læs forskellen på AI-telefonsvarer og telefonpasning.", tags=("telefonsvarer", "aitelefonsvarer")),
    Topic(
        key="chatbot", path="/chatbot", kicker="Chatbot",
        angle="Dansk chatbot til hjemmesiden med samme godkendte viden som telefonen.",
        hooks={"facebook": "Samme viden på telefonen og på hjemmesiden",
               "instagram": "Chatbot til din hjemmeside – med samme hjerne som telefonen",
               "tiktok": "Din hjemmeside kan svare kunderne. Hele døgnet."},
        points=("Dansk chatbot til din hjemmeside",
                "Samme godkendte viden som telefonen",
                "Besøgende kan bede om at blive kontaktet"),
        proof="Én viden, to kanaler.", tags=("chatbot", "hjemmeside")),
    Topic(
        key="keep_number", path="/viden/viderestil-telefonen", kicker="Dit nummer",
        angle="Man behøver ikke skifte telefonnummer; man viderestiller til Dialogbot.",
        hooks={"facebook": "Du behøver ikke skifte telefonnummer",
               "instagram": "Dit nummer. Din hverdag. Bare uden missede opkald.",
               "tiktok": "Skal du skifte nummer for at få en AI-receptionist? Nej."},
        points=("Behold dit nuværende nummer",
                "Viderestil til Dialogbot",
                "Vi hjælper dig med opsætningen"),
        proof="Gratis personlig opsætning på cirka en halv time.", tags=("viderestilling", "telefon")),
    Topic(
        key="demo_call", path="/", kicker="Prøv selv",
        angle="Man kan selv bede om at blive ringet op af Dialogbot og høre, hvordan den tager telefonen.",
        hooks={"facebook": "Hør Dialogbot tage telefonen – live",
               "instagram": "Hør det selv: Dialogbot ringer dig op",
               "tiktok": "Lad en AI ringe dig op og hør, hvordan den svarer"},
        points=("Skriv dit nummer på dialogbot.dk",
                "Sæt kryds ved samtykke",
                "Dialogbot ringer og viser, hvordan den tager telefonen"),
        proof="Der ringes kun, hvis du selv beder om det.", tags=("prøvselv", "demo")),
    Topic(
        key="industry_haandvaerkere", path="/ai-receptionist/haandvaerkere", kicker="Håndværkere",
        angle="Håndværkeren står på stigen eller under en vask og kan ikke tage telefonen; Dialogbot samler opgave og "
              "adresse og booker besigtigelser.",
        hooks={"facebook": "VVS, el, tømrer, maler: tag telefonen fra stigen",
               "instagram": "Mester står på stigen. Telefonen ringer. Hvad nu?",
               "tiktok": "Når du er under en vask, og telefonen ringer"},
        points=("Tager telefonen, når I står med hænderne fulde",
                "Samler opgave, adresse og hvor meget det haster",
                "Booker besigtigelser direkte i kalenderen"),
        proof="Du ringer tilbage til en varm kunde med alle oplysninger klar.",
        tags=("håndværker", "vvs", "tømrer", "elektriker")),
    Topic(
        key="industry_klinikker", path="/ai-receptionist/klinikker", kicker="Klinikker",
        angle="Telefonen ringer midt i behandlinger; Dialogbot booker, flytter og aflyser tider døgnet rundt.",
        hooks={"facebook": "Aflast receptionen i morgentimerne",
               "instagram": "Patienten ringer. Tiden bliver flyttet. Receptionen ser det ikke engang.",
               "tiktok": "Receptionen drukner i opkald hver morgen"},
        points=("Booker, flytter og aflyser tider døgnet rundt",
                "Sender bekræftelse på SMS",
                "Giver aldrig behandlingsråd – henviser til klinikken"),
        proof="I bestemmer selv reglerne for, hvad der må siges.", tags=("klinik", "tandlæge", "fysioterapeut")),
    Topic(
        key="industry_frisoerer", path="/ai-receptionist/frisoerer", kicker="Frisører og saloner",
        angle="Man kan ikke tage telefonen med saksen i hånden; Dialogbot booker tider, også om aftenen.",
        hooks={"facebook": "Book tider uden at afbryde kunden i stolen",
               "instagram": "Saksen i hånden. Telefonen ringer. Dialogbot tager den.",
               "tiktok": "Telefonen ringer, mens du har saksen i hånden"},
        points=("Booker tider, også om aftenen og i weekenden",
                "Sender SMS-bekræftelse",
                "Svarer på priser og åbningstider ud fra din egen prisliste"),
        proof="Du skal aldrig afbryde en kunde i stolen.", tags=("frisør", "salon", "barber")),
    Topic(
        key="industry_autovaerksteder", path="/ai-receptionist/autovaerksteder", kicker="Autoværksteder",
        angle="Mekanikerne er i værkstedet; Dialogbot tager imod bestillinger på service, syn og dækskift.",
        hooks={"facebook": "Service, syn og dækskift – uden at mekanikeren forlader bilen",
               "instagram": "Vinterdæk-sæsonen: telefonen ringer konstant. Dialogbot tager den.",
               "tiktok": "Mekanikeren har olie til albuerne. Hvem tager telefonen?"},
        points=("Tager imod bestillinger på service, syn og dækskift",
                "Noterer bil, nummerplade og problem",
                "Booker tider og sender SMS"),
        proof="Den stiller ingen diagnose; den samler oplysningerne, så I ringer tilbage forberedt.",
        tags=("autoværksted", "dækskift", "bil")),
    Topic(
        key="industry_raadgivere", path="/ai-receptionist/raadgivere", kicker="Rådgivere og kontorer",
        angle="Rådgiverne sidder i møder; Dialogbot kvalificerer nye henvendelser og booker indledende møder.",
        hooks={"facebook": "Nye kunder, der ringer, mens du sidder i møde",
               "instagram": "Den nye kunde fik en telefonsvarer. Og ringede til en anden.",
               "tiktok": "Du sidder i møde. Den nye kunde ringer."},
        points=("Kvalificerer nye henvendelser med jeres egne spørgsmål",
                "Booker indledende møder",
                "Sender en klar opsummering til den rette rådgiver"),
        proof="Den lover aldrig noget, I ikke har godkendt.", tags=("rådgiver", "advokat", "revisor", "ejendomsmægler")),
    Topic(
        key="industry_restauranter", path="/ai-receptionist/restauranter", kicker="Restauranter og hoteller",
        angle="Telefonen ringer midt i frokost- og aftenrush; Dialogbot tager imod bordbestillinger og forespørgsler.",
        hooks={"facebook": "Bordbestillinger i myldretiden – uden at afbryde servicen",
               "instagram": "Aftenrush. Telefonen ringer. Personalet bliver ved gæsterne.",
               "tiktok": "Aftenrush og ringende telefon – hvem tager den?"},
        points=("Tager imod bordbestillinger, også i myldretiden og efter lukketid",
                "Svarer på åbningstider, menu og parkering",
                "Samler selskabs- og cateringforespørgsler med antal, dato og ønsker"),
        proof="Personalet kan blive ved gæsterne.", tags=("restaurant", "café", "hotel", "catering")),
)

TOPICS_BY_KEY = {t.key: t for t in TOPICS}
