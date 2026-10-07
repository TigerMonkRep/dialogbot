# SEO-agent

En WooRank-lignende scanner, der overvåger dialogbot.dk (eller et andet site), giver en score pr. kategori og en prioriteret handlingsplan på dansk – og sammenligner med forrige scanning, så fremgang og tilbageskridt er synlige.

Ingen ekstra afhængigheder (kun Python-standardbiblioteket).

## Kør den

```bash
python -m seo_agent                       # scan https://www.dialogbot.dk
python -m seo_agent https://staging.example.dk --max-pages 100
python -m seo_agent --psi                 # + Core Web Vitals fra Google PageSpeed (PSI_API_KEY anbefales)
python -m seo_agent --json --no-save      # maskinlæsbar output
python -m seo_agent --fail-under 85 --fail-on-regression   # til CI
```

Rapporter gemmes i `var/seo/<host>/` (`latest.md`, `latest.json` og en tidsstemplet kopi). Næste kørsel sammenlignes automatisk med `latest.json`, eller med `--baseline fil.json`.

## Hvad den tjekker (~60 tjek i 9 kategorier)

Indeksering (status, noindex, robots.txt, sitemap, canonical, døde links, forældreløse sider, soft-404) · On-page (title, description, H1, overskriftsorden, unikke titler/beskrivelser, ankertekster, nøgleord) · Indhold (tyndt indhold, alt-tekst) · Teknik (HTTPS, redirects, www, komprimering, favicon, llms.txt) · Hastighed (svartid, HTML-størrelse, blokerende scripts, cache, billeder + Lighthouse/Core Web Vitals) · Sikkerhed (HSTS, mixed content, headers) · Mobil (viewport, tilgængelighed) · Struktureret data (JSON-LD, Organization, Article, BreadcrumbList) · Sociale medier (Open Graph, Twitter card).

Hvert tjek har vægt, forklaring og konkret løsning i `seo_agent/catalog.py`. Score = vægtet andel bestået (OK = 1, advarsel = ½, fejl = 0). Prioritet = vægt × hvor galt det står til.

Siden crawles fra forsiden og sitemap, kun på samme domæne og kun hvad robots.txt tillader. Ikke med: backlinks, domæneautoritet, søgeordsplaceringer, trafik (kræver betalte datakilder eller Search Console).

## Overvågning (GitHub Actions)

`.github/workflows/seo.yml` kører hver mandag (og manuelt): tester agenten, scanner sitet, skriver rapporten i job-summary, gemmer den som artifact i 90 dage og sammenligner med forrige kørsel. Jobbet fejler under score 80. Tilføj evt. secret `PSI_API_KEY` (gratis fra Google Cloud) for stabile Core Web Vitals.

## Claude-agenten

`.claude/agents/seo-ekspert.md` er en underagent med SEO-ekspertens arbejdsgang: scan → tolk → ret i `web/` → scan igen → rapportér. Bed Claude om fx «brug seo-ekspert til at gennemgå sitet og rette de vigtigste punkter».

## Udvid

Nyt tjek: tekster i `catalog.py`, logik i `checks.py`, test i `seo_agent/tests/`. Tests: `python -m unittest discover -s seo_agent/tests -t .`
