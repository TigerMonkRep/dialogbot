import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { AgreementForm } from "./client";

export type AgreementOut = {
  current: { version: number; model: string; monthly: { net_minor: number; gross_minor: number }; lead_fee: { net_minor: number; gross_minor: number }; campaign_call: { net_minor: number }; created_at: string } | null;
  plan: { monthly_net_minor: number; lead_fee_net_minor: number; campaign_call_net_minor: number };
};

/** The subscription (one offer). The owner confirms it; admins can see it. */
export default async function AgreementPage() {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Abonnementet kan ses af ejere og administratorer.</p>;
  }
  const a = await backend<AgreementOut>(`/workspaces/${ws.id}/agreement`);
  return <AgreementForm wsId={ws.id} current={a.current} plan={a.plan} canEdit={ws.role === "owner"} />;
}
