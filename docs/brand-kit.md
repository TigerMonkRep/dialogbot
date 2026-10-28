# Dialogbot brand kit – filer og hvor de skal bruges

Alle filer følger `docs/brand.md` (v2, "Byggevejledningen"): blæk `#14213D`, papir, trin-flade `#EEF4FB`,
klods-blå `#2456F6`, trin-gul `#FFCF3F`, Outfit 800 til overskrifter og wordmark, Inter til brødtekst.
Ingen gradienter, ingen bløde skygger, ingen emoji, ingen knopper på klodserne.

Alt genereres fra kode – ret aldrig PNG-filerne i hånden. SVG'erne er håndskrevne (wordmark som kurver fra
Outfit 800, så de kræver ingen font).

## Logo – `web/public/brand/`

| Fil | Hvad | Brug |
|---|---|---|
| `logo.svg` | Mærke + wordmark, blæk tekst | Hjemmeside, dokumenter, lys baggrund |
| `logo-dark.svg` | Mærke + wordmark, hvid tekst | Mørk (blæk) baggrund |
| `logo-mark.svg` | Kun mærket (blå rundet firkant, radius 28 %, hvid talebobbel) | Ikoner, favicon, små flader |
| `logo-wordmark.svg` | Kun «Dialogbot» i Outfit 800 (kurver) | Når mærket står et andet sted |
| `logo-mark-1024.png` | Mærket, 1024 px, gennemsigtige hjørner | Profilbilleder, app-butikker, partnere |
| `logo-720.png` | Mærket på hvid, 12 % luft, 720 px | **Google Business-profil → Logo** (kræver kvadrat, min. 250 px) |
| `cover-1024x576.png` | Kopi af Google-coveret | Google Business (se nedenfor) |
| `foto-funktioner-1200x900.png` | Fladt «Det kan Dialogbot»-panel | Google Business-fotos, nyhedsbreve, LinkedIn-billede |
| `foto-priser-1200x900.png` | Fladt «To måder at betale på»-panel | Samme |

Mærket må ikke roteres, få skygge eller gradient. Luft omkring logoet: mindst mærkets halve bredde.

## App- og site-ikoner

| Fil | Størrelse | Brug |
|---|---|---|
| `web/src/app/icon.png` | 512 | Next.js `<link rel="icon">` |
| `web/src/app/apple-icon.png` | 180 | iOS-hjemmeskærm (fuld blå flade, iOS runder selv) |
| `web/src/app/favicon.ico` | 16/32/48 | Ældre browsere |
| `web/public/icons/icon-192.png`, `icon-512.png` | 192/512 | PWA-manifest. `icon-192.png` er også logoet i e-mails (`email_templates.LOGO_PATH`) og i signaturen |
| `web/public/icons/icon-maskable-512.png` | 512 | PWA maskable: mærket med sikker luft (boblen fylder 42 %) |
| `web/src/app/opengraph-image.png` + `twitter-image.png` | 1200×630 | Link-forhåndsvisning (Facebook, LinkedIn, Slack, X). Alt-tekst i `opengraph-image.alt.txt` |

## Sociale medier – `web/public/brand/social/`

| Fil | Størrelse | Upload her |
|---|---|---|
| `profile-1024.png` | 1024×1024 | **Instagram** @dialogbotdenmark → Rediger profil → Skift profilbillede. **TikTok** @dialogbot → Rediger profil → Foto. **Facebook-side** → Profilbillede. **LinkedIn-side** → Logo (300×300 anbefalet; filen skaleres). Google Business: brug `logo-720.png` |
| `cover-facebook-1640x624.png` | 1640×624 | **Facebook-side** → Rediger coverbillede. Al tekst ligger i midterfeltet (1250 px), som mobilen viser |
| `cover-google-1024x576.png` | 1024×576 | **Google Business-profil** → Fotos → Cover (16:9) |
| `cover-linkedin-1584x396.png` | 1584×396 | **LinkedIn-side** → Rediger side → Coverbillede. Logoet dækker nederste venstre hjørne – teksten står til højre |
| `cover-tiktok-1080x1920-story.png` | 1080×1920 | TikTok/Instagram story eller fastgjort video-cover. Teksten holder sig fri af top (250 px), bund (400 px) og højre kant (120 px) |
| `post-hook-1080x1080.png` | 1080×1080 | Eksempel på «hook»-look (blæk, gult trin-nummer, hvid Outfit). Facebook/Instagram-feed |
| `post-point-1080x1350.png` | 1080×1350 | Eksempel på «point»-look (papir, blæk-kontur-kort, «Du skal bruge»-boks). Instagram 4:5 |
| `post-cta-1080x1080.png` | 1080×1080 | Eksempel på «cta»-look (gul, blæk tekst, blå knap) |

Opslag genereres automatisk af `app/modules/social/render.py` i de samme tre looks (JPEG, de tre platformers
formater). Fonte og mærke ligger i `app/modules/social/assets/`.

Profil-tekster (bio) kan bruge: «Din AI-receptionist – på dansk, døgnet rundt · dialogbot.dk · 93 70 34 33».

## E-mail

- Transaktionsmails: `app/modules/integrations/email_templates.py` – hvidt kort med 2 px blæk-kontur på
  trin-flade, blå knap, gult trin-nummer når `Email.step` er sat (f.eks. bekræftelsesmailen = trin 1).
- Signatur: `docs/email-signature.html` – tabel + inline CSS. Udskift `{{NAVN}}` og `{{TITEL}}`, indsæt i
  Gmail → Indstillinger → Signatur (eller Outlook → Signaturer) som HTML. Mærket hentes fra
  `https://www.dialogbot.dk/icons/icon-192.png`, så der skal ikke vedhæftes billeder.

## Print – `web/public/materiale/`

`salgsmateriale.html` (brochure, 5 sider), `opsaetningsmanual.html` (trin 0–3 + viderestilling + «I dag»/«Det ved den»,
8 sider) og `ambassadoerhaandbog.html` (5 sider) er skrevet om som byggevejledninger i v2-designet: selvstændige
A4-dokumenter, én `<section class="page">` pr. ark, Outfit/Inter selvhostet i `materiale/fonts/` (ingen Google Fonts).
PDF'erne `dialogbot-*.pdf` ved siden af genereres med `cd web && node scripts/materiale-pdf.js` (Playwright/Chromium,
se `web/scripts/brand/README.md`). Brochuren kan personaliseres med `?navn=&link=&kode=&rabat=` (ambassadørportalen).

## Sådan genereres filerne igen

`web/scripts/brand/` (se README der): `make_fonts.py` laver statiske Outfit/Inter-TTF'er fra de variable fonte i
`web/node_modules/@fontsource-variable/*`, `svg_logo.py` skriver logo-SVG'erne, `svg2png.js` rasteriserer
mærket med Playwright, og `gen_assets.py` tegner alle PNG/ICO-filer med Pillow (`brand.py` er hjælpebiblioteket).
