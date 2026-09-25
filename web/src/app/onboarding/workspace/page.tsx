import { backend } from "@/lib/api.server";
import type { Workspace } from "@/lib/workspace.server";
import { Card, Steps } from "@/components/ui";
import { WorkspaceForm, WorkspaceList } from "./form";

/** A06: create or choose a workspace; product intent from signup is the default. */
export default async function WorkspacePage() {
  const [list, me] = await Promise.all([backend<Workspace[]>("/workspaces"), backend<{ signup_intent: string | null; email_verified: boolean }>("/auth/me")]);
  return (
    <div className="mx-auto max-w-2xl">
      <Steps current="/onboarding/workspace" />
      <h1 className="mb-4 text-2xl font-extrabold text-primary-dark">Arbejdsrum</h1>
      {list.length > 0 && <Card title="Vælg eksisterende" className="mb-4"><WorkspaceList workspaces={list} /></Card>}
      <Card title="Opret nyt arbejdsrum"><WorkspaceForm defaultIntent={me.signup_intent ?? "reception"} verified={me.email_verified} /></Card>
    </div>
  );
}
