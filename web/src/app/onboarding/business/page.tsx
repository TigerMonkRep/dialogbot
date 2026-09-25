import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Card, Steps } from "@/components/ui";
import { BusinessForm, Categories } from "./form";

/** O01/S01: manual business setup, optional URL, multiple/custom categories. */
export default async function BusinessPage() {
  const ws = await requireWorkspace();
  const [profile, cats, suggested] = await Promise.all([
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/profile`),
    backend<{ id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean }[]>(`/workspaces/${ws.id}/categories`),
    backend<{ items: { slug: string; label: string }[] }>(`/workspaces/${ws.id}/categories/suggested`),
  ]);
  return (
    <div className="mx-auto max-w-2xl">
      <Steps current="/onboarding/business" />
      <h1 className="mb-4 text-2xl font-extrabold text-primary-dark">Virksomhedsoplysninger</h1>
      <Card className="mb-4"><BusinessForm wsId={ws.id} profile={profile} canEdit={ws.role !== "reader"} /></Card>
      <Card title="Branchekategorier"><Categories wsId={ws.id} categories={cats} suggested={suggested.items} canEdit={ws.role !== "reader"} /></Card>
    </div>
  );
}
