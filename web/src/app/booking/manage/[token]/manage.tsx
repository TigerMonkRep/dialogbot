"use client";
import { useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { useT } from "@/i18n/client";
import { Button } from "@/components/ui";
import { Card, CodeStep, CustomerFrame, Note, useCustomerError, useWhen } from "@/components/customer";

export type BookingView = {
  business: string; what: string; first_name: string; starts_at: string; ends_at: string; label: string; timezone: string;
  status: "confirmed" | "cancelled"; confirmation: "confirmed" | "pending";
  policy: { can_change: boolean; reason: "cancelled" | "past" | "too_late" | null; cutoff_hours: number; cutoff_at: string };
  verification: { required: boolean; phone_display: string | null; verified: boolean }; expires_at: string;
};
type Slot = { start: string; end: string };

export function BookingManager({ token, state, initial }: { token: string; state: "ok" | "invalid" | "expired" | "error"; initial: BookingView | null }) {
  const t = useT("widget");
  const when = useWhen();
  const errText = useCustomerError();
  const [v, setV] = useState(initial);
  const [session, setSession] = useState<string | null>(null);
  const [mode, setMode] = useState<"idle" | "move" | "cancel">("idle");
  const [slots, setSlots] = useState<Slot[] | null>(null);
  const [choice, setChoice] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const base = `/public/booking/manage/${encodeURIComponent(token)}`;

  if (state !== "ok" || !v) {
    const title = state === "expired" ? t("customer.expiredTitle") : state === "invalid" ? t("customer.invalidTitle") : t("customer.loadFailed");
    return (
      <CustomerFrame business={null} title={title} icon="link_off">
        <Card><Note tone="error">{state === "expired" ? t("customer.expiredText") : state === "invalid" ? t("customer.invalidText") : t("customer.loadFailed")}</Note></Card>
      </CustomerFrame>
    );
  }
  const tz = v.timezone;
  const fmt = (iso: string) => t("customer.booking.when", { date: when.date(iso, tz), time: when.time(iso, tz) });
  const verified = !v.verification.required || session !== null || v.verification.verified;
  const status = v.status === "cancelled" ? "cancelled" : v.confirmation;

  async function openMove() {
    setMode("move"); setError(null); setDone(null);
    try {
      const r = await api<{ slots: Slot[] }>(`${base}/slots`);
      setSlots(r.slots); setChoice(r.slots[0]?.start ?? "");
    } catch (e) { setError(errText(e as ApiError)); }
  }
  async function act(kind: "move" | "cancel") {
    setPending(true); setError(null);
    try {
      const body = kind === "move" ? { start: choice, session } : { session };
      const nv = await api<BookingView>(`${base}/${kind}`, { method: "POST", body: JSON.stringify(body) });
      setV(nv); setMode("idle");
      setDone(kind === "cancel" ? t("customer.booking.cancelled")
        : nv.confirmation === "pending" ? t("customer.booking.movedPending", { when: fmt(nv.starts_at) }) : t("customer.booking.moved", { when: fmt(nv.starts_at) }));
    } catch (e) {
      const err = e as ApiError;
      setError(errText(err));
      if (err.code === "verification_required") setSession(null);
      if (err.code === "slot_taken") openMove();
    } finally { setPending(false); }
  }

  return (
    <CustomerFrame business={v.business} title={t("customer.booking.title", { business: v.business })} icon="event">
      <Card>
        {v.first_name && <p className="text-body-lg text-ink">{t("customer.greeting", { name: v.first_name })}</p>}
        <dl className="rounded-xl bg-panel p-3 grid grid-cols-1 gap-1 text-body-md">
          <dt className="sr-only">{t("customer.booking.metaTitle")}</dt>
          <dd className="font-display text-headline-sm text-ink">{v.what}</dd>
          <dd className="text-ink" data-testid="booking-when">{fmt(v.starts_at)}</dd>
          <dd><span data-testid="booking-status" className={`inline-flex rounded-full border-[1.5px] px-2.5 py-0.5 text-[12px] font-semibold ${status === "confirmed" ? "bg-success-soft text-success border-success" : status === "pending" ? "bg-highlight text-ink border-highlight" : "bg-panel text-ink border-ink"}`}>{t(`customer.booking.status.${status}`)}</span></dd>
        </dl>
        <p className="text-body-sm text-muted">{t("customer.booking.tz", { tz: when.zone(v.starts_at, tz) })}</p>
        {done && <Note tone="ok">{done}</Note>}
        {!v.policy.can_change && v.policy.reason === "too_late" && <Note>{t("customer.booking.tooLate", { hours: v.policy.cutoff_hours, business: v.business })}</Note>}
        {!v.policy.can_change && v.policy.reason === "past" && <Note>{t("customer.booking.past")}</Note>}
        {!v.policy.can_change && v.policy.reason === "cancelled" && !done && <Note>{t("customer.booking.cancelledNote")}</Note>}
        {error && <Note tone="error">{error}</Note>}
      </Card>
      {v.policy.can_change && !verified && v.verification.phone_display && (
        <CodeStep base={base} phone={v.verification.phone_display} onVerified={(s) => { setSession(s); setError(null); }} />
      )}
      {v.policy.can_change && verified && (
        <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
          {v.verification.required && session && <p className="text-body-sm text-success font-semibold">{t("customer.code.verified")}</p>}
          {mode === "idle" && (
            <>
              <Button icon="event_repeat" onClick={openMove} className="w-full min-h-[52px]">{t("customer.booking.move")}</Button>
              <Button variant="outline" icon="event_busy" onClick={() => { setMode("cancel"); setDone(null); setError(null); }}>{t("customer.booking.cancel")}</Button>
            </>
          )}
          {mode === "move" && slots && (
            slots.length === 0 ? <Note>{t("customer.booking.noSlots")}</Note> : (
              <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); act("move"); }}>
                <label className="flex flex-col gap-1 text-label-lg text-ink">{t("customer.booking.newTime")}
                  <select value={choice} onChange={(e) => setChoice(e.target.value)} className="w-full min-h-[46px] px-3 rounded-xl bg-paper border-2 border-ink text-ink text-[15px]">
                    {slots.map((s) => <option key={s.start} value={s.start}>{fmt(s.start)}</option>)}
                  </select>
                </label>
                <Button type="submit" icon="check_circle" disabled={pending || !choice} className="w-full min-h-[52px]">{t("customer.booking.moveSubmit")}</Button>
              </form>
            )
          )}
          {mode === "cancel" && (
            <div className="flex flex-col gap-2" role="group" aria-label={t("customer.booking.cancel")}>
              <Note>{t("customer.booking.cancelConfirm", { when: fmt(v.starts_at) })}</Note>
              <Button variant="danger" disabled={pending} onClick={() => act("cancel")} className="w-full min-h-[52px]">{t("customer.booking.cancelYes")}</Button>
            </div>
          )}
          {mode !== "idle" && <Button variant="ghost" onClick={() => { setMode("idle"); setError(null); }}>{t("customer.booking.back")}</Button>}
        </section>
      )}
    </CustomerFrame>
  );
}
