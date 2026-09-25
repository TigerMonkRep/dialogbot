import "server-only";
import { redirect } from "next/navigation";
import { backend, currentWorkspaceId } from "./api.server";

export type Workspace = { id: string; name: string; role: string; product_intent: string; knowledge_revision: number };

/** Resolve the active workspace for server components; redirect to creation when none exists. */
export async function requireWorkspace(): Promise<Workspace> {
  const list = await backend<Workspace[]>("/workspaces");
  if (list.length === 0) redirect("/onboarding/workspace");
  const wanted = await currentWorkspaceId();
  return list.find((w) => w.id === wanted) ?? list[0];
}
