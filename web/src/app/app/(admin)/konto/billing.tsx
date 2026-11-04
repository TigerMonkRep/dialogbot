"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { ErrorBox, inputCls, useSubmit } from "@/components/ui";
import { useT } from "@/i18n/client";

const BTN = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-[1.5px] border-ink bg-paper text-[14px] font-semibold text-ink hover:bg-panel disabled:opacity-50";
const BTN_PRIMARY = "inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep disabled:opacity-50";

/** Owner confirms the subscription (one offer). Each confirmation is a new version of the agreement. */
export function ConfirmSubscription({ wsId, label }: { wsId: string; label: string }) {
  const router = useRouter();
  const c = useSubmit(async () => { await api(`/workspaces/${wsId}/agreement`, { method: "POST", body: JSON.stringify({ model: "A" }) }); router.refresh(); });
  return <div className="flex flex-col gap-1"><button type="button" className={BTN_PRIMARY + " self-start"} disabled={c.pending} onClick={() => c.run()}>{label}</button><ErrorBox error={c.error} /></div>;
}

/** Opens Stripe Checkout (setup mode) where the owner saves a card. Nothing is charged there. */
export function AddCard({ wsId, hasCard }: { wsId: string; hasCard: boolean }) {
  const t = useT("app");
  const go = useSubmit(async () => {
    const r = await api<{ url: string }>(`/workspaces/${wsId}/billing/card/checkout`, { method: "POST", body: "{}" });
    window.location.assign(r.url);
  });
  return <div className="flex flex-col gap-1"><button type="button" className={hasCard ? BTN : BTN_PRIMARY + " self-start"} onClick={() => go.run()} disabled={go.pending}>{go.pending ? t("account.card.opening") : hasCard ? t("account.card.change") : t("account.card.add")}</button><ErrorBox error={go.error} /></div>;
}

export function InvoiceMonth({ wsId, month, label }: { wsId: string; month: string; label: string }) {
  const router = useRouter();
  const t = useT("app");
  const run = useSubmit(async () => { await api(`/workspaces/${wsId}/billing/invoices`, { method: "POST", body: JSON.stringify({ month }) }); router.refresh(); });
  return <div className="flex flex-col gap-1"><button type="button" className={BTN + " self-start"} onClick={() => run.run()} disabled={run.pending}>{run.pending ? t("account.invoiceNow.pending") : t("account.invoiceNow.button", { month: label })}</button><ErrorBox error={run.error} /></div>;
}

/** A customer who was recommended but did not use the link can type the ambassador's code (first 30 days). One place only. */
export function ReferralCode({ wsId }: { wsId: string }) {
  const router = useRouter();
  const t = useT("app");
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const s = useSubmit(async () => { await api(`/workspaces/${wsId}/referral`, { method: "PUT", body: JSON.stringify({ code }) }); router.refresh(); });
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="self-start min-h-[44px] text-[14px] font-semibold text-accent hover:underline">{t("account.referral.ask")}</button>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); s.run(); }} className="flex flex-wrap items-end gap-3 rounded-xl border-[1.5px] border-dashed border-ink p-4">
      <div className="flex-1 min-w-[180px]"><label htmlFor="ref-code" className="block text-[13px] font-semibold mb-1">{t("account.referral.label")}</label><input id="ref-code" required className={inputCls} value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("account.referral.placeholder")} />
        <p className="text-[13px] text-muted mt-1">{t("account.referral.hint")}</p>
        {fieldError(s.error, "code") && <p role="alert" className="text-[13px] text-danger">{fieldError(s.error, "code")}</p>}</div>
      <button type="submit" className={BTN_PRIMARY} disabled={s.pending}>{s.pending ? t("common.saving") : t("account.referral.add")}</button>
      <ErrorBox error={s.error} />
    </form>
  );
}

/** An operator's discount code (made under Admin → Rabatkoder). One per workspace; it counts from this month's statement. */
export function DiscountCode({ wsId }: { wsId: string }) {
  const router = useRouter();
  const t = useT("app");
  const [open, setOpen] = useState(false);
  const [code, setCode] = useState("");
  const s = useSubmit(async () => { await api(`/workspaces/${wsId}/billing/discount`, { method: "PUT", body: JSON.stringify({ code }) }); router.refresh(); });
  if (!open) return <button type="button" onClick={() => setOpen(true)} className="self-start min-h-[44px] text-[14px] font-semibold text-accent hover:underline">{t("account.discount.ask")}</button>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); s.run(); }} className="flex flex-wrap items-end gap-3 rounded-xl border-[1.5px] border-dashed border-ink p-4">
      <div className="flex-1 min-w-[180px]"><label htmlFor="discount-code" className="block text-[13px] font-semibold mb-1">{t("account.discount.label")}</label><input id="discount-code" required className={`${inputCls} uppercase`} value={code} onChange={(e) => setCode(e.target.value)} placeholder={t("account.discount.placeholder")} autoCapitalize="characters" />
        <p className="text-[13px] text-muted mt-1">{t("account.discount.hint")}</p>
        {fieldError(s.error, "code") && <p role="alert" className="text-[13px] text-danger">{fieldError(s.error, "code")}</p>}</div>
      <button type="submit" className={BTN_PRIMARY} disabled={s.pending}>{s.pending ? t("common.saving") : t("account.discount.add")}</button>
      {!fieldError(s.error, "code") && <ErrorBox error={s.error} />}
    </form>
  );
}
