import "server-only";
import { backend } from "./api.server";
import { profileIsDone } from "./setup-done";

export type StepState = "done" | "current" | "todo" | "skipped";
export type SetupStatus = {
  goals: { version: number; product_intent: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean; guidance_mode: string; conversation_goals: string[] };
  telephony: { status: { code: string }; active: boolean } | null;
  /** The website chat: on (enabled) or not; null for readers (webchat.read is staff+). */
  webchat: { enabled: boolean } | null;
  profileDone: boolean;
  steps: [StepState, StepState, StepState];
  done: boolean;
  next: 1 | 2 | 3;
};

const CALENDARS = ["google_calendar", "microsoft_calendar"];

/** Where the workspace is in the three steps – read from the real data only, so what is done on the ordinary settings
 *  pages (Virksomhed, Telefoni, Webchat, Integrationer) counts exactly as when it is done in the guide.
 *  Step 3 is done when the chosen channel is on: the phone (on or paused after having been on), else the website chat. */
export async function setupStatus(wsId: string, role: string): Promise<SetupStatus> {
  const staff = role !== "reader";
  const [goals, profile, tel, chat, integrations] = await Promise.all([
    backend<SetupStatus["goals"]>(`/workspaces/${wsId}/goals`),
    backend<{ legal_name: string; description: string; phone: string | null }>(`/workspaces/${wsId}/profile`),
    staff ? backend<NonNullable<SetupStatus["telephony"]>>(`/workspaces/${wsId}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ enabled: boolean }>(`/workspaces/${wsId}/webchat`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ items: { key: string; status: string }[] }>(`/workspaces/${wsId}/integrations`).catch(() => null) : Promise.resolve(null),
  ]);
  const code = tel?.status.code ?? "not_started";
  const phoneOn = code === "active" || code === "paused";
  const profileDone = profileIsDone(profile, goals.inbound_phone);
  const s3 = goals.inbound_phone ? phoneOn : goals.webchat ? Boolean(chat?.enabled) : profileDone;
  const skip2 = !goals.booking;
  const calendar = Boolean(integrations?.items.some((c) => CALENDARS.includes(c.key) && c.status === "connected"));
  const s1: StepState = profileDone ? "done" : "current";
  const s2: StepState = skip2 ? "skipped" : calendar ? "done" : "todo";
  const steps: SetupStatus["steps"] = [s1, s2, s3 ? "done" : "todo"];
  const next: 1 | 2 | 3 = !profileDone ? 1 : skip2 || calendar ? 3 : 2;
  return { goals, telephony: tel, webchat: chat ? { enabled: chat.enabled } : null, profileDone, steps, done: profileDone && s3, next };
}

export type BillingState = { confirmed: boolean; card: boolean; configured: boolean; paid: boolean };

/** The subscription: confirmed (the agreement) and – when card payment is set up – a card on file. Erhverv has no
 *  free trial. null for roles that cannot see billing (staff, reader): they are never sent to payment. */
export async function billingState(wsId: string, role: string): Promise<BillingState | null> {
  if (role !== "owner" && role !== "admin") return null;
  const [agr, acc] = await Promise.all([
    backend<{ current: { model: string } | null }>(`/workspaces/${wsId}/agreement`).catch(() => null),
    backend<{ configured: boolean; card: unknown | null }>(`/workspaces/${wsId}/billing/account`).catch(() => null),
  ]);
  if (!agr || !acc) return null;
  const confirmed = Boolean(agr.current && agr.current.model !== "B");
  const card = Boolean(acc.card);
  // Without card payment set up (no Stripe) there is nothing more to do than confirming: invoices come by e-mail.
  return { confirmed, card, configured: acc.configured, paid: confirmed && (card || !acc.configured) };
}
