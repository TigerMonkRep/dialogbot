# Designreferencer

- `latest/stitch_dialogbot/<skærm>_{desktop,mobil}/` er Stitch-eksporten (projekt DIALOGBOT, 25.09.2026). `code.html` er kilden til sandheden, og `screen.png` er kun en thumbnail.
- `latest/stitch_dialogbot/nordic_telephony_ai_operations/DESIGN.md` er designsystemet.
- `stitch/` indeholder DESIGN.md og skærmoversigten, hentet via Stitch MCP. De er identiske med eksporten.
- `tools/` bruges til offline-rendering af referencerne: `cd design-reference/tools && npm ci && npm run render`. Det giver `out/<skærm>-1440.png` for desktop og `out/<skærm>-390.png` for mobil. Tailwind v3 kompileres fra hver skærms egen `tailwind.config`, og fontene er lokale. Der er intet CDN involveret.

Desktop- og mobilversionerne er separate layouts og skal matches hver for sig ved 1440 og 390 px.

Tokens: alle farver i `web/src/app/globals.css` stemmer 1:1 med `code.html`. Radius er DEFAULT 0.25rem, lg 0.5rem og xl 0.75rem, som i `code.html`. DESIGN.md's `rounded`-sektion afviger, men `code.html` gælder.
