/** The guide's steps (Fürster 12/11 09:25): Virksomhed → Viden → the channels the customer chose (Telefon and/or Chat,
 *  plus Kalender when «Booke aftaler» is chosen) → Betaling. Only the relevant steps exist – nothing «sprunget over».
 *  Shared by the server (stepper, checklist on «I dag» and in settings) and the client (the «Videre» buttons). */
export type StepKey = "virksomhed" | "viden" | "telefon" | "chat" | "kalender" | "betaling";
export type StepState = "done" | "todo";
export type ChannelGoals = { inbound_phone: boolean; webchat: boolean; booking: boolean };

export const STEP_ORDER: StepKey[] = ["virksomhed", "viden", "telefon", "chat", "kalender", "betaling"];

/** The steps this workspace has, in order. */
export function stepsFor(g: ChannelGoals): StepKey[] {
  return STEP_ORDER.filter((k) => (k === "telefon" ? g.inbound_phone : k === "chat" ? g.webchat : k === "kalender" ? g.booking : true));
}

export const stepHref = (k: StepKey) => `/opsaetning/${k}`;

/** The step after `k` for these choices (Betaling is always last). */
export function nextStep(k: StepKey, g: ChannelGoals): StepKey {
  const list = stepsFor(g);
  const i = list.indexOf(k);
  return i >= 0 && i < list.length - 1 ? list[i + 1] : "betaling";
}

/** 1-based position of `k` in this workspace's steps (what the stepper and «trin N» say). */
export const stepNumber = (k: StepKey, g: ChannelGoals) => Math.max(1, stepsFor(g).indexOf(k) + 1);

