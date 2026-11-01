# Samtaletempo – hvorfor der er ventetid, og hvad der er skruet på

Gælder alle Vapi-opkald (indgående reception, demo-opkald, kampagner og Peters salgsopkald). Indstillingerne samles i
`app/modules/telephony/vapi.py` (`PACING`, `apply_pacing()`), og kan overstyres uden deploy med `VAPI_PACING_JSON`.

## Hvor tiden går

Hver tur i samtalen er tre led efter hinanden:

1. **Talegenkendelsen beslutter, at kunden er færdig** (endpointing). Det er det største led og det eneste, vi styrer
   helt selv.
2. **Modellen begynder at svare** (Claude Haiku 4.5 via Vapi). Tiden afhænger af system-promptens længde – den sendes
   med på hver tur.
3. **Stemmen begynder at tale** (ElevenLabs v4 turbo). Vapi venter som standard på ~30 tegn tekst, før første lydbid
   sendes.

Dertil kommer, at et korrekt svar, der er skrevet som skrift (lange sætninger, opremsninger), *lyder* langsomt og
mekanisk, selv når det kommer hurtigt.

## Det, der er sat (1. november 2026)

| Nøgle | Før | Nu | Hvad den gør |
|---|---|---|---|
| `wait_seconds` | 0,6 | 0,35 | Pause efter kunden stopper, før assistenten begynder |
| `on_punctuation_seconds` | 0,4 | 0,25 | Efter en færdig sætning (. ? !) |
| `on_no_punctuation_seconds` | 1,4 | 0,9 | Efter en ufærdig sætning ("øh …") |
| `on_number_seconds` | 1,2 | 1,2 | Mens kunden læser cifre op – uændret, tal kommer langsomt |
| `backoff_seconds` | 1,0 | 0,8 | Hvor længe assistenten tier efter at være blevet afbrudt |
| `max_tokens` | (ubegrænset) | 150 | Svar bliver aldrig monologer |
| `temperature` | (standard) | 0,7 | Samme spørgsmål får ikke ordret samme svar |
| `min_characters` | 30 (Vapi-standard) | 12 | Stemmen starter på første klausul ("Ja, det kan jeg godt hjælpe med –") |
| `optimize_streaming_latency` | 0 | 3 | ElevenLabs' laveste første-byte-latenstid; stemmekvaliteten er den samme |
| `background_sound` | off | office | Svagt kontorbrus, så en kort pause ikke lyder som en død linje |

Samlet forventet besparelse pr. tur: 0,8–1,3 sekunder. Korte "ja"/"mm" fra kunden afbryder stadig ikke assistenten
(`STOP_SPEAKING_PLAN.acknowledgementPhrases`).

Stemmemodel (`eleven_v4_turbo`) og dialogmodel (Haiku 4.5) er bevidst ikke ændret: de er kvaliteten. Flash v2.5 er
hurtigere, men fladere i dansk intonation – prøv den kun, hvis målingen viser, at stemmen er flaskehalsen.

## Prompten (phone-v6)

Telefonreglerne (`app/modules/ai/service.py`, `CHANNEL_INSTRUCTIONS["phone"]`) kræver nu en kort reaktion på to-fem ord
med punktum først, derefter det vigtigste i én sætning, højst cirka tyve ord pr. svar, og "Lige et øjeblik, jeg kigger."
før et værktøjskald. Den korte første sætning er det, stemmen begynder på, mens resten genereres.

Den godkendte viden sendes som én kompakt linje pr. emne (`type · titel: indhold`) i stedet for JSON-objekter – cirka
40 % færre tokens i system-prompten, som betales i ventetid på hver tur.

## Sådan måler du, før du skruer

1. Ring til demonummeret og stil tre-fire spørgsmål, afbryd én gang midt i et svar.
2. Åbn opkaldet på vapi.ai → *Calls* → fanen *Latency*: den viser pr. tur, hvor mange millisekunder der gik til
   transskribering, model og stemme.
3. Er transskriberingen størst: sæt `on_no_punctuation_seconds` ned i trin af 0,1. Bliver kunden afbrudt: op igen.
4. Er modellen størst: forkort den godkendte viden (færre, kortere emner) før alt andet.
5. Er stemmen størst: prøv `eleven_flash_v2_5` på nummeret og lyt til forskellen.

## A/B uden deploy

Sæt fx `VAPI_PACING_JSON={"on_no_punctuation_seconds": 0.7, "wait_seconds": 0.3}` på `dialogbot-api-staging` og
`dialogbot-worker-staging` i Render, genstart, ring igen. Fjern variablen for at gå tilbage til standarderne. Ukendte
nøgler ignoreres, så en tastefejl kan ikke stoppe opkald.

## Telefonnumre: bekræft, spørg ikke

Assistenten kender næsten altid kundens nummer i forvejen: det nummer, der ringes fra (Vapi `call.customer.number`,
ElevenLabs `caller_id`), det nummer, der blev skrevet på hjemmesiden (demo-opkald), eller det nummer, kampagnen eller
salgskanalen ringer til. `known_number_section()` i `app/modules/ai/service.py` lægger derfor en blok "Kundens
telefonnummer" ind i alle fire telefon-prompter med nummeret udtalt i ciffer-par ("tyve, tredive, fyrre, halvtreds")
og reglen: bed aldrig kunden diktere et nummer, du har – spørg "Skal vi ringe på det nummer, du ringer fra – det, der
ender på …?". Kun hvis kunden vil ringes op på et andet nummer, tages det ét ciffer-par ad gangen og gentages i par.
Er nummeret skjult, siger blokken det, og assistenten spørger i par.

Transskriptionen kører med Deepgram `numerals: true`, så cifre kommer som "20 30 40 50" i stedet for "tyve tredive
fyrre halvtreds" – det læser modellen langt mere sikkert, og `onNumberSeconds` giver kunden tid til at sige hele nummeret.
