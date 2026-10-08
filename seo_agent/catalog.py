"""Videnbasen: hvert tjek har kategori, vægt, en forklaring på hvorfor det betyder noget og en konkret løsning.

Det er her 'eksperten' bor – rapporten bygger direkte på disse tekster.
"""
from __future__ import annotations

from dataclasses import dataclass

IDX, ONP, CON, TEK, SPD, SEC, MOB, SCH, SOC = (
    "Indeksering", "On-page", "Indhold", "Teknik", "Hastighed", "Sikkerhed", "Mobil", "Struktureret data", "Sociale medier",
)
CATEGORIES = [IDX, ONP, CON, TEK, SPD, SEC, MOB, SCH, SOC]


@dataclass(frozen=True)
class CheckInfo:
    id: str
    category: str
    title: str
    weight: int  # 1-10: hvor meget tjekket tæller i scoren
    why: str
    fix: str


def _build() -> dict[str, CheckInfo]:
    rows = [
        # --- Indeksering -------------------------------------------------------------------------
        ("page_status", IDX, "Sider svarer med 200 OK", 10,
         "Sider der giver 4xx/5xx kan ikke indekseres og spilder crawl-budget og linkværdi.",
         "Ret eller fjern interne links til fejlsider; sæt 301 fra flyttede sider til den nye adresse."),
        ("noindex", IDX, "Ingen utilsigtet noindex", 10,
         "En side med noindex (meta eller X-Robots-Tag) forsvinder fra Google, selv om den står i sitemap. "
         "Noindex på sider uden for sitemap (login, app, onboarding) regnes som bevidst og tæller ikke.",
         "Fjern noindex fra sider, der skal kunne findes – eller tag siden ud af sitemap, hvis den bevidst holdes ude."),
        ("robots_present", IDX, "robots.txt findes", 8,
         "robots.txt fortæller søgemaskiner, hvad de må crawle, og peger på sitemap.", "Opret /robots.txt (Next.js: src/app/robots.ts)."),
        ("robots_open", IDX, "robots.txt blokerer ikke hele sitet", 10,
         "'Disallow: /' for alle bots fjerner hele sitet fra søgeresultaterne.", "Fjern 'Disallow: /' og blokér kun private områder."),
        ("robots_sitemap", IDX, "robots.txt peger på sitemap", 4,
         "Sitemap-linjen gør det hurtigere for bots at finde alle sider.", "Tilføj 'Sitemap: https://…/sitemap.xml' i robots.txt."),
        ("robots_assets", IDX, "CSS/JS er ikke blokeret for bots", 4,
         "Google skal kunne hente CSS og JS for at rendere siden som en bruger ser den.", "Fjern Disallow for /_next/static og lignende."),
        ("sitemap_present", IDX, "XML-sitemap findes", 8,
         "Sitemap hjælper Google med at finde og prioritere alle indekserbare sider.", "Opret /sitemap.xml (Next.js: src/app/sitemap.ts) og indsend i Search Console."),
        ("sitemap_valid", IDX, "Sitemap er gyldig XML", 6,
         "Ugyldig XML ignoreres af Google.", "Ret sitemap-filen, så den følger sitemaps.org-formatet."),
        ("sitemap_urls_ok", IDX, "Alle sitemap-URL'er svarer 200 uden redirect", 7,
         "Sitemap med redirects eller fejl får Google til at miste tilliden til den.", "Fjern eller ret URL'er, der ikke svarer direkte med 200."),
        ("sitemap_lastmod", IDX, "Sitemap lastmod er troværdig", 2,
         "Hvis alle sider har 'lastmod = nu' ved hver forespørgsel, lærer Google at ignorere feltet.",
         "Sæt lastmod til sidens rigtige ændringsdato (fx ARTICLES[].published), ikke new Date()."),
        ("orphan_pages", IDX, "Ingen forældreløse sider", 3,
         "Sider i sitemap uden interne links modtager ingen linkværdi og vurderes som mindre vigtige.", "Link til siden fra relevante sider, menu eller footer."),
        ("broken_links", IDX, "Ingen døde interne links", 8,
         "Døde links skader brugeroplevelsen og spilder crawl-budget.", "Ret linket eller sæt en 301-redirect."),
        ("notfound_page", IDX, "Ukendte URL'er giver rigtig 404", 6,
         "Soft-404 (200 på en ikke-eksisterende side) forvirrer Google og skaber duplikeret indhold.", "Lad ukendte stier returnere HTTP 404 med en brugbar fejlside."),
        ("canonical_present", IDX, "Canonical-tag findes", 7,
         "Canonical forhindrer duplikeret indhold fra parametre og www/ikke-www.", "Tilføj <link rel=canonical> (Next.js: metadata.alternates.canonical)."),
        ("canonical_self", IDX, "Canonical peger på sidens egen endelige URL", 6,
         "Peger canonical andetsteds hen, bliver siden normalt ikke indekseret.", "Sæt canonical til den absolutte, endelige URL for siden."),
        # --- On-page -----------------------------------------------------------------------------
        ("title_present", ONP, "Title-tag findes", 10, "Title er den stærkeste on-page-faktor og overskriften i søgeresultatet.", "Tilføj en unik <title> med hovednøgleordet."),
        ("title_length", ONP, "Title er 30–65 tegn", 5, "For lange titler afkortes i Google, for korte udnytter ikke pladsen.", "Skriv titlen til 30–65 tegn (ca. 580 pixels) med nøgleordet først."),
        ("title_unique", ONP, "Titler er unikke", 6, "Ens titler får sider til at konkurrere mod hinanden.", "Giv hver side sin egen titel."),
        ("desc_present", ONP, "Meta description findes", 8, "Beskrivelsen er salgstekst i søgeresultatet og påvirker klikraten.", "Tilføj meta description (metadata.description)."),
        ("desc_length", ONP, "Meta description er 70–175 tegn", 4, "Afkortes ellers i søgeresultatet.", "Skriv 120–155 tegn med nøgleord og en opfordring."),
        ("desc_unique", ONP, "Meta descriptions er unikke", 5, "Duplikerede beskrivelser giver svage, ens søgeresultater.", "Skriv en unik beskrivelse pr. side."),
        ("h1_single", ONP, "Præcis én H1", 8, "H1 er sidens hovedoverskrift. Ingen eller flere forvirrer både bots og brugere.", "Brug én H1, der indeholder hovednøgleordet."),
        ("heading_order", ONP, "Overskrifter springer ikke niveauer over", 3, "Logisk H1→H2→H3 gør indholdet lettere at forstå for bots og skærmlæsere.", "Brug H2 under H1, H3 under H2 osv."),
        ("lang_attr", ONP, "Sprog er angivet (lang)", 4, "Hjælper søgemaskiner og skærmlæsere med at vælge sprog.", "Sæt <html lang=\"da\">."),
        ("url_quality", ONP, "Pæne URL'er", 2, "Korte, små bogstaver og bindestreger er lettere at forstå og dele.", "Brug små bogstaver, bindestreger og undgå parametre."),
        ("anchor_text", ONP, "Beskrivende linktekster", 3, "'Klik her' siger intet om målsiden – ankertekst er et rankingsignal.", "Brug linktekst, der beskriver målet."),
        ("internal_links", ONP, "Siden har interne links", 3, "Interne links fordeler linkværdi og hjælper brugeren videre.", "Link til relevante guides, brancher og prissiden."),
        ("keyword_focus", ONP, "Hovednøgleord står i title og H1", 3, "Det mest brugte emneord i selve indholdet (uden menu og footer) bør også stå i title og H1.", "Flet sidens hovedord ind i title og H1 – uden nøgleordsfyld."),
        # --- Indhold -----------------------------------------------------------------------------
        ("thin_content", CON, "Nok tekst på siden (≥ 300 ord)", 5, "Tynde sider rangerer sjældent på konkurrenceprægede søgeord.", "Uddyb med konkrete svar, eksempler og FAQ."),
        ("img_alt", CON, "Billeder har alt-tekst", 6, "Alt-tekst giver billedsøgning, tilgængelighed og kontekst.", "Tilføj beskrivende alt (tom alt=\"\" kun til ren dekoration)."),
        # --- Teknik ------------------------------------------------------------------------------
        ("https_final", TEK, "Sitet leveres på HTTPS", 10, "HTTPS er et rankingsignal og kræves af moderne browsere.", "Aktivér SSL og redirect alt til https."),
        ("http_redirect", TEK, "HTTP redirecter til HTTPS med 301", 8, "Ellers findes to versioner af sitet.", "Tilføj permanent redirect fra http til https."),
        ("www_redirect", TEK, "www / ikke-www samles på én version", 5, "To versioner splitter linkværdi og skaber dubletter.", "Redirect den ene til den anden med 301 og brug samme i canonical."),
        ("redirect_chain", TEK, "Ingen lange redirect-kæder", 4, "Hvert hop koster tid og linkværdi.", "Redirect direkte til slutadressen (max ét hop)."),
        ("doctype_charset", TEK, "Doctype og tegnsæt er angivet", 2, "Sikrer korrekt rendering af æ, ø, å.", "Brug <!doctype html> og <meta charset=utf-8>."),
        ("favicon", TEK, "Favicon findes", 2, "Vises i browsertabs og i mobilsøgning.", "Tilføj /favicon.ico og <link rel=icon>."),
        ("compression", TEK, "Tekstressourcer komprimeres (gzip/br)", 6, "Komprimering halverer typisk overførslen.", "Aktivér gzip eller Brotli på host/CDN."),
        ("llms_txt", TEK, "llms.txt findes (AI-søgning)", 1, "Hjælper AI-assistenter med at forstå sitet.", "Opret /llms.txt med en kort beskrivelse og nøgle-links."),
        # --- Hastighed ---------------------------------------------------------------------------
        ("ttfb", SPD, "Hurtig server-svartid (< 600 ms)", 6, "Langsom første byte forsinker alt andet og skader Core Web Vitals.", "Cache HTML på CDN, brug statisk generering (ISR) og region tæt på brugerne."),
        ("html_size", SPD, "HTML-dokument under 200 KB (komprimeret 100 KB)", 3, "Tung HTML forsinker rendering, især på mobil.", "Fjern inline-data og unødig markup."),
        ("render_blocking", SPD, "Ingen render-blokerende scripts i <head>", 4, "Scripts uden async/defer stopper sidens visning.", "Tilføj defer/async eller flyt scriptet."),
        ("cache_static", SPD, "Statiske filer caches længe", 3, "Lange cache-tider gør gensyn lynhurtige.", "Sæt Cache-Control: public, max-age=31536000, immutable på hashede filer."),
        ("img_dims", SPD, "Billeder har width/height", 3, "Uden dimensioner hopper siden under indlæsning (CLS).", "Angiv width og height, eller brug next/image."),
        ("img_lazy", SPD, "Billeder under folden er lazy-loadet", 2, "Sparer båndbredde og forbedrer LCP.", "Brug loading=\"lazy\" på alle andre end de første billeder."),
        ("psi_perf", SPD, "Lighthouse performance (mobil) ≥ 90", 8, "Samlet hastighedsscore fra Google PageSpeed.", "Se Lighthouse-rapporten for største flaskehalse."),
        ("psi_lcp", SPD, "LCP under 2,5 s", 6, "Largest Contentful Paint er en Core Web Vital.", "Optimér hero-billede/-tekst, preload font, hurtigere server."),
        ("psi_cls", SPD, "CLS under 0,1", 5, "Layout-hop irriterer brugere og er en Core Web Vital.", "Reservér plads til billeder, embeds og fonte."),
        ("psi_tbt", SPD, "Total Blocking Time under 200 ms", 4, "Proxy for INP – hvor responsiv siden føles.", "Reducér og udskyd JavaScript."),
        ("psi_a11y", MOB, "Lighthouse tilgængelighed ≥ 90", 3, "Tilgængelighed påvirker brugere og indirekte SEO.", "Ret kontrastfejl, labels og aria-attributter fra rapporten."),
        # --- Sikkerhed ---------------------------------------------------------------------------
        ("hsts", SEC, "HSTS er aktiveret", 4, "Tvinger HTTPS i browseren og beskytter mod downgrade-angreb.", "Send Strict-Transport-Security: max-age=31536000; includeSubDomains."),
        ("mixed_content", SEC, "Ingen mixed content", 6, "http-ressourcer på en https-side blokeres af browsere.", "Skift alle ressource-URL'er til https."),
        ("sec_nosniff", SEC, "X-Content-Type-Options: nosniff", 2, "Forhindrer MIME-sniffing.", "Send headeren X-Content-Type-Options: nosniff."),
        ("sec_frame", SEC, "Beskyttelse mod clickjacking", 2, "Forhindrer at siden indlejres på fremmede sites.", "Send X-Frame-Options: DENY eller CSP frame-ancestors."),
        ("sec_referrer", SEC, "Referrer-Policy er sat", 2, "Begrænser data sendt til andre sites.", "Send Referrer-Policy: strict-origin-when-cross-origin."),
        ("sec_csp", SEC, "Content-Security-Policy er sat", 2, "Reducerer risikoen for XSS.", "Indfør en CSP (start i report-only, og håndhæv den, når konsollen er stille)."),
        ("sec_permissions", SEC, "Permissions-Policy er sat", 1, "Slår ubrugte browser-API'er fra.", "Send Permissions-Policy: camera=(), geolocation=()."),
        ("security_txt", SEC, "security.txt findes", 1, "Gør det nemt at rapportere sårbarheder.", "Opret /.well-known/security.txt."),
        # --- Mobil -------------------------------------------------------------------------------
        ("viewport", MOB, "Viewport-meta er sat", 6, "Uden den vises siden som desktop på mobil – Google bruger mobile-first indexing.", "Tilføj <meta name=viewport content=\"width=device-width, initial-scale=1\">."),
        # --- Struktureret data -------------------------------------------------------------------
        ("jsonld_valid", SCH, "JSON-LD er gyldig", 5, "Ugyldig JSON-LD ignoreres og giver ingen rich results.", "Valider i Googles Rich Results Test."),
        ("schema_org", SCH, "Organization/WebSite-schema på forsiden", 6, "Hjælper Google med at forstå virksomheden (knowledge panel, sitelinks).", "Tilføj Organization og WebSite JSON-LD på forsiden."),
        ("schema_article", SCH, "Guides har Article/FAQPage-schema", 4, "Giver mulighed for rich results og bedre forståelse.", "Tilføj Article (headline, datePublished, author) eller FAQPage."),
        ("schema_breadcrumb", SCH, "Underside har BreadcrumbList", 2, "Viser brødkrumme-sti i søgeresultatet.", "Tilføj BreadcrumbList JSON-LD på undersider."),
        # --- Sociale medier ----------------------------------------------------------------------
        ("og_tags", SOC, "Open Graph-tags komplette", 4, "Styrer hvordan siden ser ud, når den deles på LinkedIn/Facebook.", "Sæt og:title, og:description, og:image og og:url."),
        ("twitter_card", SOC, "Twitter/X card er sat", 2, "Pænt delingskort på X.", "Sæt twitter:card=summary_large_image."),
    ]
    return {r[0]: CheckInfo(*r) for r in rows}


CATALOG: dict[str, CheckInfo] = _build()
