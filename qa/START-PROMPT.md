# Startprompt – kør hele QA-holdet

Kopiér teksten herunder ind i Claude Code (åbnet i Dialogbot-repoet), eller giv den til Claude i en session med adgang til repoet.

---

Du er `qa-lead` (se `.claude/agents/qa-lead.md`). Kør en fuld QA-kørsel af Dialogbot efter protokollen i `qa/README.md`.

1. Læs `qa/README.md`, `qa/scenarios.csv` og handoff-filerne. Byg QA-miljøet (Postgres i Docker + Alembic head + API + worker + Next.js mod den lokale API, Playwright med Chromium). Skriv aldrig til produktion – Render-tjenesterne med "staging" i navnet ER produktion.
2. Bølge 1: alle P0-scenarier. Start specialist-agenterne parallelt efter ejerkolonnen. e2e-erhverv deles op i flere instanser efter område.
3. Triagér fund løbende, send bekræftede fund til `fix-engineer` (branch `qa/fix-<dato>`), og send hver rettelse til `verifier`.
4. Bølge 2: P1. Bølge 3: P2, hvis tiden rækker.
5. Når gaten i README er opfyldt (eller du er blokeret), skriv `qa/reports/<dato>-run.md` og åbn én PR med tests + rettelser til mig.
6. Saml alt, der kræver min beslutning (priser, tekster, juridisk, Peters regler), i en kort dansk liste øverst i rapporten.

Ingen rigtige opkald, SMS eller e-mails, ingen Stripe live, ingen ændringer i Render/Vercel/Supabase. Hvis et testopkald til mit eget nummer er nødvendigt til sidst, så spørg mig først.
