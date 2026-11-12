import { redirect } from "next/navigation";
import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { nextStep, stepHref, stepNumber } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";
import { StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getRaw, getT } from "@/i18n/server";
import type { Webchat } from "../_parts/channels";
import { ChatStep } from "../_parts/chat-step";

/** Chat (only when «Svare på hjemmesiden» is chosen): where the chat may be shown, how it greets, the one line for the
 *  website and a preview to try it. It goes live for visitors when the subscription is in place. */
export default async function ChatStepPage() {
  const ws = await requireWorkspace();
  const staff = ws.role !== "reader";
  const [st, profile, webchat] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<{ legal_name: string; website_url: string | null }>(`/workspaces/${ws.id}/profile`),
    staff ? backend<Webchat>(`/workspaces/${ws.id}/webchat`).catch(() => null) : Promise.resolve(null),
  ]);
  if (!st.goals.webchat) redirect(stepHref(nextStep(st.goals.inbound_phone ? "telefon" : "viden", st.goals)));
  const t = await getT("setup.chatPage");
  const ts = await getT("setup.shell");
  const raw = await getRaw();
  const n = stepNumber("chat", st.goals);
  const next = nextStep("chat", st.goals);
  return (
    <SetupShell step="chat" steps={st.steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: staff }}>
      <StepHead n={n} eyebrow={t("eyebrow", { n, total: st.steps.length })} title={t("title")} intro={t("intro")} need={raw<[string, string, string?][]>("setup.chatPage.need")} needTitle={raw<string>("setup.need.title")} />
      {webchat
        ? <ChatStep wsId={ws.id} w={webchat} canManage={ws.role === "owner" || ws.role === "admin"} website={profile.website_url ?? ""} company={profile.legal_name || ws.name}
            nextHref={stepHref(next)} nextLabel={ts("next", { n: stepNumber(next, st.goals), label: ts(`labels.${next}`) })} status={t("status")} />
        : <p role="status" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("readOnly")}</p>}
    </SetupShell>
  );
}
