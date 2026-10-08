# SEO-agent

En WooRank-lignende scanner, der overvåger dialogbot.dk (eller et andet site), giver en score pr. kategori og en prioriteret handlingsplan på dansk – og sammenligner med forrige scanning, så fremgang og tilbageskridt er synlige. Med Googles nøgler får rapporten også Core Web Vitals (PageSpeed/CrUX) og rigtige søgetal fra Search Console.

Ingen ekstra afhængigheder (kun Python-standardbiblioteket – også Search Console-login, som signerer sit eget JWT).

## Kør den

```bash
python -m seo_agent                       # scan https://www.dialogbot.dk
python -m seo_agent https://staging.example.dk --max-pages 100
python -m seo_agent --psi                 # + Core Web Vitals fra Google PageSpeed (mobil; PSI_API_KEY anbefales)
python -m seo_agent --psi --psi-strategy both   # mobil og desktop (eller desktop)
python -m seo_agent --json --no-save      # maskinlæsbar output
python -m seo_agent --fail-under 85 --fail-on-regression   # til CI
python -m seo_agent --no-gsc              # spring Search Console over, selv om nøglerne er sat
```

Rapporter gemmes i `var/seo/<host>/` (`latest.md`, `latest.json`, en tidsstemplet kopi og `gsc-history.json`). Næste kørsel sammenlignes automatisk med `latest.json`, eller med `--baseline fil.json`.

## Hvad den tjekker (~70 tjek i 9 kategorier)

Indeksering (status, noindex, robots.txt, sitemap, canonical, døde links, forældreløse sider, soft-404) · On-page (title, description, H1, overskriftsorden, unikke titler/beskrivelser, ankertekster, nøgleord) · Indhold (tyndt indhold, alt-tekst) · Teknik (HTTPS, redirects, www, komprimering, favicon, llms.txt) · Hastighed (svartid, HTML-størrelse, blokerende scripts, cache, billeder + Lighthouse/Core Web Vitals og CrUX-feltdata) · Sikkerhed (HSTS, mixed content, headers, security.txt) · Mobil (viewport, tilgængelighed) · Struktureret data (JSON-LD, Organization, Article, BreadcrumbList) · Sociale medier (Open Graph, Twitter card).

Hvert tjek har vægt, forklaring og konkret løsning i `seo_agent/catalog.py`. Score = vægtet andel bestået (OK = 1, advarsel = ½, fejl = 0). Prioritet = vægt × hvor galt det står til.

Siden crawles fra forsiden og sitemap, kun på samme domæne og kun hvad robots.txt tillader. En side med `noindex`, som **ikke** står i sitemap (login, app, onboarding), regnes som bevidst holdt ude af Google og får kun de tekniske tjek. Nøgleordstjekket måler på selve indholdet (uden menu og footer).

Ikke med: backlinks, domæneautoritet og konkurrentdata (kræver betalte datakilder). Søgeordsplaceringer og trafik kommer fra Search Console, når den er sat op (se nedenfor).

## Google-integration

### PageSpeed Insights (`--psi`)

Lighthouse-score, LCP, CLS, TBT og tilgængelighed for forsiden – for mobil, desktop eller begge (`--psi-strategy`). Når Google har nok rigtige besøg, vises også **feltdata fra Chrome UX Report** (LCP, INP, CLS ved 75. percentil, 28 dage) – det er disse tal, Google bruger som rankingsignal. Uden `PSI_API_KEY` deles kvoten med alle, og svaret er ofte 429; rapporten forklarer, hvad der skete (429 = kvote, 403 = nøgle/aktivering).

### Search Console (`GSC_SERVICE_ACCOUNT_JSON` + `GSC_SITE_URL`)

Kører automatisk, når begge er sat, ellers springes sektionen over. Rapporten får et afsnit med de seneste 28 dages **klik, visninger, CTR og gennemsnitlig position**, de 20 vigtigste **søgeforespørgsler** og **sider**, samt **indekseringsstatus** fra URL Inspection API for sitemap-siderne (højst `--gsc-inspect`, standard 20, for at spare kvote). Nøgletallene gemmes i `gsc-history.json`, så rapporten viser ændringen siden sidst og en udviklingstabel. Data i Search Console er ca. 3 dage forsinket; perioden slutter derfor 3 dage før i dag.

`GSC_SERVICE_ACCOUNT_JSON` er indholdet af nøglefilen (eller en sti til den). `GSC_SITE_URL` skal matche property'en præcis: `https://www.dialogbot.dk/` (URL-prefix) eller `sc-domain:dialogbot.dk` (domæne-property).

### Det kan kun ejeren gøre (tjekliste)

Agenten henter aldrig hemmeligheder selv og skriver dem aldrig i filer eller commits. Alt nedenfor sker i Google- og GitHub-konsollerne.

1. **PageSpeed Insights-nøgle**
   1. Gå til [console.cloud.google.com](https://console.cloud.google.com), vælg (eller opret) et projekt, fx «Dialogbot SEO».
   2. *APIs & Services → Library* → søg **PageSpeed Insights API** → *Enable*.
   3. *APIs & Services → Credentials → Create credentials → API key*. Begræns nøglen til «PageSpeed Insights API» under *API restrictions*.
   4. I GitHub: *Settings → Secrets and variables → Actions → New repository secret* → navn `PSI_API_KEY`, værdi = nøglen.
2. **Verificér dialogbot.dk i Search Console og indsend sitemap**
   1. Gå til [search.google.com/search-console](https://search.google.com/search-console) → *Tilføj property*.
   2. Vælg **Domæne** (`dialogbot.dk`) og tilføj den viste TXT-record i DNS hos domæneudbyderen – *eller* vælg **URL-præfiks** (`https://www.dialogbot.dk/`) og brug HTML-tagget: læg tag-værdien i Vercel som miljøvariabel `GOOGLE_SITE_VERIFICATION` (sitet skriver den i `<meta name="google-site-verification">`), deploy, og klik *Verificér*.
   3. *Sitemaps* → indsend `https://www.dialogbot.dk/sitemap.xml`.
3. **Service account til Search Console API**
   1. I Google Cloud (samme projekt): *APIs & Services → Library* → søg **Google Search Console API** → *Enable*.
   2. *IAM & Admin → Service Accounts → Create service account*, fx «seo-agent». Ingen projektroller er nødvendige.
   3. På service account'en: *Keys → Add key → Create new key → JSON*. Filen downloades én gang – gem den sikkert.
   4. I Search Console: *Indstillinger → Brugere og tilladelser → Tilføj bruger* → service account-mailen (`seo-agent@…iam.gserviceaccount.com`) med **Fuld** (eller Begrænset) adgang.
   5. I GitHub: secret `GSC_SERVICE_ACCOUNT_JSON` = hele JSON-filens indhold. Under *Variables* (ikke secret): `GSC_SITE_URL` = `sc-domain:dialogbot.dk` (domæne-property) eller `https://www.dialogbot.dk/` (URL-præfiks) – præcis som property'en hedder i Search Console.
   6. Kør workflowet manuelt (*Actions → SEO-overvågning → Run workflow*) og tjek, at rapporten har afsnittet «Google Search Console» uden advarsler.
4. **Google Business Profile**
   1. Gå til [business.google.com](https://business.google.com) → *Tilføj virksomhed* → «Dialogbot», kategori fx «Softwarevirksomhed», adresse Abildgade 18, 8200 Aarhus (eller serviceområde: Danmark), telefon, website `https://www.dialogbot.dk`.
   2. Verificér (postkort/telefon/video – Google vælger metoden).
   3. Upload logo, cover og billeder fra `web/public/brand/` (lavet til formålet i #59), tilføj åbningstider og en kort beskrivelse (brug teksten fra `web/public/llms.txt`).

Lokalt kan nøglerne sættes i miljøet før `python -m seo_agent --psi` – aldrig i `.env`-filer, der commites.

## Overvågning (GitHub Actions)

`.github/workflows/seo.yml` har tre jobs:

- **tests** – unittest + ruff af agenten (alle kørsler).
- **scan** – hver mandag, manuelt (*Run workflow* med site og PSI-strategi) og ved push til `main`: scanner det deployede site med PageSpeed (mobil + desktop) og Search Console, skriver rapporten i job-summary, gemmer `latest.json`, `latest.md` og `gsc-history.json` som artifact i 90 dage og sammenligner med forrige kørsel. Jobbet fejler under score 80. Secrets `PSI_API_KEY`, `GSC_SERVICE_ACCOUNT_JSON` og variablen `GSC_SITE_URL` sendes med, hvis de findes.
- **pr** – på pull requests, der ændrer `web/**`: bygger `web/`, starter den lokalt (uden backend og uden preview-gate) og scanner `http://localhost:3000`, så metadata, sitemap, robots, headers og struktureret data måles **før** deploy. Sammenlignes med den seneste lokale scanning af `main` og fejler med `--fail-on-regression`. HTTPS/www/hastighed og sider, der kræver backend (fx `/ambassador/bliv`), kan ikke vurderes her – de er ens i baseline og PR og tæller derfor ikke som regression.

## Claude-agenten

`.claude/agents/seo-ekspert.md` er en underagent med SEO-ekspertens arbejdsgang: scan → tolk → ret i `web/` → byg og scan lokalt → scan igen efter deploy → rapportér. Bed Claude om fx «brug seo-ekspert til at gennemgå sitet og rette de vigtigste punkter».

## Udvid

Nyt tjek: tekster i `catalog.py`, logik i `checks.py`, test i `seo_agent/tests/`. Tests: `python -m unittest discover -s seo_agent/tests -t .` · Lint: `python -m ruff check seo_agent`.
