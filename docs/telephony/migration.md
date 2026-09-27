# Migrations- og rollbackplan – platformtelefoni (`e668ed509035`)

## Før

- Produktion (Supabase `zofdupmpcokvcvstsozm`, skema `dialogbot`) havde den 27/9 2026 **0 rækker** i
  `phone_numbers`. Ingen kunde havde en aktiv telefonforbindelse, der kan brydes.
- Tag alligevel en backup (Supabase → Database → Backups), før der deployes.

## Migration (kører automatisk som Render pre-deploy)

1. **Nye tabeller:** `telephony_accounts`, `telephony_setups`, `telephony_tests`, `telephony_jobs` og
   `telephony_costs`.
2. **Nye kolonner på `phone_numbers`:**
   - `source` (eksisterende rækker = `legacy_customer`);
   - `status` (`active`);
   - `telephony_account_id`, `provider_sid`;
   - `outbound_allowed` (`false`).
3. **Eksisterende numre bevares:**
   - Hvert arbejdsrum med et aktivt nummer får en `telephony_setups`-række med `state=active`, der peger på nummeret.
     Opkald til nummeret besvares derfor som før.
   - Numre, som en kampagne allerede bruger, får `outbound_allowed=true`.
   - Ingen numre bliver slettet eller frigivet.

Migrationen er testet på en tom database og på en database med et eksisterende nummer:
- `upgrade` gav `active | legacy_customer | active | false`;
- `downgrade` efterlod nummeret uændret;
- `alembic check` fandt ingen afvigelser.

## Efter deploy

- Kunder uden telefoni ser "Ikke sat op" og næste skridt. Intet bliver købt, før en kunde har bekræftet sit
  nummer, dokumentationen er godkendt, og en prisaftale er valgt. Uden `TELEPHONY_PROVIDER=live` køber systemet
  aldrig noget.
- Eksisterende manuelt opsatte numre (hvis der kommer nogen før deploy) kan flyttes til Dialogbots
  Vapi-organisation. Operatøren tilknytter dem i `/app/operator/telephony` → "Tilknyt (migrering)".

## Rollback

1. **Kode:** redeploy forrige commit på Render og Vercel.
2. **Database:** `alembic downgrade a8a4f6f5ffaf`. Det fjerner de nye tabeller og kolonner, mens `phone_numbers`
   og deres Vapi-id'er bliver stående. Opsætninger, tests, job og omkostningsposter går tabt. Tag en backup først.
3. **Hos leverandørerne** bliver intet slettet ved rollback. Købte numre og underkonti ligger fortsat i Dialogbots
   Twilio-konto og kan genfindes på FriendlyName `dialogbot-<workspace id>`. Efter en ny upgrade adopterer jobbet
   dem igen i stedet for at købe nye.
