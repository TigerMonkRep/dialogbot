import "server-only";
import { backend } from "./api.server";
import { profileIsDone } from "./setup-done";
import { stepsFor, type StepKey, type StepState } from "./setup-steps";

export type { StepKey, StepState } from "./setup-steps";
/** `paid` is the plain rule; `graceEnds` is set while a paid subscription that stopped being paid (card expired/removed,
 *  payment failed) still runs – 7 days, Fürster 12/11 (backend billing.grace). */
export type BillingState = { confirmed: boolean; card: boolean; configured: boolean; paid: boolean; graceEnds: string | null };
type Tel = { status: { code: string }; active: boolean; business_number: string | null; verified: boolean; documents: { required: boolean; status: string }; subscription_paid?: boolean };
type Chat = { enabled: boolean; available: boolean; setup_missing?: string[]; unavailable_reasons: string[]; subscription_paid?: boolean };

export type SetupStatus = {
  goals: { version: number; product_intent: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean; guidance_mode: string; conversation_goals: string[] };
  telephony: Tel | null;
  /** The website chat: on (enabled) and live for visitors (available); null for readers (webchat.read is staff+). */
  webchat: { enabled: boolean; live: boolean } | null;
  billing: BillingState | null;
  profileDone: boolean;
  /** This workspace's steps in order (only the relevant ones) and whether each is done – the one truth for the stepper,
   *  the guide's buttons and the checklist on «I dag» and in settings. */
  steps: { key: StepKey; state: StepState }[];
  /** Everything before Betaling is done (set up in the guide or by hand on the settings pages). */
  setupDone: boolean;
  /** The subscription is paid (confirmed + card, or confirmed where card payment is not set up). */
  paid: boolean;
  /** Every chosen channel is live: the phone on (or paused after having been on), the website chat answering visitors. */
  live: boolean;
  /** All steps done: set up, paid and live. */
  done: boolean;
  /** The first step that is not done (Betaling when all is done). */
  next: StepKey;
};

const CALENDARS = ["google_calendar", "microsoft_calendar"];

/** The subscription: confirmed (the agreement) and – when card payment is set up – a card on file. Erhverv has no
 *  free trial. null for roles that cannot see billing (staff, reader): they are never sent to payment. */
export async function billingState(wsId: string, role: string): Promise<BillingState | null> {
  if (role !== "owner" && role !== "admin") return null;
  const [agr, acc] = await Promise.all([
    backend<{ current: { model: string } | null }>(`/workspaces/${wsId}/agreement`).catch(() => null),
    backend<{ configured: boolean; card: unknown | null; subscription?: { paid: boolean; in_grace: boolean; grace_ends: string | null } }>(`/workspaces/${wsId}/billing/account`).catch(() => null),
  ]);
  if (!agr || !acc) return null;
  const confirmed = Boolean(agr.current && agr.current.model !== "B");
  const card = Boolean(acc.card);
  // Without card payment set up (no Stripe) there is nothing more to do than confirming: invoices come by e-mail.
  const sub = acc.subscription;
  return { confirmed, card, configured: acc.configured, paid: sub ? sub.paid : confirmed && (card || !acc.configured),
    graceEnds: sub?.in_grace ? sub.grace_ends : null };
}

/** Where the workspace is in the guide – read from the real data only, so what is done on the ordinary settings pages
 *  (Virksomhed, Viden, Telefoni, Webchat, Integrationer, Konto) counts exactly as when it is done in the guide. */
export async function setupStatus(wsId: string, role: string): Promise<SetupStatus> {
  const staff = role !== "reader";
  const [goals, profile, tel, chat, integrations, items, billing] = await Promise.all([
    backend<SetupStatus["goals"]>(`/workspaces/${wsId}/goals`),
    backend<{ legal_name: string; description: string; phone: string | null }>(`/workspaces/${wsId}/profile`),
    staff ? backend<Tel>(`/workspaces/${wsId}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<Chat>(`/workspaces/${wsId}/webchat`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ items: { key: string; status: string }[] }>(`/workspaces/${wsId}/integrations`).catch(() => null) : Promise.resolve(null),
    backend<{ items: { approved_version: unknown | null }[] }>(`/workspaces/${wsId}/knowledge/items?limit=200`).catch(() => null),
    billingState(wsId, role),
  ]);
  const code = tel?.status.code ?? "not_started";
  const phoneLive = code === "active" || code === "paused";
  // Everything about the number that can be done before paying: given, confirmed with the code, papers sent (if needed).
  const phoneSet = phoneLive || Boolean(tel?.business_number && tel.verified && (!tel.documents.required || ["submitted", "approved"].includes(tel.documents.status)));
  const chatMissing = chat?.setup_missing ?? chat?.unavailable_reasons.filter((r) => r !== "disabled" && r !== "subscription_required") ?? ["unknown"];
  const chatLive = Boolean(chat?.available);
  const chatSet = chatLive || (chat !== null && chatMissing.length === 0);
  const profileDone = profileIsDone(profile, goals.inbound_phone);
  const knowledge = Boolean(items?.items.some((i) => i.approved_version));
  const calendar = Boolean(integrations?.items.some((c) => CALENDARS.includes(c.key) && c.status === "connected"));
  // Staff and readers cannot see billing; the channels tell whether it is paid.
  const paid = billing ? billing.paid : Boolean(chat?.subscription_paid ?? tel?.subscription_paid);
  const live = (!goals.inbound_phone || phoneLive) && (!goals.webchat || chatLive);
  const doneOf: Record<StepKey, boolean> = {
    virksomhed: profileDone, viden: knowledge, telefon: phoneSet, chat: chatSet, kalender: calendar,
    betaling: paid && live,
  };
  const keys = stepsFor(goals);
  const steps = keys.map((key) => ({ key, state: (doneOf[key] ? "done" : "todo") as StepState }));
  const setupDone = steps.every((s) => s.key === "betaling" || s.state === "done");
  const next = steps.find((s) => s.state !== "done")?.key ?? "betaling";
  return {
    goals, telephony: tel, webchat: chat ? { enabled: chat.enabled, live: chatLive } : null, billing, profileDone, steps,
    setupDone, paid, live, done: steps.every((s) => s.state === "done"), next,
  };
}
