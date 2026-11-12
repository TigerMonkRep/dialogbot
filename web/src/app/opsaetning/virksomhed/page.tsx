import { cookies } from "next/headers";
import { backend } from "@/lib/api.server";
import { REFERRAL_COOKIE } from "@/lib/config";
import { setupStatus } from "@/lib/setup.server";
import { stepsFor } from "@/lib/setup-steps";
import { requireWorkspaceOrNull } from "@/lib/workspace.server";
import { StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getRaw, getT } from "@/i18n/server";
import { CreateWorkspace, Step1, type Fact, type Goals, type Languages, type Profile } from "./step1";

/** Trin 1 – Virksomhed: the website first (it fills in name, phone and address), then the channels, then the rest. */
export default async function Virksomhed({ searchParams }: { searchParams: Promise<{ ny?: string }> }) {
  const { ny } = await searchParams;
  // ?ny=1: «Byg en Dialogbot til en anden virksomhed» – a fresh workspace, not the current one.
  const ws = ny ? null : await requireWorkspaceOrNull();
  const me = await backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me");
  const t = await getT("setup.step1Page");
  const raw = await getRaw();
  const head = (total: number) => <StepHead n={1} eyebrow={t("eyebrow", { total })} title={t("title")} intro={t("intro")} need={raw<[string, string, string?][]>("setup.step1Page.need")} needTitle={raw<string>("setup.need.title")} />;
  if (!ws) {
    const referral = (await cookies()).get(REFERRAL_COOKIE)?.value ?? null;
    const steps = stepsFor({ inbound_phone: true, webchat: false, booking: false }).map((key) => ({ key, state: "todo" as const }));
    return (
      <SetupShell step="virksomhed" steps={steps} wide>
        {head(steps.length)}
        <CreateWorkspace verified={me.email_verified} defaultIntent={me.signup_intent && me.signup_intent !== "privat" ? me.signup_intent : "reception"} referralLink={referral} />
      </SetupShell>
    );
  }
  const canEdit = ws.role !== "reader";
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const [profile, goals, languages, items, caps, st] = await Promise.all([
    backend<Profile>(`/workspaces/${ws.id}/profile`),
    backend<Goals>(`/workspaces/${ws.id}/goals`),
    backend<Languages>(`/workspaces/${ws.id}/languages`),
    backend<{ items: Fact[] }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<{ items: { key: string; status: string }[] }>("/integrations/capabilities"),
    setupStatus(ws.id, ws.role),
  ]);
  const capOn = (k: string) => caps.items.some((c) => c.key === k && c.status !== "not_implemented");
  const facts = items.items.filter((i) => i.kind === "opening_hours" || i.kind === "coverage_area");
  return (
    <SetupShell step="virksomhed" steps={st.steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: canEdit }}>
      {head(st.steps.length)}
      <Step1 wsId={ws.id} canEdit={canEdit} canApprove={canApprove} aiReady={capOn("knowledge.source_import")} cvrReady={capOn("cvr.lookup")} profile={profile} goals={goals} languages={languages} facts={facts} done={st.profileDone} />
    </SetupShell>
  );
}
