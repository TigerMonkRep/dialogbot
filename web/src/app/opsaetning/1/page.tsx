import { cookies } from "next/headers";
import { backend } from "@/lib/api.server";
import { REFERRAL_COOKIE } from "@/lib/config";
import { setupStatus } from "@/lib/setup.server";
import { requireWorkspaceOrNull } from "@/lib/workspace.server";
import { Need } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { CreateWorkspace, Step1, type Fact, type Goals, type Languages, type Profile } from "./step1";

/** Trin 1 af 3 – Virksomhed. */
export default async function Trin1({ searchParams }: { searchParams: Promise<{ ny?: string }> }) {
  const { ny } = await searchParams;
  // ?ny=1: «Byg en Dialogbot til en anden virksomhed» – a fresh workspace, not the current one.
  const ws = ny ? null : await requireWorkspaceOrNull();
  const me = await backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me");
  const head = (
    <div className="flex flex-col gap-3 mb-6">
      <span className="eyebrow">Byg din Dialogbot · trin 1 af 3 · ca. 5 min</span>
      <h1 className="font-display font-extrabold text-[34px] md:text-[44px] leading-[1.02] tracking-[-1px] text-ink">Hvem er I – og hvad skal den gøre?</h1>
      <p className="text-[16px] text-ink-soft max-w-[620px]">Ét trin. Vi henter det meste fra jeres hjemmeside – du retter kun det, der er forkert. Det kan ændres senere ved at sige det til assistenten.</p>
      <Need items={[["1×", "hjemmeside-adresse"], ["1×", "CVR-nummer", "eller bare navnet"], ["1×", "det nummer, kunderne ringer til"]]} />
    </div>
  );
  if (!ws) {
    const referral = (await cookies()).get(REFERRAL_COOKIE)?.value ?? null;
    return (
      <SetupShell step={1} steps={["current", "todo", "todo"]} wide later>
        {head}
        <CreateWorkspace verified={me.email_verified} defaultIntent={me.signup_intent ?? "reception"} referralLink={referral} />
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
    <SetupShell step={1} steps={st.steps} workspaceName={ws.name} wide later>
      {head}
      <Step1 wsId={ws.id} canEdit={canEdit} canApprove={canApprove} aiReady={capOn("knowledge.source_import")} cvrReady={capOn("cvr.lookup")} profile={profile} goals={goals} languages={languages} facts={facts} />
    </SetupShell>
  );
}
