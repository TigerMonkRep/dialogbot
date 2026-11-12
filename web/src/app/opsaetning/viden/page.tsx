import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { nextStep, stepNumber } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";
import { StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getRaw, getT } from "@/i18n/server";
import type { Item, SourceImport } from "@/app/app/(admin)/viden/types";
import { Viden } from "./viden";

/** Trin 2 – Viden: what Dialogbot answers from. The website (read again), a file and pasted text become suggestions,
 *  reviewed here per category; nothing reaches the customers before it is approved. */
export default async function VidenStep() {
  const ws = await requireWorkspace();
  const [st, items, caps, profile, latest] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<{ items: Item[] }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<{ items: { key: string; status: string }[] }>("/integrations/capabilities"),
    backend<{ website_url: string | null }>(`/workspaces/${ws.id}/profile`),
    backend<{ import: SourceImport | null }>(`/workspaces/${ws.id}/knowledge/imports/latest`).catch(() => ({ import: null })),
  ]);
  const t = await getT("setup.videnPage");
  const raw = await getRaw();
  const review = items.items.filter((i) => i.open_draft?.source_type === "extraction");
  const approved = items.items.filter((i) => i.approved_version).length;
  const aiReady = caps.items.some((c) => c.key === "knowledge.source_import" && c.status !== "not_implemented");
  const n = stepNumber("viden", st.goals);
  return (
    <SetupShell step="viden" steps={st.steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: ws.role !== "reader" }}>
      <StepHead n={n} eyebrow={t("eyebrow", { n, total: st.steps.length })} title={t("title")} intro={t("intro")} need={raw<[string, string, string?][]>("setup.videnPage.need")} needTitle={raw<string>("setup.need.title")} />
      <Viden wsId={ws.id} canDraft={ws.role !== "reader"} canApprove={ws.role === "owner" || ws.role === "admin"} aiReady={aiReady}
        website={profile.website_url ?? ""} latest={latest.import} review={review} approved={approved} next={nextStep("viden", st.goals)} nextN={stepNumber(nextStep("viden", st.goals), st.goals)} />
    </SetupShell>
  );
}
