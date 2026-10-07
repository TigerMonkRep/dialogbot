import type { Part } from "@/components/lego";

/** Maps the server's setup tasks onto the printed building manual (public/materiale/opsaetningsmanual.html):
 *  the same five bags, the same step numbers and the same parts, so the guide and the PDF can be read side by side.
 *  Steps 1–3 (account, e-mail, workspace) happen before the plan exists; step 17 (price agreement) lives in Settings. */

export const BAGS = [
  { n: 1, name: "Din virksomhed", text: "Virksomhedsoplysninger og branchekategorier" },
  { n: 2, name: "Mål og sprog", text: "Hvad assistenten skal kunne, og hvilke sprog den taler" },
  { n: 3, name: "Viden og svar", text: "Ydelser, priser og åbningstider. Godkend og test" },
  { n: 4, name: "Kanaler", text: "Stemme, telefon og prøveopkald. Webchat og booking er valgfrie" },
  { n: 5, name: "Aktivering", text: "Vælg prisaftale, og tænd for receptionen" },
] as const;

type Build = { bag: number; step: string; parts: Part[] };

const BUILD: Record<string, Build> = {
  "business.profile": { bag: 1, step: "4a", parts: [{ icon: "badge", label: "CVR-nummer", color: "sky" }, { icon: "language", label: "Hjemmeside", color: "ghost", optional: true }] },
  "business.categories": { bag: 1, step: "4b", parts: [] },
  "goals.select": { bag: 2, step: "5", parts: [] },
  "languages.settings": { bag: 2, step: "6", parts: [] },
  "knowledge.services": { bag: 3, step: "7", parts: [{ icon: "sell", label: "Ydelser og priser", color: "lime" }, { icon: "language", label: "Hjemmeside", color: "ghost", optional: true }] },
  "knowledge.opening_hours": { bag: 3, step: "8a", parts: [{ icon: "schedule", label: "Åbningstider", color: "mint" }] },
  "knowledge.coverage_area": { bag: 3, step: "8b", parts: [{ icon: "map", label: "Område", color: "ghost", optional: true }] },
  "knowledge.answers": { bag: 3, step: "8c", parts: [{ icon: "quiz", label: "Faste svar", color: "ghost", optional: true }] },
  "knowledge.review": { bag: 3, step: "9", parts: [{ icon: "person", label: "Ejer/admin", color: "lime" }] },
  "checks.server": { bag: 3, step: "10", parts: [] },
  "voice.choose": { bag: 4, step: "11", parts: [{ icon: "headphones", label: "Lyd", color: "mint" }] },
  "reception.telephony_forwarding": { bag: 4, step: "12–13", parts: [{ icon: "call", label: "Firmaets telefon", color: "forest" }, { icon: "description", label: "CVR-udskrift", color: "white" }] },
  "reception.test_call": { bag: 4, step: "14", parts: [{ icon: "smartphone", label: "Ekstra telefon", color: "sky" }] },
  "reception.webchat": { bag: 4, step: "15", parts: [{ icon: "code", label: "Kodeadgang", color: "ghost" }] },
  "booking.calendar": { bag: 4, step: "16a", parts: [{ icon: "calendar_month", label: "Kalender", color: "ghost" }] },
  "integrations.connect": { bag: 4, step: "16b", parts: [{ icon: "hub", label: "Zapier/Make", color: "ghost", optional: true }] },
  "campaign.first": { bag: 4, step: "K1", parts: [{ icon: "contacts", label: "Kontakter (CSV)", color: "sky" }] },
  "activation.reception": { bag: 5, step: "18", parts: [{ icon: "credit_card", label: "Prisaftale", color: "white" }] },
  "activation.campaigns": { bag: 5, step: "K2", parts: [] },
};

const BAG_OF_PHASE: Record<string, number> = { "Din virksomhed": 1, "Mål og sprog": 2, "Viden og svar": 3, "Test og godkendelse": 3, Kanaler: 4, Kampagner: 4, Aktivering: 5 };

export function build(t: { key: string; phase: string }, fallbackIndex: number): Build {
  return BUILD[t.key] ?? { bag: BAG_OF_PHASE[t.phase] ?? 4, step: String(fallbackIndex), parts: [] };
}

export const MANUAL_PDF = "/materiale/dialogbot-opsaetningsmanual.pdf";
