import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { FlowBar } from "@/components/onboarding";
import { GoalsForm } from "./form";

export default async function GoalsPage() {
  const ws = await requireWorkspace();
  const goals = await backend<Record<string, unknown>>(`/workspaces/${ws.id}/goals`);
  return (
    <div className="space-y-space-xl">
      <FlowBar step={2} />
      <div className="max-w-4xl mx-auto rounded-xl bg-surface-container-lowest p-space-md md:p-space-xl shadow-sm space-y-space-lg">
        <div>
          <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Mål og kanalarkitektur</span>
          <h1 className="font-headline-sm text-headline-sm text-primary font-bold mt-1">Valgte driftsmål &amp; automatiseringer</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Vælg produkt og kanaler. Din personlige plan beregnes ud fra dine valg.</p>
        </div>
        <GoalsForm wsId={ws.id} goals={goals} canEdit={ws.role !== "reader"} />
      </div>
    </div>
  );
}
