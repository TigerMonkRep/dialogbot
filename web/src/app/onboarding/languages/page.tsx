import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Card, Steps } from "@/components/ui";
import { LanguagesForm } from "./form";

export default async function LanguagesPage() {
  const ws = await requireWorkspace();
  const ls = await backend<Record<string, unknown>>(`/workspaces/${ws.id}/languages`);
  return (
    <div className="mx-auto max-w-2xl">
      <Steps current="/onboarding/languages" />
      <h1 className="mb-4 text-2xl font-extrabold text-primary-dark">Sprog</h1>
      <Card><LanguagesForm wsId={ws.id} settings={ls} canEdit={ws.role !== "reader"} /></Card>
    </div>
  );
}
