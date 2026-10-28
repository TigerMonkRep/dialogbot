import { cookies } from "next/headers";
import { backend, currentWorkspaceId } from "@/lib/api.server";
import { REFERRAL_COOKIE } from "@/lib/config";
import type { Workspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { FlowBar } from "@/components/onboarding";
import { WorkspaceCards, WorkspaceForm } from "./form";

/** A06 — choose or create a workspace (Stitch a06 module + creation panel). */
export default async function WorkspacePage() {
  const referralLink = (await cookies()).get(REFERRAL_COOKIE)?.value ?? null;
  const [list, me, currentId] = await Promise.all([backend<Workspace[]>("/workspaces"), backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me"), currentWorkspaceId()]);
  return (
    <div className="space-y-space-xl">
      <FlowBar step={1} intent={me.signup_intent} />
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-xl items-start">
        <div className="xl:col-span-8 bg-surface-container-lowest p-space-md md:p-space-xl rounded-2xl border-2 border-ink space-y-space-lg">
          <div>
            <div className="flex items-center gap-space-sm">
              <span className="px-2.5 py-0.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">Arbejdsrum</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Arbejdsrumsoversigt</span>
            </div>
            <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink mt-0.5">Vælg eller opret arbejdsrum</h1>
          </div>
          <WorkspaceCards workspaces={list} currentId={currentId} />
        </div>
        <div className="xl:col-span-4 bg-surface-container-lowest p-space-md md:p-space-xl rounded-2xl border-2 border-ink space-y-space-lg">
          <div className="flex items-center gap-space-sm">
            <div className="w-11 h-11 rounded-xl bg-accent text-white flex items-center justify-center flex-shrink-0"><Icon name="add_business" size={22} /></div>
            <div>
              <h2 className="font-display font-extrabold text-[22px] leading-[1.15] text-ink">Nyt arbejdsrum</h2>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Hvert arbejdsrum har egen viden, eget team og egne indstillinger. Data deles aldrig på tværs.</p>
            </div>
          </div>
          <WorkspaceForm defaultIntent={me.signup_intent ?? "reception"} verified={me.email_verified} referralLink={referralLink} />
        </div>
      </div>
    </div>
  );
}
