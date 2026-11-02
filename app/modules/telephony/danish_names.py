"""Common Danish given and family names, for the transcriber's custom vocabulary (Speechmatics takes up to 1,000
entries with "sounds like" alternatives). A caller's name said on its own over a phone line is the hardest thing a
Danish speech model hears – "André" became "Andreas", "Pernille" became "Panel" – and a vocabulary of the names
Danes actually have is the one lever that moves it. The lists are ordered by how common the name is (Danmarks
Statistik's name counts, from memory of the public tables; exact order is not important), so a cap keeps the most
common ones. SOUNDS_LIKE adds spellings for names the models confuse."""
from __future__ import annotations

GIVEN = """
Anne Kirsten Mette Hanne Helle Anna Susanne Lene Maria Marianne Lone Camilla Pia Louise Charlotte Jette Tina Gitte
Bente Inge Karen Bodil Birgitte Jytte Dorthe Ida Emma Sofie Freja Laura Julie Ella Mathilde Caroline Katrine Sara
Line Rikke Signe Maja Nanna Cecilie Amalie Clara Josefine Frederikke Alma Agnes Olivia Isabella Victoria Astrid Liv
Nora Esther Karla Lærke Mille Emilie Nicoline Sille Josephine Thea Alberte Malou Vigga Marie Lise Else Grethe Ruth
Inger Ellen Lis Birthe Tove Ingrid Ulla Annette Lisbeth Vibeke Britta Bitten Majbritt Maibritt Pernille Trine Tine
Ditte Stine Lotte Liselotte Merete Annemette Heidi Jeanette Tanja Rie Søs Åse Aase Sanne Sine Nina Malene Mia Maiken
Ane Benedikte Christina Kristina Christine Eva Lena Linda Monica Gunhild Gudrun Solveig Yrsa Hjørdis Ragnhild
Peter Lars Michael Jens Thomas Henrik Søren Christian Jan Martin Niels Anders Morten Jesper Hans Mads Rasmus Jørgen
Ole Per Kim Jakob Jacob Frederik Mikkel Kasper Erik Steen Poul Flemming Mogens Bent Kurt Svend Knud Palle Torben
Claus Klaus Carsten Allan Brian Kenneth René Rene Andreas Andre André Jonas Simon Emil Oliver Noah William Lucas
Oscar Victor Malthe Magnus Alexander Elias Sebastian Tobias Nikolaj Nicolai Nicklas Niklas Mathias Matias Marcus
Markus Daniel David Benjamin Philip Filip Johan Johannes Carl Karl Valdemar Villads Aksel Axel Storm August Alfred
Anton Arthur Theo Theodor Viggo Vilfred Bertram Felix Hugo Lauge Loke Albert Elliot Liam Milas Kjeld Keld Jørn Bjørn
Thorbjørn Torbjørn Bjarke Bjarne Preben Aage Åge Ove Ejvind Ejner Egon Verner Villy Leif Finn Frank Jørgen Arne
Gunnar Kaj Tage Ib Asger Rolf Thor Tor Bo Jon Jan Kenn Dan Jens-Christian Hans-Henrik Jean Ulrik Troels Rune Søren
Stig Sten Henning Hugo Helge Holger Jens-Peter Bjørn Jes Jeppe Jesper Casper Kristian Kristoffer Christoffer Nikolas
Patrick Pelle Rasmus Robert Ronnie Steffen Tommy Tonny Torsten Thorsten Thøger Vagn Viktor Ebbe Esben Espen Gorm
""".split()

FAMILY = """
Nielsen Jensen Hansen Andersen Pedersen Christensen Larsen Sørensen Rasmussen Jørgensen Petersen Madsen Kristensen
Olsen Thomsen Christiansen Poulsen Johansen Møller Mortensen Knudsen Jakobsen Jacobsen Mikkelsen Frederiksen
Laursen Henriksen Lund Schmidt Eriksen Holm Kristiansen Clausen Simonsen Svendsen Andreasen Iversen Jeppesen
Mogensen Jespersen Nissen Lauridsen Frandsen Østergaard Vestergaard Nørgaard Søndergaard Kjær Kjærgaard Kjeldsen
Thøgersen Schou Skov Skou Krogh Krog Bach Bak Bech Beck Friis Fischer Winther Vinther Dahl Dam Lind Bruun Brun Bang
Kofoed Koch Mathiesen Mathiasen Hald Toft Lassen Carlsen Karlsen Steffensen Gregersen Villadsen Ravn Riis Hoffmann
Hvid Thorsen Thuesen Troelsen Villumsen Vestergård Nygaard Nygård Lykke Bentsen Brandt Bundgaard Dalsgaard Degn
Enevoldsen Fogh Gade Gram Hedegaard Hjorth Holst Hougaard Ibsen Isaksen Justesen Kaae Kirkegaard Kragh Ladefoged
Lauritsen Leth Lindberg Lorentzen Lundgaard Mørch Nedergaard Nørregaard Overgaard Pallesen Paulsen Qvist Rask Riber
Sand Schultz Schrøder Sloth Smed Storm Svane Søgaard Tang Terkelsen Thygesen Vang Vang Wulff Zachariassen Ørum
""".split()

# Other ways a name sounds (never another real name – that would steal its hits), so the right spelling wins.
SOUNDS_LIKE: dict[str, list[str]] = {
    "André": ["andre", "andræ", "an-dre"], "Kjeld": ["kell", "keld", "kjell"], "Keld": ["kell", "kjeld"],
    "Majbritt": ["maj brit", "mai brit", "maibrit"], "Thorbjørn": ["tor bjørn", "torbjørn"], "Ditte": ["dit te", "ditte"],
    "Jørn": ["jørn", "jøn", "jöärn"], "Søs": ["søs", "sus", "søss"], "Bjarke": ["bjarke", "bjarki", "bjark"],
    "Liselotte": ["lise lotte", "lisa lotte"], "Aage": ["åge", "oge", "o-ge"], "Åge": ["åge", "oge"], "Åse": ["åse", "ose", "aase"],
    "Aase": ["åse", "ose"], "Pernille": ["per nille", "pernil", "pernilje"], "Preben": ["pre ben", "præben"],
    "Mathilde": ["matilde", "mattille"], "Kjærgaard": ["kærgård", "kjærgård", "kær gård"], "Thøgersen": ["tøgersen", "tøjersen"],
    "Schou": ["skou", "sko", "skow"], "Trøjborg": ["trøjborg", "troiborg", "trojborg"], "Kjær": ["kær"], "Hjørdis": ["jørdis"],
    "Thea": ["tea"], "Theo": ["teo"], "Kaj": ["kai"], "Lærke": ["lerke", "lærke"],
}


def vocabulary(limit: int = 700) -> list[dict]:
    """Custom-vocabulary items for Speechmatics ({content, soundsLike?}), most common names first, de-duplicated."""
    out: list[dict] = []
    seen: set[str] = set()
    for name in [*GIVEN, *FAMILY]:
        if name.lower() in seen:
            continue
        seen.add(name.lower())
        item: dict = {"content": name}
        if name in SOUNDS_LIKE:
            item["soundsLike"] = SOUNDS_LIKE[name]
        out.append(item)
        if len(out) >= limit:
            break
    return out
