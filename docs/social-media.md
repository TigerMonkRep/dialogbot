# Sociale medier — automatisk opslag på Facebook, Instagram og TikTok

Dialogbot kan selv lave og poste indhold på sine egne profiler. Koden ligger i `app/modules/social/` og kører i den eksisterende worker (`python -m app.worker.runner`); der er ingen ny tjeneste.

**Status (8. oktober 2026):** i drift på staging. Første rigtige opslag er gået ud på alle tre platforme (Facebook-siden *Dialogbot*, Instagram *@dialogbotdenmark*, TikTok *@dialogbotdenmark* — TikTok endnu kun privat, se audit nedenfor). `SOCIAL_REQUIRE_APPROVAL=true`, alle ugens dage (`SOCIAL_WEEKDAYS=0,1,2,3,4,5,6`). API'et svarer på `https://api.dialogbot.dk` (eget domæne, krævet af TikToks URL-verifikation).

## Hvad der sker, helt automatisk

Hver mandag, onsdag og fredag (`SOCIAL_WEEKDAYS`) får hver forbundet platform ét opslag. Kladderne laves 3 dage forud (`SOCIAL_PLAN_DAYS_AHEAD`), så der er tid til at kigge på dem. Dagens opslag handler om **ét emne** — det, der er brugt længst tid siden — men de tre platforme får **hver sit opslag**:

| | Facebook (kl. 09.30) | Instagram (kl. 12.15) | TikTok (kl. 19.00) |
|---|---|---|---|
| Billeder | ét kvadratisk kort (1080×1080) med overskrift og tre afkrydsede punkter | karrusel, 5 slides i 4:5 (1080×1350): hook → ét punkt pr. slide → opfordring | karrusel, 5 slides i 9:16 (1080×1920), tekst holdt væk fra TikToks egne knapper |
| Tekst | rolig, fortællende, 2-4 korte afsnit | levende og personlig, 1-3 afsnit | meget kort, talesprog, hook som spørgsmål |
| Link | klikbart link til den relevante side på dialogbot.dk | "Link i bio" (links i Instagram-tekster er ikke klikbare) | "Link i bio" |
| Hashtags | 1-3 | op til 10 | op til 5 |

Emnerne (16 stk., `app/modules/social/topics.py`): ubesvarede opkald, sådan kommer du i gang, priser, "svarer kun ud fra godkendt viden", booking, opsummeringer, AI-telefonsvarer vs. telefonpasning, chatbot, behold dit nummer, "bliv ringet op"-demoen og seks brancher (håndværkere, klinikker, frisører, autoværksteder, rådgivere, restauranter). Alle formuleringer følger hjemmesidens egne (`web/public/llms.txt`, `web/src/lib/industries.ts`).

### Hvem skriver teksten — og hvad forhindrer, at den finder på noget?

1. Er `AI_PROVIDER` slået til (`anthropic`), skriver AI'en de tre opslag ud fra en fast liste af **verificerede fakta** (`topics.FACTS`) og en vinkel for emnet. Den får de seneste overskrifter at undgå, så opslagene ikke ligner hinanden.
2. Hvert svar kontrolleres i kode (`content.check`): kun priserne 1.495 kr. og 149 kr. må nævnes; ingen procenter, garantier, "bedst"/"nr. 1", besparelser eller "gratis" uden for "gratis opsætning"; ingen links eller hashtags i selve teksten (dem sætter koden på); længdegrænser og antal slides pr. platform.
3. Fejler en platforms tekst kontrollen — eller er AI'en slået fra, utilgængelig eller svarer ugyldigt — bruges den **håndskrevne tekst** for den platform. Et opslag blokeres altså aldrig af AI'en, og det indeholder aldrig et tal eller løfte, der ikke står i fakta-listen. AI-kald logges i `ai_usage` på salgsarbejdsrummet (`SALES_WORKSPACE_ID`), hvis det findes.
4. Billederne er rene grafikker i brandets farver og skrifttype (Manrope) — ingen genererede fotos, ingen opdigtede kundecitater.

Ændrer du en pris eller et løfte på hjemmesiden, så ret det også i `topics.py` (en test låser priserne).

## Det skal du gøre (kun du kan det)

Jeg kan ikke oprette konti, apps eller tokens hos Meta og TikTok. Indtil nøglerne er sat, er `SOCIAL_PROVIDER=none`, og der sker intet.

### 1. Offentlig billed-URL
Platformene henter billederne selv fra `PUBLIC_BASE_URL/api/v1/social/media/<id>.jpg`. `PUBLIC_BASE_URL` skal derfor være API'ets offentlige **https**-adresse — både på API og worker. (JPEG er valgt med vilje: Instagram accepterer kun JPEG, TikTok-fotoopslag kun JPEG/WEBP.)

### 2. Facebook + Instagram (Meta)
1. Instagram-kontoen skal være en *Business*- eller *Creator*-konto og knyttet til Dialogbots Facebook-side.
2. Opret en app (type *Business*) på developers.facebook.com. Tilføj tilladelserne `pages_manage_posts`, `pages_read_engagement`, `pages_show_list`, `instagram_basic`, `instagram_content_publish`. Så længe appen er i udviklingstilstand og du er administrator af den, virker de på dine egne aktiver uden app-review.
3. Lav en **langlivet sidetoken** — eller (det vi bruger) en **System User-token** i Business Manager/Meta Business Suite: appen knyttes til business-porteføljen, systembrugeren (Admin) får *fuld adgang* til siden og Instagram-kontoen og *Udvikl app* på appen, og tokenet genereres med udløb *Aldrig* og de fem tilladelser. Koden udveksler selv et systembruger-/brugertoken til sidens eget token (`GET /{page-id}?fields=access_token`), fordi Graph API ellers svarer `(#200) publish_actions` på `/{page-id}/photos`. Bemærk: er siden ejet af en business-portefølje, viser Facebooks login-dialog den ikke, før appen er knyttet til porteføljen.
4. Find Instagram-id'et: `GET /{page-id}?fields=instagram_business_account`.
5. Sæt `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN`, `META_INSTAGRAM_USER_ID` (API + worker).

### 3. TikTok
1. På developers.tiktok.com: opret en app, tilføj produkterne *Login Kit* og *Content Posting API*, scopes `user.info.basic` og `video.publish`.
2. Verificér ejerskab af URL-præfikset med billederne (`PUBLIC_BASE_URL/api/v1/social/media/`) i appens indstillinger — TikTok henter kun fra verificerede adresser (typisk via en DNS-TXT-post på domænet).
3. Sæt `TIKTOK_CLIENT_KEY` og `TIKTOK_CLIENT_SECRET`, sæt `CREDENTIALS_KEY` (`python -m scripts.credentials_key`), og kør i Render-shellen:
   ```bash
   python -m scripts.social_connect tiktok-url  https://<din-redirect-uri>
   # åbn linket logget ind som Dialogbots TikTok-konto, godkend, kopiér ?code=… fra adressen du sendes til
   python -m scripts.social_connect tiktok-code https://<din-redirect-uri> <code>
   python -m scripts.social_connect status
   ```
   Refresh-tokenet gemmes krypteret i databasen og skifter af sig selv ved hver brug.
4. **Vigtigt forbehold fra TikTok:** indtil TikTok har *auditeret* appen, må den kun poste til en konto, der er sat til **privat** (fejlen `unaudited_client_can_only_post_to_private_accounts`), og opslagene bliver `SELF_ONLY`. Systemet poster privat og skriver det i opslagets `last_error` ("… kun synligt for dig"). Produktions-appen kan ikke engang *gemmes* uden en demovideo af integrationen, så den første forbindelse laves i en **Sandbox** (egne nøgler, target user = Dialogbots konto, domænet skal verificeres *separat* for sandboxen). Når audit er godkendt: sæt production-nøglerne i `TIKTOK_CLIENT_KEY/SECRET`, kør `social_connect tiktok-url/tiktok-code` igen, og sæt kontoen tilbage til offentlig.

### 4. Slå det til
Sæt `SOCIAL_PROVIDER=live` på API og worker. Anbefalet start: `SOCIAL_REQUIRE_APPROVAL=true`, læs de første kladder (se nedenfor), godkend dem, og skift derefter til `false`.

## Styring (operatør-API)

Kræver operatørrollen (`python -m scripts.grant_operator grant <e-mail>`). Alle ændringer skrives i revisionsloggen.

| Kald | Gør |
|---|---|
| `GET /api/v1/operator/social` | Provider, hvilke platforme der er forbundet, tidsplan, antal pr. status |
| `GET /api/v1/operator/social/posts?status=draft&platform=tiktok` | Opslag med tekst, slides, billed-URL'er, fejl |
| `PATCH /operator/social/posts/{id}` `{caption}` | Ret teksten, før opslaget går ud |
| `POST /operator/social/posts/{id}/approve` | Godkend en kladd |
| `POST /operator/social/posts/{id}/cancel` | Annullér (pladsen kan planlægges igen) |
| `POST /operator/social/posts/{id}/publish-now` | Post med det samme (kan tage op til ét minut på Instagram) |
| `POST /operator/social/plan` `{day, topic?, platforms?}` | Lav opslag til en bestemt dag/emne |

**Nødbremse:** sæt `SOCIAL_PROVIDER=none` — intet planlægges eller postes. Planlagte opslag bliver liggende.

## Hvordan fejl håndteres

- Et opslag sættes til `publishing` og gemmes, **før** platformen kaldes. Sker der en nedbrud midt i, markeres opslaget efter 30 min som *usikkert* (`failed`, "tjek profilen") og postes **ikke** igen automatisk — et dobbelt opslag er værre end et manglende.
- Fejl, hvor platformen ikke kan have oprettet noget (forbindelse, rate limit, 5xx) prøves igen efter 5 og 30 minutter, højst 3 gange. Udløbet token, afvist indhold og timeouts på selve opslagskaldet prøves ikke igen.
- Er et tidspunkt mere end `SOCIAL_MAX_LATE_MINUTES` (6 timer) forsinket, springes det over (`skipped`).
- Worker-løkken er enkeltrådet: et Instagram-opslag kan holde den op til ca. et minut, mens Instagram behandler billederne.
- Tokens logges aldrig og indgår ikke i fejlbeskeder.

## Begrænsninger (ærligt)

- **Kun fotos/karruseller — ingen video.** TikTok-opslagene er fotokarruseller (TikTok kalder det "photo mode"), ikke videoer. Video kræver en anden pipeline.
- **Ingen opfølgning på kommentarer, beskeder eller statistik.** Systemet poster; det besvarer og måler ikke. Kommentarer skal stadig læses af et menneske.
- Meta- og TikTok-kaldene er skrevet efter leverandørernes dokumentation og testet mod en mock; formater og fejlkoder kan afvige i praksis. Følg det første rigtige opslag på hver platform.
- Dialogbot skriver kun om sig selv. Indholdet er markedsføring af egen virksomhed på egne profiler; det er ikke kundeindhold.
