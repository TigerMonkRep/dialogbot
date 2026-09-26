import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { InviteForm, InvitationActions, MemberRow, ROLE_LABEL } from "./client";

type Member = { id: string; user_id: string; email: string; display_name: string; role: string };
type Inv = { id: string; email: string; role: string; status: string; expires_at: string };
const INV_STATUS: Record<string, [string, string]> = {
  pending: ["Afventer", "bg-secondary-container text-on-secondary-container"], accepted: ["Accepteret", "bg-surface-container-high text-primary"],
  revoked: ["Tilbagekaldt", "bg-surface-container-highest text-on-surface-variant"], expired: ["Udløbet", "bg-error-container text-on-error-container"],
};

/** S02: members, invitations, roles. Server enforces role limits; the UI only mirrors them. */
export default async function TeamPage() {
  const ws = await requireWorkspace();
  const admin = ws.role === "owner" || ws.role === "admin";
  const [members, invitations, me] = await Promise.all([
    backend<Member[]>(`/workspaces/${ws.id}/members`),
    admin ? backend<Inv[]>(`/workspaces/${ws.id}/invitations`) : Promise.resolve([] as Inv[]),
    backend<{ id: string }>("/auth/me"),
  ]);
  return (
    <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-lg items-start">
      <div className="xl:col-span-8 flex flex-col gap-space-lg">
        <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
          <div className="flex items-start justify-between gap-space-md">
            <div>
              <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Indstillinger</span>
              <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Medlemmer i {ws.name}</h2>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Roller styrer, hvem der må redigere, godkende viden og se aktivitetsloggen.</p>
            </div>
            <span className="px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant font-label-sm text-label-sm font-medium flex-shrink-0">{members.length} medlemmer</span>
          </div>
          <ul className="flex flex-col gap-2">{members.map((m) => <MemberRow key={m.id} wsId={ws.id} m={m} myRole={ws.role} isMe={m.user_id === me.id} />)}</ul>
        </section>
        {admin && (
          <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Invitationer</h2>
            {invitations.length === 0 ? <p className="p-space-md rounded-xl bg-surface-container-low font-body-sm text-body-sm text-on-surface-variant">Ingen invitationer endnu.</p> : (
              <ul className="flex flex-col gap-2">
                {invitations.map((i) => {
                  const [label, cls] = INV_STATUS[i.status] ?? [i.status, "bg-surface-container-high"];
                  return (
                    <li key={i.id} className="p-3 rounded-xl bg-surface-container-low flex flex-wrap items-center justify-between gap-space-sm">
                      <div className="flex items-center gap-space-sm min-w-0">
                        <div className="w-9 h-9 rounded-full bg-surface-container text-on-surface-variant flex items-center justify-center flex-shrink-0"><Icon name="mail" size={18} /></div>
                        <div className="min-w-0"><p className="font-label-lg text-label-lg text-primary truncate">{i.email}</p><p className="font-body-sm text-body-sm text-on-surface-variant">{ROLE_LABEL[i.role] ?? i.role} · udløber {new Date(i.expires_at).toLocaleDateString("da-DK")}</p></div>
                      </div>
                      <div className="flex items-center gap-space-sm">
                        <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-semibold ${cls}`}>{label}</span>
                        {i.status === "pending" && <InvitationActions wsId={ws.id} id={i.id} />}
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        )}
      </div>
      <div className="xl:col-span-4 xl:sticky xl:top-20 flex flex-col gap-space-lg">
        {admin ? (
          <section className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
            <div className="flex items-center gap-space-sm"><div className="w-9 h-9 rounded-lg bg-primary-container text-secondary-fixed flex items-center justify-center"><Icon name="person_add" size={20} /></div><h2 className="font-headline-sm text-headline-sm text-primary font-bold">Invitér kollega</h2></div>
            <InviteForm wsId={ws.id} myRole={ws.role} />
          </section>
        ) : (
          <section className="bg-surface-container-low rounded-xl p-space-md font-body-sm text-body-sm text-on-surface-variant">Kun ejere og administratorer kan invitere og ændre roller.</section>
        )}
        <section className="bg-surface-container-low rounded-xl p-space-md flex flex-col gap-space-xs">
          <p className="font-label-md text-label-md text-primary font-bold flex items-center gap-1"><Icon name="verified_user" size={18} className="text-secondary" />Roller</p>
          <ul className="font-body-sm text-body-sm text-on-surface-variant space-y-1">
            <li><strong className="text-on-surface">Ejer</strong> – alt, inkl. ejerskab.</li>
            <li><strong className="text-on-surface">Administrator</strong> – team, godkendelse af viden, log.</li>
            <li><strong className="text-on-surface">Medarbejder</strong> – redigerer og indsender kladder.</li>
            <li><strong className="text-on-surface">Læser</strong> – kan se, ikke ændre.</li>
          </ul>
        </section>
      </div>
    </div>
  );
}
