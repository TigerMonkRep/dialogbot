"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";

const RANK: Record<string, number> = { reader: 1, staff: 2, admin: 3, owner: 4 };
export const ROLE_LABEL: Record<string, string> = { reader: "Læser", staff: "Medarbejder", admin: "Administrator", owner: "Ejer" };

export function InviteForm({ wsId, myRole }: { wsId: string; myRole: string }) {
  const router = useRouter();
  const [email, setEmail] = useState(""); const [role, setRole] = useState("staff"); const [ok, setOk] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api(`/workspaces/${wsId}/invitations`, { method: "POST", body: JSON.stringify({ email, role }), headers: { "idempotency-key": crypto.randomUUID() } }); setOk(true); setEmail(""); router.refresh(); });
  return (
    <form onSubmit={(e) => { e.preventDefault(); setOk(false); run(); }} className="space-y-space-md">
      <ErrorBox error={error} />{ok && <Alert kind="ok">Invitationen er oprettet og lagt i udsendelseskøen.</Alert>}
      <Field label="E-mail"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="kollega@firma.dk" /></Field>
      <Field label="Rolle"><Select value={role} onChange={(e) => setRole(e.target.value)}>{["reader", "staff", "admin"].filter((r) => RANK[r] <= RANK[myRole]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</Select></Field>
      <Button type="submit" icon="send" disabled={pending} className="w-full">{pending ? "Sender…" : "Send invitation"}</Button>
    </form>
  );
}

export function InvitationActions({ wsId, id }: { wsId: string; id: string }) {
  const router = useRouter();
  const act = async (path: "resend" | "revoke") => {
    if (path === "revoke" && !confirm("Tilbagekald invitationen? Linket holder op med at virke.")) return;
    try { await api(`/workspaces/${wsId}/invitations/${id}/${path}`, { method: "POST" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); }
  };
  return (
    <span className="flex items-center gap-1">
      <button onClick={() => act("resend")} className="px-2.5 py-1 rounded-lg font-label-sm text-label-sm text-primary font-semibold hover:bg-surface-container">Send igen</button>
      <button onClick={() => act("revoke")} className="px-2.5 py-1 rounded-lg font-label-sm text-label-sm text-error font-semibold hover:bg-error-container/40">Tilbagekald</button>
    </span>
  );
}

export function MemberRow({ wsId, m, myRole, isMe }: { wsId: string; m: { id: string; email: string; display_name: string; role: string }; myRole: string; isMe: boolean }) {
  const router = useRouter();
  const canManage = RANK[myRole] >= 3 && (m.role !== "owner" || myRole === "owner") && !isMe;
  const change = async (role: string) => { try { await api(`/workspaces/${wsId}/members/${m.id}/role`, { method: "PUT", body: JSON.stringify({ role }) }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } };
  const remove = async () => { if (!confirm(isMe ? "Forlad arbejdsrummet?" : `Fjern ${m.display_name} fra arbejdsrummet?`)) return; try { await api(`/workspaces/${wsId}/members/${m.id}`, { method: "DELETE" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } };
  const initials = m.display_name.split(/\s+/).map((s) => s[0]).join("").slice(0, 2).toUpperCase();
  return (
    <li className="p-3 rounded-xl bg-surface-container-low flex flex-wrap items-center justify-between gap-space-sm">
      <div className="flex items-center gap-space-sm min-w-0">
        <div className="w-9 h-9 rounded-full bg-primary text-on-primary font-label-md text-label-md font-bold flex items-center justify-center flex-shrink-0">{initials}</div>
        <div className="min-w-0"><p className="font-label-lg text-label-lg text-primary truncate">{m.display_name}{isMe && <span className="ml-1 font-label-sm text-label-sm text-on-surface-variant">(dig)</span>}</p><p className="font-body-sm text-body-sm text-on-surface-variant truncate">{m.email}</p></div>
      </div>
      <div className="flex items-center gap-space-sm">
        {canManage
          ? <select aria-label={`Rolle for ${m.display_name}`} className="px-2 py-1.5 rounded-lg bg-surface-container-lowest font-label-md text-label-md shadow-sm focus:outline-none focus:ring-2 focus:ring-primary" value={m.role} onChange={(e) => change(e.target.value)}>{Object.keys(RANK).filter((r) => RANK[r] <= RANK[myRole]).map((r) => <option key={r} value={r}>{ROLE_LABEL[r]}</option>)}</select>
          : <span className="px-2 py-0.5 rounded-full bg-surface-container-high text-primary font-label-sm text-label-sm font-semibold">{ROLE_LABEL[m.role]}</span>}
        {(canManage || isMe) && <button onClick={remove} aria-label={isMe ? "Forlad arbejdsrummet" : `Fjern ${m.display_name}`} className="w-8 h-8 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-error hover:bg-error-container/40"><Icon name={isMe ? "logout" : "person_remove"} size={18} /></button>}
      </div>
    </li>
  );
}
