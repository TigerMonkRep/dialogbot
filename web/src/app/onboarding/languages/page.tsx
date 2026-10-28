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
      <div className="max-w-4xl mx-auto rounded-2xl bg-white p-space-md md:p-space-xl border-2 border-ink space-y-space-lg">
        <div>
          <span className="eyebrow">Sprog</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink mt-1">Eksplicit adskillelse af 4 sprogniveauer</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Kontrollér sprogparametre separat for drift, AI-forståelse og ledelsesrapportering.</p>
        </div>
        <LanguagesForm wsId={ws.id} settings={ls} canEdit={ws.role !== "reader"} />
      </div>
    </div>
  );
}
