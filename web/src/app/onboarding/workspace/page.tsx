import { backend, currentWorkspaceId } from "@/lib/api.server";
import type { Workspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { FlowBar } from "@/components/onboarding";
import { WorkspaceCards, WorkspaceForm } from "./form";

/** A06 — choose or create a workspace (Stitch a06 module + creation panel). */
export default async function WorkspacePage() {
  const [list, me, currentId] = await Promise.all([backend<Workspace[]>("/workspaces"), backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me"), currentWorkspaceId()]);
  return (
    <div className="space-y-space-xl">
      <FlowBar step={1} intent={me.signup_intent} />
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-xl items-start">
        <div className="xl:col-span-8 bg-surface-container-lowest p-space-md md:p-space-xl rounded-xl shadow-sm space-y-space-lg">
          <div>
            <div className="flex items-center gap-space-sm">
              <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold uppercase tracking-wider">Arbejdsrum</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Arbejdsrumsoversigt</span>
            </div>
            <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight mt-0.5">Vælg eller opret arbejdsrum</h1>
          </div>
          <WorkspaceCards workspaces={list} currentId={currentId} />
        </div>
        <div className="xl:col-span-4 bg-surface-container-lowest p-space-md md:p-space-xl rounded-xl shadow-sm space-y-space-lg">
          <div className="flex items-center gap-space-sm">
            <div className="w-9 h-9 rounded-lg bg-primary-container text-secondary-fixed flex items-center justify-center"><Icon name="add_business" size={20} /></div>
            <div>
              <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Nyt arbejdsrum</h2>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Hvert arbejdsrum har egen viden, eget team og egne indstillinger. Data deles aldrig på tværs.</p>
            </div>
          </div>
          <WorkspaceForm defaultIntent={me.signup_intent ?? "reception"} verified={me.email_verified} />
        </div>
      </div>
    </div>
  );
}
