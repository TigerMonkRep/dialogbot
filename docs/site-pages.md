# Sider med redigerbart indhold på dialogbot.dk (`/gastrohall`)

Små sider, som Dialogbots egne folk retter direkte i browseren – fx manuskriptet, vi viser en kunde. Siden ligger som
statisk fil i `web/public/<slug>/index.html` (rewrite i `next.config.ts`), og dens indhold hentes fra API'et:

- `GET /api/v1/public/pages/{slug}` – åben. Returnerer `{slug, blob, updated_at}`; `blob` er opak for serveren.
- `PUT /api/v1/operator/pages/{slug}` – kun platformsoperatører (`scripts/grant_operator.py`). Skriver i revisorloggen.
- Tilladte slugs står i `app/modules/pages/router.py` (`SLUGS`); nye sider tilføjes der.

`/gastrohall` er kodeordsbeskyttet i browseren: teksten er krypteret med PBKDF2 + AES-GCM ud fra kodeordet, så hverken
databasen eller kildekoden viser ordene. Første version er indlejret i filen som reserve; «Gem» kræver, at man er logget
ind som operatør på samme domæne (`/login?next=/gastrohall`). Kilden til siden ligger i chat-sessionen (generator
`build.mjs` + `template-site.html`); ret indholdet på siden, ikke i filen.

# Rutekort for det offentlige site (nov. 2026)

| Rute | Hvad | Sprog |
|---|---|---|
| `/` | **Indgangen** – én assistent, to døre (`web/src/app/(public)/page.tsx`, tekster `messages/<sprog>/entry.json`). Organization + WebSite-schema. | `/<sprog>` (proxy) |
| `/erhverv` | Erhverv-landingen (tidligere `/`; `web/src/app/(public)/erhverv/page.tsx`, SoftwareApplication-schema). | `/<sprog>/erhverv` |
| `/privat` | Privat-landingen (`web/src/app/privat/page.tsx`). | cookie `dlg_lang` |
| `/proev`, `/byggevejledning`, `/priser`, `/start`, `/privat/start`, `/a/{slug}` | Uændret. Ambassadørbanneret (`/a/{slug}` → `/?anbefalet=…`, cookie `db_ref`) vises på både indgangen og `/erhverv` (`components/referral-banner.tsx`). | |

## Cookien `db_aud` – «hvilken dør valgte du»

- Sættes af `web/src/proxy.ts`, når en besøgende åbner `/erhverv` eller `/privat` (Trin 2-panelerne på indgangen
  linker dertil, så et klik på et panel sætter den). Værdier `erhverv` | `privat`, 1 år, `SameSite=Lax`, `Path=/`.
  Ikke en hemmelighed og ikke persondata – ét af to ord.
- Når cookien findes, sender proxyen `/` (og `/<sprog>`) direkte videre: `erhverv` → `/<sprog>/erhverv`,
  `privat` → `/privat` (307, `Cache-Control: private, no-store`, `Vary: cookie`). Query-parametre følger med
  (`?anbefalet=…`, `utm_*`).
- Uden cookie (nye besøgende, søgemaskiner) vises indgangen.
- **Nulstilling:** `/?aud=reset` viser indgangen uanset cookie og sletter den (Max-Age 0). Det er den ene valgte
  mekanisme; `?vis=indgang` findes ikke.
- Indgangens svar sendes altid med `Cache-Control: private, no-store`, så en delt cache aldrig serverer den til én
  med cookie (eller omvendt).
- Preview-gaten (`PREVIEW_GATE=on`) dækker `/`, `/erhverv`, `/proev`, `/byggevejledning` og `/signup`.

## Accentlag

`web/src/components/mark.tsx`: `<Mark kind="marker|underline|ring" tone="yellow|ink|blue|orange">` (inline-SVG bag
overskriftsord, CSS i `globals.css` → `.mk`), `<Tilted deg>` og `<ShortArrow/>`. Regler: markør = gul på begge
målgrupper, maks én pr. skærmbillede; tynd streg = blæk på Erhverv, orange på Privat; aldrig på brødtekst, knapper,
felter, footer eller logo; ingen animation. De markerede ord ligger i JSON som `{ "before", "mark", "after" }`
(ingen HTML i JSON), så hvert sprog vælger sit eget nøgleord.
