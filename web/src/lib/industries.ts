/** Industry landing pages (/ai-receptionist/[branche]). Copy mirrors the sales playbooks in app/modules/sales/script.py;
 *  every claim is something Dialogbot does today. */
export type Industry = {
  slug: string; name: string; plural: string; examples: string;
  /** H1 on the page. */
  title: string;
  /** <title> (≤ 54 characters, " | Dialogbot" is appended) and meta description (120–160 characters). */
  seoTitle: string; description: string;
  /** Last content change: sitemap lastmod. */
  updated: string;
  pain: string; scenario: [string, string][]; benefits: string[]; objection: [string, string]; faq: [string, string][];
};

export const INDUSTRIES: Industry[] = [
  {
    slug: "haandvaerkere", name: "håndværkere", plural: "Håndværkere", examples: "VVS, el, tømrer, maler, murer, gulv og tag",
    title: "AI-receptionist til håndværkere – tag telefonen fra stigen",
    seoTitle: "AI-receptionist til håndværkere – VVS, el og tømrer", updated: "2026-10-08",
    description: "Dialogbot tager telefonen for VVS'eren, elektrikeren, tømreren og maleren, når I står med hænderne fulde – samler opgave og adresse og booker besigtigelser.",
    pain: "Mester står på stigen eller under en vask og kan ikke tage telefonen. Hvert ubesvaret opkald er typisk en kunde, der ringer videre til den næste håndværker på Google.",
    scenario: [["Kunde", "Hej, jeg har et utæt toilet, kan I komme og kigge på det?"], ["Dialogbot", "Det kan vi godt. Hvilken adresse drejer det sig om, og haster det?"], ["Kunde", "Vesterbrogade 12 i Aarhus – helst i denne uge."], ["Dialogbot", "Tak. Jeg har noteret det, og mester ringer dig op i dag og aftaler tidspunktet."]],
    benefits: ["Tager telefonen, når I står med hænderne fulde", "Samler opgave, adresse og hvor meget det haster i én besked til mester", "Booker besigtigelser direkte i kalenderen", "Følger op på de tilbud, I har sendt"],
    objection: ["Mine kunder vil tale med mig selv.", "Det skal de også. Dialogbot tager kun de opkald, I ikke selv når, og sørger for, at I ringer tilbage til en varm kunde med alle oplysninger klar."],
    faq: [["Kan Dialogbot give pris på en opgave?", "Kun hvis I har lagt prisen ind og godkendt den, fx en fast pris pr. m². Ellers noterer den opgaven og lover, at mester vender tilbage med et tilbud."], ["Kan den booke besigtigelser?", "Ja, ud fra jeres åbningstider og bookingregler – og den spørger altid kunden om lov først."]],
  },
  {
    slug: "klinikker", name: "klinikker", plural: "Klinikker", examples: "tandlæge, fysioterapeut, kiropraktor, psykolog og dyrlæge",
    title: "AI-receptionist til klinikker – book tider døgnet rundt",
    seoTitle: "AI-receptionist til klinikker – booking døgnet rundt", updated: "2026-10-08",
    description: "Dialogbot booker, flytter og aflyser tider for tandlægen, fysioterapeuten og kiropraktoren – også uden for åbningstid – og aflaster receptionen.",
    pain: "Telefonen ringer midt i behandlinger, og receptionen er presset om morgenen. Patienter, der ikke kommer igennem, finder en anden klinik.",
    scenario: [["Patient", "Jeg skal flytte min tid på torsdag."], ["Dialogbot", "Det kan jeg hjælpe med. Den næste ledige tid er fredag kl. 9.30 eller mandag kl. 14. Hvad passer bedst?"], ["Patient", "Fredag."], ["Dialogbot", "Så er din tid flyttet til fredag kl. 9.30. Vil du have en bekræftelse på SMS?"]],
    benefits: ["Booker, flytter og aflyser tider døgnet rundt", "Sender bekræftelse på SMS", "Aflaster receptionen i morgentimerne", "Giver aldrig behandlingsråd – den henviser til klinikken"],
    objection: ["Hvad med fortrolighed?", "Assistenten spørger kun om det, der skal til for at booke. I bestemmer selv reglerne, og samtalerne kan slettes efter jeres egne frister."],
    faq: [["Giver Dialogbot sundhedsfaglige råd?", "Nej. Den booker og svarer på praktiske spørgsmål og henviser altid til klinikken ved faglige spørgsmål."], ["Kan patienter flytte og aflyse selv?", "Ja. Dialogbot finder aftalen ud fra telefonnummer eller navn og flytter eller aflyser, når patienten har sagt ja."]],
  },
  {
    slug: "frisoerer", name: "frisører og saloner", plural: "Frisører og saloner", examples: "frisør, barber, kosmetolog, negle og massage",
    title: "AI-receptionist til frisører og saloner – book uden at slippe saksen",
    seoTitle: "AI-receptionist til frisører og saloner", updated: "2026-10-08",
    description: "Dialogbot tager telefonen for frisøren, barberen og skønhedsklinikken og booker tider – også om aftenen – så I aldrig afbryder en kunde i stolen.",
    pain: "Man kan ikke tage telefonen med saksen i hånden, og mange kunder ringer om aftenen, når salonen er lukket.",
    scenario: [["Kunde", "Har I en tid til herreklip i morgen efter kl. 16?"], ["Dialogbot", "Der er en ledig tid i morgen kl. 16.30. Skal jeg reservere den i dit navn?"], ["Kunde", "Ja tak, det er Mads."], ["Dialogbot", "Så er du booket i morgen kl. 16.30, Mads. Du får en bekræftelse på SMS."]],
    benefits: ["Booker tider, også om aftenen og i weekenden", "Sender SMS-bekræftelse", "Svarer på priser og åbningstider ud fra jeres egen prisliste", "I skal aldrig afbryde en kunde i stolen"],
    objection: ["Vi har allerede online booking.", "Super – mange ringer alligevel. Dialogbot tager de opkald og booker i samme kalender, så ingen falder imellem."],
    faq: [["Kan Dialogbot læse vores prisliste op?", "Ja, når I har lagt den ind og godkendt den. Den svarer kun ud fra godkendt viden."], ["Hvad sker der om aftenen?", "Dialogbot tager telefonen døgnet rundt og booker inden for jeres åbningstider."]],
  },
  {
    slug: "autovaerksteder", name: "autoværksteder", plural: "Autoværksteder", examples: "autoværksted, dækcenter, pladeværksted og bilforhandler",
    title: "AI-receptionist til autoværksteder – service, syn og dækskift",
    seoTitle: "AI-receptionist til autoværksteder og dækcentre", updated: "2026-10-08",
    description: "Dialogbot tager imod bestillinger på service, syn og dækskift, noterer bil og nummerplade og booker tider, mens mekanikerne arbejder.",
    pain: "Mekanikerne er ude i værkstedet, og telefonen ringer konstant om syn, service og dækskift.",
    scenario: [["Kunde", "Jeg skal have skiftet til vinterdæk."], ["Dialogbot", "Det klarer vi. Hvilken bil drejer det sig om, og har du nummerpladen?"], ["Kunde", "En Golf, AB 12 345."], ["Dialogbot", "Tak. Der er en ledig tid onsdag kl. 8. Skal jeg booke den?"]],
    benefits: ["Tager imod bestillinger på service, syn og dækskift", "Noterer bil, nummerplade og problem", "Booker tider og sender SMS", "Svarer på åbningstider og priser fra jeres prisliste"],
    objection: ["Det er for teknisk til en robot.", "Den skal ikke diagnosticere bilen. Den samler oplysningerne, så mekanikeren ringer tilbage velforberedt."],
    faq: [["Kan Dialogbot stille en diagnose?", "Nej. Den samler oplysninger om bil og problem, så I kan ringe tilbage forberedt."], ["Kan den booke dækskift i højsæsonen?", "Ja, ud fra jeres ledige tider og bookingregler."]],
  },
  {
    slug: "raadgivere", name: "rådgivere og kontorer", plural: "Rådgivere og kontorer", examples: "advokat, revisor, ejendomsmægler, forsikring og IT-konsulent",
    title: "AI-receptionist til advokater, revisorer og rådgivere",
    seoTitle: "AI-receptionist til advokater, revisorer og rådgivere", updated: "2026-10-08",
    description: "Dialogbot kvalificerer nye henvendelser med jeres egne spørgsmål, booker indledende møder og sender en klar opsummering til den rette rådgiver.",
    pain: "Rådgiverne sidder i møder, og nye kunder, der ringer, møder en telefonsvarer og vælger en anden.",
    scenario: [["Kunde", "Jeg skal have hjælp til en bolighandel."], ["Dialogbot", "Det hjælper vi gerne med. Er det et køb eller et salg, og hvornår skal handlen være på plads?"], ["Kunde", "Et køb – inden for en måned."], ["Dialogbot", "Tak. Skal jeg booke et kort indledende møde, eller vil du ringes op af en rådgiver?"]],
    benefits: ["Kvalificerer nye henvendelser med jeres egne spørgsmål", "Booker indledende møder", "Sender en klar opsummering til den rette rådgiver", "Lover aldrig noget, I ikke har godkendt"],
    objection: ["Vores kunder forventer et menneske.", "Assistenten siger ærligt, at den er digital, og sørger for, at et menneske ringer tilbage med sagen allerede forstået."],
    faq: [["Giver Dialogbot juridisk eller økonomisk rådgivning?", "Nej. Den afklarer sagen kort og sender den til den rette rådgiver."], ["Kan den skelne mellem typer af sager?", "Ja, med de spørgsmål I godkender, fx køb eller salg, privat eller erhverv."]],
  },
  {
    slug: "restauranter", name: "restauranter, hoteller og caféer", plural: "Restauranter, hoteller og caféer", examples: "restaurant, café, hotel, kro, bed & breakfast og catering",
    title: "AI-receptionist til restauranter, hoteller og caféer",
    seoTitle: "AI-receptionist til restauranter, hoteller og caféer", updated: "2026-10-08",
    description: "Dialogbot tager imod bordbestillinger og forespørgsler i myldretiden og efter lukketid og svarer på menu, åbningstider og parkering.",
    pain: "Telefonen ringer midt i frokost- og aftenrush. Bordbestillinger, værelsesforespørgsler og selskaber går tabt, eller gæsterne booker et andet sted.",
    scenario: [["Gæst", "Kan vi få et bord til fire på lørdag kl. 19?"], ["Dialogbot", "Det noterer jeg gerne. Hvilket navn må jeg skrive, og er der allergier, vi skal kende til?"], ["Gæst", "Hansen – én er glutenallergiker."], ["Dialogbot", "Tak. Jeg har noteret bord til fire lørdag kl. 19 i navnet Hansen med glutenallergi."]],
    benefits: ["Tager imod bordbestillinger og forespørgsler, også i myldretiden og efter lukketid", "Svarer på åbningstider, menu, priser, parkering og indtjekning", "Samler selskabs- og cateringforespørgsler med antal, dato og ønsker", "Personalet kan blive ved gæsterne"],
    objection: ["Vi bruger allerede et bookingsystem.", "Fint – mange gæster ringer alligevel. Dialogbot tager de opkald, så personalet slipper for at afbryde servering eller reception."],
    faq: [["Kan Dialogbot tage imod selskaber og catering?", "Ja. Den samler antal, dato og ønsker og sender forespørgslen til den ansvarlige."], ["Kan den svare på menuen?", "Ja, når I har lagt menu og priser ind og godkendt dem."]],
  },
];

export const industryBySlug = (slug: string) => INDUSTRIES.find((i) => i.slug === slug);
