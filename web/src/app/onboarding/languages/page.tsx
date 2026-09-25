import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { FlowBar } from "@/components/onboarding";
import { LanguagesForm } from "./form";

export default async function LanguagesPage() {
  const ws = await requireWorkspace();
  const ls = await backend<Record<string, unknown>>(`/workspaces/${ws.id}/languages`);
  return (
    <div className="space-y-space-xl">
      <FlowBar step={2} />
      <div className="max-w-4xl mx-auto rounded-xl bg-surface-container-lowest p-space-md md:p-space-xl shadow-sm space-y-space-lg">
        <div>
          <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Sprog (O04)</span>
          <h1 className="font-headline-sm text-headline-sm text-primary font-bold mt-1">Eksplicit adskillelse af 4 sprogniveauer</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Kontrollér sprogparametre separat for drift, AI-forståelse og ledelsesrapportering.</p>
        </div>
        <LanguagesForm wsId={ws.id} settings={ls} canEdit={ws.role !== "reader"} />
      </div>
    </div>
  );
}
