import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Integrations, type Catalogue } from "./client";

/** I01: the customer's own systems the assistant can act in – honest status per connector, connect/disconnect,
 *  settings, tests and the trail of executed actions. Nothing is shown as connected unless a real call succeeded. */
export default async function IntegrationsPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">Integrationer kan ses af medarbejdere, administratorer og ejere.</p>;
  const data = await backend<Catalogue>(`/workspaces/${ws.id}/integrations`);
  return <Integrations wsId={ws.id} data={data} canManage={ws.role === "owner" || ws.role === "admin"} />;
}
