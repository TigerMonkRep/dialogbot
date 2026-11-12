"use client";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
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

/** Opens Stripe Checkout (setup mode) where the owner saves a card. Nothing is charged there. An EU company outside
 *  Denmark must give its VAT number first: the backend answers 409 `vat_number_required`, and `onVatRequired` moves
 *  the owner to the VAT number field. */
export function AddCard({ wsId, hasCard, onVatRequired, returnTo }: { wsId: string; hasCard: boolean; onVatRequired?: () => void; returnTo?: "opsaetning" }) {
  const t = useT("app");
  const go = useSubmit(async () => {
    try {
      // returnTo: Stripe sends the owner back to the guide's payment step instead of Konto
      const r = await api<{ url: string }>(`/workspaces/${wsId}/billing/card/checkout`, { method: "POST", body: JSON.stringify(returnTo ? { return_to: returnTo } : {}) });
      window.location.assign(r.url);
    } catch (e) {
      const err = e as ApiError;
      if (err?.status === 409 && err.code === VAT_REQUIRED && onVatRequired) { onVatRequired(); return; }
      throw e;
    }
  });
  return <div className="flex flex-col gap-1"><button type="button" className={hasCard ? BTN : BTN_PRIMARY + " self-start"} onClick={() => go.run()} disabled={go.pending}>{go.pending ? t("account.card.opening") : hasCard ? t("account.card.change") : t("account.card.add")}</button><ErrorBox error={go.error} /></div>;
}

const VAT_REQUIRED = "vat_number_required";

/** The card plus – for a company outside Denmark – its VAT number (PUT …/billing/vat-number). Shown when the account's
 *  country is an EU country other than DK (required: invoiced without VAT, reverse charge) or Norway (optional), and
 *  always after the backend refused a card with 409 `vat_number_required`. */
export function CardAndVat({ wsId, hasCard, canManage, vatNumber, vatMode, returnTo }: {
  wsId: string; hasCard: boolean; canManage: boolean; vatNumber: string | null; vatMode: "required" | "optional" | null; returnTo?: "opsaetning";
}) {
  const t = useT("app");
  const router = useRouter();
  const [value, setValue] = useState(vatNumber ?? "");
  const [forced, setForced] = useState(false);
  const [saved, setSaved] = useState(false);
  const ref = useRef<HTMLInputElement>(null);
  const save = useSubmit(async () => {
    await api(`/workspaces/${wsId}/billing/vat-number`, { method: "PUT", body: JSON.stringify({ vat_number: value.trim() }) });
    setSaved(true); setForced(false); router.refresh();
  });
  useEffect(() => { if (forced) { ref.current?.focus(); ref.current?.scrollIntoView({ block: "center" }); } }, [forced]);
  const show = vatMode !== null || forced;
  const required = vatMode === "required" || forced;
  const fieldErr = fieldError(save.error, "vat_number");
  const hintId = "vat-number-hint";
  return (
    <div className="flex flex-col gap-3">
      {show && (
        <form onSubmit={(e) => { e.preventDefault(); setSaved(false); save.run(); }} className={`flex flex-wrap items-end gap-3 rounded-xl border-[1.5px] p-4 ${forced ? "border-danger bg-danger-soft" : "border-dashed border-ink"}`} data-testid="vat-number">
          <div className="flex-1 min-w-[200px]">
            <label htmlFor="vat-number" className="block text-[13px] font-semibold mb-1">{t("account.vat.label")}{!required && <span className="font-normal text-muted"> · {t("account.vat.optional")}</span>}</label>
            <input id="vat-number" ref={ref} className={`${inputCls} uppercase`} value={value} onChange={(e) => setValue(e.target.value)} placeholder={t("account.vat.placeholder")}
              autoCapitalize="characters" spellCheck={false} autoComplete="off" required={required} disabled={!canManage}
              aria-invalid={forced || !!fieldErr || undefined} aria-describedby={hintId} />
            <p id={hintId} role={forced || fieldErr ? "alert" : undefined} className={`text-[13px] mt-1 ${forced || fieldErr ? "text-danger font-semibold" : "text-muted"}`}>
              {fieldErr ?? (forced ? t("account.vat.required") : required ? t("account.vat.hint") : t("account.vat.hintOptional"))}
            </p>
            {saved && !save.error && <p role="status" className="text-[13px] text-success font-semibold mt-1">{t("account.vat.saved")}</p>}
          </div>
          {canManage && <button type="submit" className={BTN} disabled={save.pending || !value.trim()}>{save.pending ? t("common.saving") : t("account.vat.save")}</button>}
          {!fieldErr && <ErrorBox error={save.error} />}
        </form>
      )}
      {canManage ? <AddCard wsId={wsId} hasCard={hasCard} onVatRequired={() => setForced(true)} returnTo={returnTo} /> : null}
    </div>
  );
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
