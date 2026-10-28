import "server-only";
import { backend } from "./api.server";

export type StepState = "done" | "current" | "todo" | "skipped";
export type SetupStatus = {
  goals: { version: number; product_intent: string; inbound_phone: boolean; webchat: boolean; callback: boolean; booking: boolean; guidance_mode: string; conversation_goals: string[] };
  telephony: { status: { code: string }; active: boolean } | null;
  profileDone: boolean;
  steps: [StepState, StepState, StepState];
  done: boolean;
  next: 1 | 2 | 3;
};

const profileDoneEarly = (profile: { legal_name: string; description: string; phone: string | null }, _goals: unknown) =>
  Boolean(profile.legal_name && profile.description.trim() && profile.phone);

/** Where the workspace is in the three steps. Step 3 is done when the phone is on (or paused after having been on). */
export async function setupStatus(wsId: string, role: string): Promise<SetupStatus> {
  const staff = role !== "reader";
  const [goals, profile, tel] = await Promise.all([
    backend<SetupStatus["goals"]>(`/workspaces/${wsId}/goals`),
    backend<{ legal_name: string; description: string; phone: string | null }>(`/workspaces/${wsId}/profile`),
    staff ? backend<NonNullable<SetupStatus["telephony"]>>(`/workspaces/${wsId}/telephony`).catch(() => null) : Promise.resolve(null),
  ]);
  const code = tel?.status.code ?? "not_started";
  const phoneOn = code === "active" || code === "paused";
  const s3 = goals.inbound_phone ? phoneOn : profileDoneEarly(profile, goals);
  const profileDone = profileDoneEarly(profile, goals);
  const skip2 = !goals.booking;
  const s1: StepState = profileDone ? "done" : "current";
  const s2: StepState = skip2 ? "skipped" : "todo"; // marked done by the page once a calendar is connected
  const steps: SetupStatus["steps"] = [s1, s2, s3 ? "done" : "todo"];
  const next: 1 | 2 | 3 = !profileDone ? 1 : skip2 ? 3 : 2;
  return { goals, telephony: tel, profileDone, steps, done: profileDone && s3, next };
}
