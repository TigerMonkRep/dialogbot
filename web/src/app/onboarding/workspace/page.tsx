import { backend } from "@/lib/api.server";
import type { Workspace } from "@/lib/workspace.server";
import { Breadcrumb, Icon, SectionLabel, Steps, Tag } from "@/components/ui";
import { WorkspaceForm, WorkspaceList } from "./form";

/** A06 — workspace overview after Stitch "a06_o01_o02" left module. */
export default async function WorkspacePage() {
  const [list, me] = await Promise.all([backend<Workspace[]>("/workspaces"), backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me")]);
  const intent = { reception: "Reception", campaigns: "Kampagner", both: "Reception + Kampagner" }[me.signup_intent ?? "reception"];
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="space-y-1">
        <Breadcrumb items={[["Onboarding"], ["Fase A06 → O01", "/onboarding/workspace"]]} />
        <h1 className="font-display text-headline-lg text-primary tracking-tight">Konfiguration af virksomhedens AI-agent</h1>
        <div className="inline-flex items-center gap-space-xs px-space-md py-1 rounded-lg bg-secondary-container text-on-secondary-container text-label-md"><Icon name="bookmark_added" size={16} />Beholdt hensigt (fra tilmelding): <strong>{intent}</strong></div>
      </div>
      <Steps current="/onboarding/workspace" />
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
        <div className="lg:col-span-7 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div className="flex items-start justify-between"><div><SectionLabel>A06 Modul</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Arbejdsrumsoversigt</h3><p className="text-body-sm text-on-surface-variant">Vælg eller opret arbejdsrum</p></div><Tag tone="secondary"><Icon name="verified_user" size={12} /> Rolle: {list[0]?.role === "owner" ? "Ejer" : "Medlem"}</Tag></div>
          <WorkspaceList workspaces={list} />
        </div>
        <div className="lg:col-span-5 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div><SectionLabel>Nyt arbejdsrum</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Opret virksomhed</h3><p className="text-body-sm text-on-surface-variant">Hvert arbejdsrum har sin egen viden, sit eget team og sine egne indstillinger. Data deles aldrig på tværs.</p></div>
          <WorkspaceForm defaultIntent={me.signup_intent ?? "reception"} verified={me.email_verified} />
        </div>
      </div>
    </div>
  );
}
