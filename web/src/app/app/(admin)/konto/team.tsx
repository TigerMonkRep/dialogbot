"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";

const RANK: Record<string, number> = { reader: 1, staff: 2, admin: 3, owner: 4 };
/** Customer-facing roles: Ejer = owner, Kan ændre = admin and staff, Kan se = reader. The backend roles are unchanged. */
export const ROLE_LABEL: Record<string, string> = { reader: "Kan se", staff: "Kan ændre", admin: "Kan ændre", owner: "Ejer" };
const BTN = "inline-flex items-center justify-center min-h-[44px] px-3.5 rounded-lg border-[1.5px] border-ink bg-paper text-[13px] font-semibold text-ink hover:bg-panel disabled:opacity-50";

type Member = { id: string; email: string; display_name: string; role: string };

export function MemberRow({ wsId, m, myRole, isMe }: { wsId: string; m: Member; myRole: string; isMe: boolean }) {
  const router = useRouter();
  const canManage = RANK[myRole] >= 3 && (m.role !== "owner" || myRole === "owner") && !isMe;
  const change = useSubmit(async (role: string) => { await api(`/workspaces/${wsId}/members/${m.id}/role`, { method: "PUT", body: JSON.stringify({ role }) }); router.refresh(); });
  const remove = useSubmit(async () => {
    if (!window.confirm(isMe ? "Forlad arbejdsrummet?" : `Fjern ${m.display_name} fra arbejdsrummet?`)) return;
    await api(`/workspaces/${wsId}/members/${m.id}`, { method: "DELETE" }); router.refresh();
  });
  const shown = m.role === "staff" ? "admin" : m.role;
  return (
    <tr className="border-t-[1.5px] border-line align-middle">
      <td className="py-3 pr-3 text-[15px] font-semibold text-ink">{m.display_name}{isMe && <span className="ml-1.5 text-[13px] font-normal text-muted">(dig)</span>}</td>
      <td className="py-3 pr-3 text-[14px] text-ink-soft break-all">{m.email}</td>
      <td className="py-3 pr-3">
        {canManage ? (
          <select aria-label={`Rolle for ${m.display_name}`} className={`${inputCls} min-w-[130px]`} value={shown} onChange={(e) => change.run(e.target.value)}>
            {m.role === "owner" && <option value="owner">Ejer</option>}
            {RANK[myRole] >= 3 && <option value="admin">Kan ændre</option>}
            <option value="reader">Kan se</option>
          </select>
        ) : <span className="inline-flex px-3 py-1.5 rounded-full border-[1.5px] border-ink text-[13px] font-semibold text-ink">{ROLE_LABEL[m.role]}</span>}
        <ErrorBox error={change.error ?? remove.error} />
      </td>
      <td className="py-3 text-right">{(canManage || isMe) && m.role !== "owner" && <button type="button" className={`${BTN} text-danger`} disabled={remove.pending} onClick={() => remove.run()}>{isMe ? "Forlad" : "Fjern"}</button>}</td>
    </tr>
  );
}

export function InvitationRow({ wsId, id, email, role, expires }: { wsId: string; id: string; email: string; role: string; expires: string }) {
  const router = useRouter();
  const act = useSubmit(async (path: "resend" | "revoke") => {
    if (path === "revoke" && !window.confirm("Tilbagekald invitationen? Linket holder op med at virke.")) return;
    await api(`/workspaces/${wsId}/invitations/${id}/${path}`, { method: "POST" }); router.refresh();
  });
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 border-t-[1.5px] border-line">
      <span className="flex-1 min-w-[200px] text-[14px] text-ink">Inviteret – ikke svaret endnu: <b>{email}</b> <span className="text-muted">· {ROLE_LABEL[role] ?? role} · udløber {new Date(expires).toLocaleDateString("da-DK")}</span></span>
      <button type="button" className={BTN} disabled={act.pending} onClick={() => act.run("resend")}>Send igen</button>
      <button type="button" className={`${BTN} text-danger`} disabled={act.pending} onClick={() => act.run("revoke")}>Tilbagekald</button>
      <ErrorBox error={act.error} />
    </li>
  );
}

export function InviteForm({ wsId, myRole }: { wsId: string; myRole: string }) {
  const router = useRouter();
  const [email, setEmail] = useState(""), [role, setRole] = useState("staff"), [ok, setOk] = useState(false);
  const s = useSubmit(async () => {
    await api(`/workspaces/${wsId}/invitations`, { method: "POST", body: JSON.stringify({ email, role }), headers: { "idempotency-key": crypto.randomUUID() } });
    setOk(true); setEmail(""); router.refresh();
  });
  return (
    <form className="flex flex-wrap items-end gap-3 pt-3 border-t-[1.5px] border-line" onSubmit={(e) => { e.preventDefault(); setOk(false); s.run(); }}>
      <div className="flex-[2_1_220px]"><label htmlFor="inv-email" className="block text-[13px] font-semibold mb-1">Invitér med e-mail</label><input id="inv-email" type="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="kollega@firma.dk" /></div>
      <div className="flex-[1_1_140px]"><label htmlFor="inv-role" className="block text-[13px] font-semibold mb-1">Må</label>
        <select id="inv-role" className={inputCls} value={role} onChange={(e) => setRole(e.target.value)}><option value="staff">Kan ændre</option><option value="reader">Kan se</option></select></div>
      <button type="submit" disabled={s.pending} className="inline-flex items-center justify-center min-h-[46px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50">{s.pending ? "Sender…" : "Invitér"}</button>
      <div className="w-full"><ErrorBox error={s.error} />{ok && <p role="status" className="text-[14px] font-semibold text-success">Invitationen er sendt.</p>}</div>
    </form>
  );
}
