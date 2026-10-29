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
