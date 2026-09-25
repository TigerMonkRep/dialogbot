# Stitch-reference (projekt DIALOGBOT)

Hentet via Stitch MCP (`https://stitch.googleapis.com/mcp`) den 25. september 2026.

- `DESIGN.md` er projektets designsystem, eksporteret uændret. Alle 47 farvetokens stemmer 1:1 med `web/src/app/globals.css`.
- `screens.json` er oversigten over de 45 skærme (id, titel, enhed og størrelse). Screenshots og `code.html` pr. skærm hentes med `get_screen`. De kræver adgang til `contribution.usercontent.google.com` og `lh3.googleusercontent.com`.

Kendt afvigelse, som ikke er afklaret: DESIGN.md angiver `rounded` DEFAULT 0.5rem, md 0.75rem, lg 1rem og xl 1.5rem. `globals.css` bruger 0.25, 0.5 og 0.75rem (angiveligt fra skærmenes `tailwind.config`). Det afgøres, når skærm-HTML'en kan hentes.
