"use client";
import { useEffect, useState } from "react";
import { Button, ErrorBox } from "@/components/ui";
import { useT } from "@/i18n/client";
import type { ApiError } from "@/lib/client";
import { household, householdInvite, householdLeave, householdRemove, type Household } from "@/lib/privat/account-api";
import { bareLink, platformOf, smsHref } from "@/lib/privat/sms";
import { Avatars, LINK, Pill } from "./bits";
import { usePlan, usePrivat } from "./store";

/** Konto → «Husstand» (Familie only): who is in it, one way to invite (an SMS from the owner's own phone), remove /
 *  leave. Shows first names only – a household shares the plan, never anybody's things. */
export function HouseholdCard() {
  const t = useT("privat");
  const { mode, refresh } = usePrivat();
  const p = usePlan();
  const [h, setH] = useState<Household | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const load = () => household().then(setH).catch(() => setH(null));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (mode === "real") void load(); }, [mode, p.plan]);
  if (mode !== "real" || !h || (!h.role && p.plan !== "familie")) return null;
  const act = async (fn: () => Promise<unknown>, done?: string) => {
    setBusy(true); setError(null);
    try { await fn(); if (done) setNote(done); await load(); await refresh(); }
    catch (e) { setError(e as ApiError); }
    finally { setBusy(false); }
  };
  const invite = () => act(async () => {
    const inv = await householdInvite();
    window.location.href = smsHref(t("familyHousehold.smsText", { link: bareLink(inv.short_url) }), [], platformOf(navigator.userAgent));
  });
  const names = h.role === "member" ? [h.owner_first_name ?? "", ...h.members.map((m) => m.name)] : [t("familyHousehold.me"), ...h.members.map((m) => m.name)];
  return (
    <section className="rounded-[18px] border-2 border-ink bg-paper p-4 flex flex-col gap-2.5" aria-labelledby="household-h" data-testid="household-card">
      <div className="flex items-center gap-3 flex-wrap">
        <h3 id="household-h" className="m-0 flex-1 font-display font-bold text-[19px]">{t("familyHousehold.title")}</h3>
        <Pill tone={h.active ? "plain" : "soon"}>{t("familyHousehold.count", { count: h.count, limit: h.limit })}</Pill>
      </div>
      <Avatars names={names.filter(Boolean)} />
      {h.role === "member"
        ? <p className="m-0 text-[15px]">{t("familyHousehold.memberLine", { name: h.owner_first_name ?? "" })}</p>
        : <p className="m-0 text-[14px] text-ink-soft">{t("familyHousehold.ownerText", { limit: h.limit })}</p>}
      {!h.active && <p className="m-0 text-[14px] font-semibold">{t("familyHousehold.paused")}</p>}
      {h.role === "owner" && h.members.length > 0 && (
        <ul className="m-0 p-0 list-none flex flex-col" data-testid="household-members">
          {h.members.map((m) => (
            <li key={m.id} className="flex items-center gap-2 border-b-[1.5px] border-line py-1.5 text-[15px]">
              <span className="flex-1 min-w-0 [overflow-wrap:anywhere]">{m.name}</span>
              <button type="button" className={LINK} disabled={busy}
                onClick={() => { if (window.confirm(t("familyHousehold.removeConfirm", { name: m.name }))) void act(() => householdRemove(m.id)); }}>{t("familyHousehold.remove")}</button>
            </li>
          ))}
        </ul>
      )}
      {h.role === "owner" && h.can_invite && <Button className="self-start rounded-full border-2 border-ink" icon="send" onClick={invite} disabled={busy}>{t("familyHousehold.invite")}</Button>}
      {h.role === "owner" && h.active && !h.can_invite && <p className="m-0 text-[14px] text-muted">{t("familyHousehold.full")}</p>}
      {h.role === "member" && (
        <button type="button" className={LINK} disabled={busy}
          onClick={() => { if (window.confirm(t("familyHousehold.leaveConfirm"))) void act(householdLeave, t("familyHousehold.left")); }}>{t("familyHousehold.leave")}</button>
      )}
      {note && <p role="status" className="m-0 text-[14px] font-semibold text-success">{note}</p>}
      <ErrorBox error={error} />
    </section>
  );
}
