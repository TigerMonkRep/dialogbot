import { redirect } from "next/navigation";
import { setupStatus } from "@/lib/setup.server";
import { stepHref } from "@/lib/setup-steps";
import { requireWorkspaceOrNull } from "@/lib/workspace.server";

/** /opsaetning: the first step that is not done (Virksomhed for a new customer without a workspace). */
export default async function Opsaetning() {
  const ws = await requireWorkspaceOrNull();
  if (!ws) redirect(stepHref("virksomhed"));
  const st = await setupStatus(ws.id, ws.role);
  redirect(stepHref(st.next));
}
