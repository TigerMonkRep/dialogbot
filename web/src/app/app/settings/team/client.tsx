"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";

const RANK: Record<string, number> = { reader: 1, staff: 2, admin: 3, owner: 4 };
const LABEL: Record<string, string> = { reader: "Læser", staff: "Medarbejder", admin: "Administrator", owner: "Ejer" };

export function InviteForm({ wsId, myRole }: { wsId: string; myRole: string }) {
  const router = useRouter();
  const [email, setEmail] = useState(""); const [role, setRole] = useState("staff"); const [ok, setOk] = useState(false);
  const { run, pending, error } = useSubmit(async () => { await api(`/workspaces/${wsId}/invitations`, { method: "POST", body: JSON.stringify({ email, role }), headers: { "idempotency-key": crypto.randomUUID() } }); setOk(true); setEmail(""); router.refresh(); });
  return (
    <form onSubmit={(e) => { e.preventDefault(); setOk(false); run(); }} className="space-y-3">
      <ErrorBox error={error} />{ok && <Alert kind="ok">Invitationen er sendt (simuleret mail i udviklingsmiljøet).</Alert>}
      <div className="grid gap-3 sm:grid-cols-[1fr_auto_auto] sm:items-end">
        <Field label="E-mail"><Input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} /></Field>
        <Field label="Rolle"><Select value={role} onChange={(e) => setRole(e.target.value)}>{["reader", "staff", "admin"].filter((r) => RANK[r] <= RANK[myRole]).map((r) => <option key={r} value={r}>{LABEL[r]}</option>)}</Select></Field>
        <Button type="submit" disabled={pending}>Invitér</Button>
      </div>
    </form>
  );
}

export function MemberRow({ wsId, m, myRole, isMe }: { wsId: string; m: { id: string; email: string; display_name: string; role: string }; myRole: string; isMe: boolean }) {
  const router = useRouter();
  const canManage = RANK[myRole] >= 3 && (m.role !== "owner" || myRole === "owner");
  const change = async (role: string) => { try { await api(`/workspaces/${wsId}/members/${m.id}/role`, { method: "PUT", body: JSON.stringify({ role }) }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } };
  const remove = async () => { if (!confirm(`Fjern ${m.display_name} fra arbejdsrummet?`)) return; try { await api(`/workspaces/${wsId}/members/${m.id}`, { method: "DELETE" }); router.refresh(); } catch (e) { alert((e as { message: string }).message); } };
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2">
      <span><strong>{m.display_name}</strong> <span className="text-on-surface-variant">{m.email}</span>{isMe && <span className="ml-1 text-label-sm text-on-surface-variant">(dig)</span>}</span>
      <span className="flex items-center gap-2">
        {canManage ? <Select value={m.role} onChange={(e) => change(e.target.value)}>{Object.keys(RANK).filter((r) => RANK[r] <= RANK[myRole]).map((r) => <option key={r} value={r}>{LABEL[r]}</option>)}</Select> : <span className="text-body-sm">{LABEL[m.role]}</span>}
        {(canManage || isMe) && <Button variant="ghost" className="text-error" onClick={remove}>{isMe ? "Forlad" : "Fjern"}</Button>}
      </span>
    </li>
  );
}
