# Dialogbot brand & design system v2 — "Byggevejledningen"

Gældende fra oktober 2026. Erstatter Stitch/Material-paletten (grøn/lime) overalt: web, app, e-mails, sociale medier, Google Business, print.

## Princip

Dialogbot er en byggevejledning. Hver skærm er ét trin: et nummer, én handling, en "Du skal bruge"-boks, et fladt billede, en kort tekst. Hvis noget kræver forklaring, er det for kompliceret. De tunge funktioner ligger bag assistenten (chatten) – aldrig i menuer.

Fire regler:
1. Én handling pr. trin.
2. Vis «du skal bruge» før «gør sådan».
3. Nummer, overskrift, billede, tekst – altid i den rækkefølge.
4. Assistenten viser altid ændringen (før → efter) og spørger «Godkend?», før noget gælder.

## Farver

| Token | Hex | Brug |
|---|---|---|
| Blæk `ink` | `#14213D` | Al tekst, 2 px konturer, mørke flader, valgte faner |
| Blæk blød `ink-soft` | `#3C4659` | Brødtekst på papir |
| Papir `paper` | `#FFFFFF` | Grund |
| Trin-flade `panel` | `#EEF4FB` | Skiftevis sektionsbaggrund, chips |
| Streg `line` | `#D6DEEA` | Hårstreger, deaktiveret |
| Dæmpet `muted` | `#5B6475` | Etiketter, hjælpetekst (4,5:1 på hvid) |
| **Klods-blå** `accent` | `#2456F6` | DEN ENE handlingsfarve: primærknapper, ikonfliser, links |
| Klods-blå mørk | `#1A3FC0` | Hover |
| Klods-blå lys | `#DCE6FF` | "I gang"-badges |
| **Trin-gul** `highlight` | `#FFCF3F` | Trin-numre, «her er du», fremhævning, gul CTA på mørk flade |
| Grøn `success` | `#1B6B3A` på `#DDF5E4` | «Klar»-status, godkendt |
| Rød `danger` | `#B3261E` på `#FFDAD6` | Fejl |

Kun to kulører: blå = handling, gul = her er du. Alt andet er blæk på papir. Ingen gradienter, ingen bløde skygger. Eneste skygge er den faste **blok-skygge** `8px 8px 0 #14213D` (én pr. sektion, det fremhævede kort).

## Typografi

- **Outfit** (800/700) til overskrifter, trin-numre, tal og wordmark. Letter-spacing −1 px på store størrelser.
- **Inter** (400/500/600) til brødtekst, knapper, etiketter.
- Etiket/eyebrow: Inter 600 · 12–13 px · versaler · +0,12 em · `muted`.
- Størrelser: display 56–68 · h2 40–46 · korttitel 20–22 · brød 17/15 · hjælp 13.

## Former

- Konturer: 2 px blæk på kort og knapper, 1,5 px på indre bokse og rækker.
- Radius: knapper 12–14 px · kort 16–20 px · fliser 10–12 px · piller 999 px.
- Trin-nummer: gul rundet firkant 56 px (store trin 1–3), 40 px (del-trin A–D), Outfit 800.
- «Du skal bruge»-boks: 1,5 px kontur, eyebrow, chips med antal (**1×**).
- Klodser i illustrationer: flade rundede blokke i blå/gul **uden knopper** (ingen LEGO-trade dress), sorte pile 3 px.
- Knapper ≥ 44 px høje (52 px primær). Én primær knap pr. skærm.
- Ikoner: 2,2 px streg, hvide på blå flise – aldrig emoji.

## Logo

Mærke: en blå (`#2456F6`) rundet firkant (radius 28 % af siden) med en hvid talebobbel (streg 2,4/24). Wordmark «Dialogbot» i Outfit 800, −0,3 px.
Filer: `web/public/brand/logo.svg` (mærke + wordmark, blæk tekst), `logo-dark.svg` (hvid tekst til mørk flade), `logo-mark.svg`, `logo-wordmark.svg`, `logo-mark-1024.png` (profilbillede), `logo-720.png` (mærke på hvid til Google Business). Oversigt og upload-steder: `docs/brand-kit.md`; generator: `web/scripts/brand/`.
Må ikke: gradienter, skygge, roteres, gammel grøn/lime-version.

## Sociale medier

Profilbillede: `brand/social/profile-1024.png` (blåt mærke på hvid, 12 % luft).
Covers: Facebook `cover-facebook-1640x624.png`, Google Business `cover-google-1024x576.png`, LinkedIn `cover-linkedin-1584x396.png`.
Opslag (genereres af `app/modules/social/render.py`): tre looks – `hook` (blæk-mørk, gul tal/pille), `point` (papir, blæk-kontur-kort), `cta` (gul). Altid trin-nummer eller «1×»-chip som grafisk greb, Outfit til overskrift, mærke + «Dialogbot» nederst til venstre.

## E-mail

Transaktionelle mails (`app/modules/integrations/email_templates.py`): hvid kort med 2 px blæk-kontur på `panel`-baggrund, blå knap, gul trin-nummer når mailen er et trin i opsætningen. Signatur: `docs/email-signature.html`.

- **Én knap pr. mail** (det ene næste trin) og få, korte afsnit. Tal vises i et lille panel (`Email.rows`), ikke som tekstmur.
- **Mørk visning og telefon** ligger i layoutet (`prefers-color-scheme: dark`, `max-width: 480px`): mørk side `#0D1630`, kort i blæk, hvid overskrift, blå knap og gult trin-nummer uændret. Apple Mail, iOS Mail, Outlook og Samsung Mail følger det; Gmail på Android kan lægge sin egen inversion ovenpå.
- **Ny mail = ny funktion**, der returnerer en `Email`, og en linje i `samples()`. Layout, mørk visning og telefon arves; en test fejler, indtil den er på listen.
- **Se dem alle:** `python -m scripts.preview_emails` (åbn `var/email-preview/index.html`: lys, mørk, telefon) og `node web/scripts/shoot-emails.mjs` (skærmbilleder i `docs/email-previews/`).

## SMS

Faste tekster i `app/modules/integrations/sms_templates.py`: ét segment (≤ 160 tegn), ingen emoji eller udråbstegn, afsender = virksomhedens navn (højst 11 tegn), alle slutter «Vh {virksomhed}». De tilhører kundens virksomhed og bærer ikke Dialogbots brand.

## Hvor det ligger

- Tokens: `web/src/app/globals.css` (@theme). Semantiske Material-navne er beholdt og peger på de nye farver; ny kode bruger brand-tokens (`bg-accent`, `text-ink`, `border-ink`, `bg-panel`, `bg-highlight`, `shadow-block`).
- Komponenter: `web/src/components/ui.tsx`, `lego.tsx` (trin-nummer, dele-boks, klods, pil), `shell.tsx`.
- Referencedesign: `design-reference/byggevejledning/*.dc.html` (Indgang, Main = byggevejledning, Proev, Onboarding, Taend, Dashboard, Viden, Avanceret, Stilark – plus kundeappen: Trin1, Opkald, Ugen, Aftaler, Kampagner, Konto, Mobil; spec i `docs/kundeapp-v2.md`).
