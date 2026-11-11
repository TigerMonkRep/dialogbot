import "server-only";
import { redirect } from "next/navigation";
import { backend, currentWorkspaceId } from "./api.server";

export type Workspace = { id: string; name: string; role: string; product_intent: string; knowledge_revision: number };

/** Without a business workspace: a Privat-only account (the API's user.home) goes to /privat/dag – never into the
 *  business set-up (F-JP-02, F-JE-03); anyone else to creating the first company. */
async function noWorkspace(): Promise<never> {
  const me = await backend<{ home?: string }>("/auth/me").catch(() => null);
  redirect(me?.home === "/privat/dag" ? "/privat/dag" : "/opsaetning/1");
}

/** Resolve the active workspace for server components; redirect to creation when none exists (Privat: to /privat). */
export async function requireWorkspace(): Promise<Workspace> {
  const list = await backend<Workspace[]>("/workspaces");
  if (list.length === 0) return noWorkspace();
  const wanted = await currentWorkspaceId();
  return list.find((w) => w.id === wanted) ?? list[0];
}

/** The active workspace, or null when the person has none yet (the setup page then creates the first one). */
export async function requireWorkspaceOrNull(): Promise<Workspace | null> {
  const list = await backend<Workspace[]>("/workspaces");
  if (list.length === 0) return null;
  const wanted = await currentWorkspaceId();
  return list.find((w) => w.id === wanted) ?? list[0];
}
