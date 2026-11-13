"use client";
import { useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { useT } from "@/i18n/client";
import { Button } from "@/components/ui";
import { Card, CustomerFrame, Note, useCustomerError, useWhen } from "@/components/customer";

export type CallbackView = {
  business: string; first_name: string; status: "requested" | "cancelled" | "done"; phone_display: string | null;
  phone_verified: boolean; window: { from: string; to: string } | null; timezone: string; calls_opt_out: boolean;
  can_opt_out: boolean; expires_at: string;
};

export function CallbackManager({ token, state, initial }: { token: string; state: "ok" | "invalid" | "expired" | "error"; initial: CallbackView | null }) {
  const t = useT("widget");
  const when = useWhen();
  const errText = useCustomerError();
  const [v, setV] = useState(initial);
  const [confirm, setConfirm] = useState(false);
  const [optOut, setOptOut] = useState(initial?.calls_opt_out ?? false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const base = `/public/customer/callback/${encodeURIComponent(token)}`;

  if (state !== "ok" || !v) {
    const title = state === "expired" ? t("customer.expiredTitle") : state === "invalid" ? t("customer.invalidTitle") : t("customer.loadFailed");
    return (
      <CustomerFrame business={null} title={title} icon="link_off">
        <Card><Note tone="error">{state === "expired" ? t("customer.expiredText") : state === "invalid" ? t("customer.invalidText") : t("customer.loadFailed")}</Note></Card>
      </CustomerFrame>
    );
  }
  async function call(path: string, init: RequestInit, after?: () => void) {
    setPending(true); setError(null); setSaved(false);
    try { const nv = await api<CallbackView>(path, init); setV(nv); setOptOut(nv.calls_opt_out); after?.(); }
    catch (e) { setError(errText(e as ApiError)); }
    finally { setPending(false); setConfirm(false); }
  }
  const tz = v.timezone;
  return (
    <CustomerFrame business={v.business} title={t("customer.callback.title", { business: v.business })} icon="phone_callback">
      <Card>
        {v.first_name && <p className="text-body-lg text-ink">{t("customer.greeting", { name: v.first_name })}</p>}
        {v.status === "requested" && (
          <>
            <p className="text-body-md text-ink">{v.phone_display ? t("customer.callback.requested", { business: v.business, phone: v.phone_display }) : t("customer.callback.requestedNoPhone", { business: v.business })}</p>
            {v.phone_verified && <p className="text-body-sm text-success font-semibold">{t("customer.callback.verified")}</p>}
            <p className="text-body-md text-ink-soft">{v.window
              ? t("customer.callback.window", { from: `${when.date(v.window.from, tz)} ${when.time(v.window.from, tz)}`, to: when.time(v.window.to, tz), tz: when.zone(v.window.from, tz) })
              : t("customer.callback.noWindow")}</p>
            {error && <Note tone="error">{error}</Note>}
            {!confirm ? (
              <Button variant="danger" icon="phone_disabled" onClick={() => setConfirm(true)} className="w-full min-h-[52px]">{t("customer.callback.cancel")}</Button>
            ) : (
              <div className="flex flex-col gap-2" role="group" aria-label={t("customer.callback.cancel")}>
                <Note>{t("customer.callback.cancelConfirm")}</Note>
                <Button variant="danger" disabled={pending} onClick={() => call(`${base}/cancel`, { method: "POST" })} className="w-full min-h-[52px]">{t("customer.callback.cancelYes")}</Button>
                <Button variant="outline" onClick={() => setConfirm(false)}>{t("customer.callback.cancelNo")}</Button>
              </div>
            )}
          </>
        )}
        {v.status === "cancelled" && <Note tone="ok">{t("customer.callback.cancelled")}</Note>}
        {v.status === "done" && <Note>{t("customer.callback.done")}</Note>}
      </Card>
      <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 flex flex-col gap-3" aria-labelledby="prefs">
        <h2 id="prefs" className="font-display text-headline-sm text-ink">{t("customer.callback.prefsTitle")}</h2>
        {v.can_opt_out ? (
          <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); call(`${base}/preferences`, { method: "PUT", body: JSON.stringify({ calls_opt_out: optOut }) }, () => setSaved(true)); }}>
            <label className="flex items-start gap-2 text-body-md text-ink">
              <input type="checkbox" className="mt-1 w-5 h-5 accent-[var(--color-accent)]" checked={optOut} onChange={(e) => { setOptOut(e.target.checked); setSaved(false); }} />
              <span>{t("customer.callback.optOut", { business: v.business })}</span>
            </label>
            <p className="text-body-sm text-muted">{t("customer.callback.optOutHint")}</p>
            {saved && <Note tone="ok">{t("customer.callback.saved")}</Note>}
            <Button type="submit" variant="outline" icon="save" disabled={pending}>{t("customer.callback.save")}</Button>
          </form>
        ) : <p className="text-body-md text-ink-soft">{t("customer.callback.noPhone")}</p>}
      </section>
    </CustomerFrame>
  );
}
