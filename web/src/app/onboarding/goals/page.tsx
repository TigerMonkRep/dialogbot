import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Card, Steps } from "@/components/ui";
import { GoalsForm } from "./form";

export default async function GoalsPage() {
  const ws = await requireWorkspace();
  const goals = await backend<Record<string, unknown>>(`/workspaces/${ws.id}/goals`);
  return (
    <div className="mx-auto max-w-2xl">
      <Steps current="/onboarding/goals" />
      <h1 className="mb-4 font-display text-headline-lg text-primary">Mål og kapabiliteter</h1>
      <Card><GoalsForm wsId={ws.id} goals={goals} canEdit={ws.role !== "reader"} /></Card>
    </div>
  );
}
