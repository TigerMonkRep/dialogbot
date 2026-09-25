import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Card, Steps } from "@/components/ui";
import { KnowledgeList, NewItemForm, ReviewQueue } from "./client";

export type Version = { id: string; item_id: string; version_no: number; status: string; title: string; content: Record<string, unknown>; edit_version: number; submitted_at: string | null };
export type Item = { id: string; kind: string; key: string; approved_version: Version | null; open_draft: Version | null };

/** K01/K03/K04/K05: approved knowledge, drafts, review queue, approval. */
export default async function KnowledgePage() {
  const ws = await requireWorkspace();
  const [items, queue, active] = await Promise.all([
    backend<{ items: Item[]; total: number }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Version[]>(`/workspaces/${ws.id}/knowledge/review-queue`),
    backend<{ knowledge_revision: number; items: unknown[] }>(`/workspaces/${ws.id}/assistant/knowledge`),
  ]);
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const canDraft = ws.role !== "reader";
  return (
    <div className="mx-auto max-w-4xl">
      <Steps current="/app/knowledge" />
      <div className="mb-4 flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-2xl font-extrabold text-primary-dark">Viden</h1>
        <p className="text-sm text-muted">Assistenten ser {active.items.length} godkendte emner · revision {active.knowledge_revision}</p>
      </div>
      {queue.length > 0 && <Card title={`Til gennemgang (${queue.length})`} className="mb-4"><ReviewQueue wsId={ws.id} queue={queue} canApprove={canApprove} /></Card>}
      <Card title="Emner" className="mb-4"><KnowledgeList wsId={ws.id} items={items.items} canDraft={canDraft} canApprove={canApprove} /></Card>
      {canDraft && <Card title="Nyt vidensemne"><NewItemForm wsId={ws.id} /></Card>}
      <p className="mt-4 text-xs text-muted">Kildeimport fra hjemmeside og dokumenter er ikke implementeret endnu; al viden indtastes manuelt og skal godkendes af en administrator, før assistenten må bruge den.</p>
    </div>
  );
}
