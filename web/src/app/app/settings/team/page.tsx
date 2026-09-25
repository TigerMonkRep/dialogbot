import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Badge, Card } from "@/components/ui";
import { InviteForm, MemberRow } from "./client";

type Member = { id: string; user_id: string; email: string; display_name: string; role: string };
type Inv = { id: string; email: string; role: string; status: string; expires_at: string };

/** S02: members, invitations, roles. Server enforces role limits; UI only mirrors them. */
export default async function TeamPage() {
  const ws = await requireWorkspace();
  const admin = ws.role === "owner" || ws.role === "admin";
  const [members, invitations, me] = await Promise.all([
    backend<Member[]>(`/workspaces/${ws.id}/members`),
    admin ? backend<Inv[]>(`/workspaces/${ws.id}/invitations`) : Promise.resolve([] as Inv[]),
    backend<{ id: string }>("/auth/me"),
  ]);
  return (
    <div className="mx-auto max-w-3xl">
      <h1 className="mb-4 text-2xl font-extrabold text-primary-dark">Team</h1>
      <Card title="Medlemmer" className="mb-4">
        <ul className="divide-y divide-line text-sm">{members.map((m) => <MemberRow key={m.id} wsId={ws.id} m={m} myRole={ws.role} isMe={m.user_id === me.id} />)}</ul>
      </Card>
      {admin && (
        <>
          <Card title="Invitationer" className="mb-4">
            {invitations.length === 0 ? <p className="text-sm text-muted">Ingen invitationer.</p> : (
              <ul className="divide-y divide-line text-sm">{invitations.map((i) => <li key={i.id} className="flex flex-wrap justify-between gap-2 py-2"><span>{i.email} · {i.role}</span><span className="flex items-center gap-2"><Badge status={i.status} /><span className="text-xs text-muted">udløber {new Date(i.expires_at).toLocaleDateString("da-DK")}</span></span></li>)}</ul>
            )}
          </Card>
          <Card title="Invitér kollega"><InviteForm wsId={ws.id} myRole={ws.role} /></Card>
        </>
      )}
    </div>
  );
}
