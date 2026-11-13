"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import type { T } from "@/i18n/translate";

const RANK: Record<string, number> = { reader: 1, staff: 2, admin: 3, owner: 4 };
/** Customer-facing roles: Ejer = owner, Kan ændre = admin and staff, Kan se = reader. The backend roles are unchanged.
 * Choosing «Kan ændre» always gives staff – the same as the invitation (F-EA-04, safer default 13/11: the least
 * privilege; an existing admin is shown as «Kan ændre» and keeps admin until someone changes the role). */
const ROLE_KEY: Record<string, string> = { reader: "reader", staff: "editor", admin: "editor", owner: "owner" };
export const roleLabel = (t: T, role: string) => (ROLE_KEY[role] ? t(`account.role.${ROLE_KEY[role]}`) : role);
const BTN = "inline-flex items-center justify-center min-h-[44px] px-3.5 rounded-lg border-[1.5px] border-ink bg-paper text-[13px] font-semibold text-ink hover:bg-panel disabled:opacity-50";

type Member = { id: string; email: string; display_name: string; role: string };

export function MemberRow({ wsId, m, myRole, isMe }: { wsId: string; m: Member; myRole: string; isMe: boolean }) {
  const router = useRouter();
  const t = useT("app");
  const canManage = RANK[myRole] >= 3 && (m.role !== "owner" || myRole === "owner") && !isMe;
  const change = useSubmit(async (role: string) => { await api(`/workspaces/${wsId}/members/${m.id}/role`, { method: "PUT", body: JSON.stringify({ role }) }); router.refresh(); });
  const remove = useSubmit(async () => {
    if (!window.confirm(isMe ? t("account.team.confirmLeave") : t("account.team.confirmRemove", { name: m.display_name }))) return;
    await api(`/workspaces/${wsId}/members/${m.id}`, { method: "DELETE" }); router.refresh();
  });
  const shown = m.role === "admin" ? "staff" : m.role;
  return (
    <tr className="border-t-[1.5px] border-line align-middle">
      <td className="py-3 pr-3 text-[15px] font-semibold text-ink">{m.display_name}{isMe && <span className="ml-1.5 text-[13px] font-normal text-muted">{t("account.team.you")}</span>}</td>
      <td className="py-3 pr-3 text-[15px] sm:text-[14px] text-ink-soft break-all">{m.email}</td>
      <td className="stack-inline py-3 pr-3 max-sm:!pt-2">
        {canManage ? (
          <select aria-label={t("account.team.roleFor", { name: m.display_name })} className={`${inputCls} sm:min-w-[130px] max-sm:w-auto`} value={shown} onChange={(e) => change.run(e.target.value)}>
            {m.role === "owner" && <option value="owner">{t("account.role.owner")}</option>}
            {RANK[myRole] >= 3 && <option value="staff">{t("account.role.editor")}</option>}
            <option value="reader">{t("account.role.reader")}</option>
          </select>
        ) : <span className="inline-flex px-3 py-1.5 rounded-full border-[1.5px] border-ink text-[13px] font-semibold text-ink">{roleLabel(t, m.role)}</span>}
        <ErrorBox error={change.error ?? remove.error} />
      </td>
      <td className="stack-inline py-3 text-right max-sm:!pt-2">{(canManage || isMe) && m.role !== "owner" && <button type="button" className={`${BTN} text-danger`} disabled={remove.pending} onClick={() => remove.run()}>{isMe ? t("account.team.leave") : t("campaigns.remove")}</button>}</td>
    </tr>
  );
}

export function InvitationRow({ wsId, id, email, role, expires }: { wsId: string; id: string; email: string; role: string; expires: string }) {
  const router = useRouter();
  const t = useT("app");
  const lang = HTML_LANG[useLocale()];
  const act = useSubmit(async (path: "resend" | "revoke") => {
    if (path === "revoke" && !window.confirm(t("account.team.confirmRevoke"))) return;
    await api(`/workspaces/${wsId}/invitations/${id}/${path}`, { method: "POST" }); router.refresh();
  });
  return (
    <li className="flex flex-wrap items-center gap-x-4 gap-y-2 py-3 border-t-[1.5px] border-line">
      <span className="flex-1 min-w-0 basis-full sm:basis-auto sm:min-w-[200px] text-[14px] text-ink">{t("account.team.invited")} <b>{email}</b> <span className="text-muted">· {roleLabel(t, role)} · {t("account.team.expires", { date: new Date(expires).toLocaleDateString(lang) })}</span></span>
      <button type="button" className={BTN} disabled={act.pending} onClick={() => act.run("resend")}>{t("account.team.resend")}</button>
      <button type="button" className={`${BTN} text-danger`} disabled={act.pending} onClick={() => act.run("revoke")}>{t("account.team.revoke")}</button>
      <ErrorBox error={act.error} />
    </li>
  );
}

export function InviteForm({ wsId, myRole }: { wsId: string; myRole: string }) {
  const router = useRouter();
  const t = useT("app");
  const [email, setEmail] = useState(""), [role, setRole] = useState("staff"), [ok, setOk] = useState(false);
  const s = useSubmit(async () => {
    await api(`/workspaces/${wsId}/invitations`, { method: "POST", body: JSON.stringify({ email, role }), headers: { "idempotency-key": crypto.randomUUID() } });
    setOk(true); setEmail(""); router.refresh();
  });
  return (
    <form className="flex flex-wrap items-end gap-3 pt-3 border-t-[1.5px] border-line" onSubmit={(e) => { e.preventDefault(); setOk(false); s.run(); }}>
      <div className="flex-[2_1_220px]"><label htmlFor="inv-email" className="block text-[13px] font-semibold mb-1">{t("account.team.inviteEmail")}</label><input id="inv-email" type="email" required className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder={t("account.team.emailPlaceholder")} /></div>
      <div className="flex-[1_1_140px]"><label htmlFor="inv-role" className="block text-[13px] font-semibold mb-1">{t("account.team.may")}</label>
        <select id="inv-role" className={inputCls} value={role} onChange={(e) => setRole(e.target.value)}><option value="staff">{t("account.role.editor")}</option><option value="reader">{t("account.role.reader")}</option></select></div>
      <button type="submit" disabled={s.pending} className="inline-flex items-center justify-center min-h-[46px] px-5 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50">{s.pending ? t("account.team.sending") : t("account.team.invite")}</button>
      <div className="w-full"><ErrorBox error={s.error} />{ok && <p role="status" className="text-[14px] font-semibold text-success">{t("account.team.sent")}</p>}</div>
    </form>
  );
}
