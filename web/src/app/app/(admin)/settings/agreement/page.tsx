import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { AgreementForm } from "./client";

export type AgreementOut = { current: { version: number; model: string; monthly: { net_minor: number }; lead_fee: { net_minor: number; gross_minor: number }; created_at: string } | null };

/** Reception price agreement (model A or B). Owners choose; admins can see it. No invoicing yet. */
export default async function AgreementPage() {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Prisaftalen kan ses af ejere og administratorer.</p>;
  }
  const a = await backend<AgreementOut>(`/workspaces/${ws.id}/agreement`);
  return <AgreementForm wsId={ws.id} current={a.current} canEdit={ws.role === "owner"} />;
}
