"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useT } from "@/i18n/client";
import { fieldError, type ApiError } from "@/lib/client";
import { track } from "@/components/site-analytics";
import { Alert, Button, inputCls } from "@/components/ui";
import { Ico } from "@/components/privat/icons";
import type { GateBody } from "@/lib/funnel/api";
import { Question } from "./parts";
import { useFunnel } from "./provider";

type FieldKey = "name" | "phone" | "email" | "consent";
const ORDER: FieldKey[] = ["name", "phone", "email", "consent"];
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/;
const digits = (v: string) => v.replace(/\D/g, "");
/** 8 digits, optionally after +45 / 0045. */
export const validPhone = (v: string) => { const d = digits(v); return d.length === 8 || ((d.length === 10 && d.startsWith("45")) || (d.length === 12 && d.startsWith("0045"))); };

/** The gate: name → mobile → e-mail → consent, one field at a time (the answered ones stay above, tap to change),
 *  then POST /funnel/drafts/{id}/gate sends the SMS code. `website` is the honeypot: hidden from people, filled by bots.
 *  `consent` is the funnel's consent text (what the person says yes to); `title`/`lead` come from the page. */
export function Gate({ title, lead, consent, onCodeSent }: { title: string; lead?: string; consent: string; onCodeSent: () => void }) {
  const t = useT("site.funnel.gate");
  const { api, draft, kind, hook, gate, setGate } = useFunnel();
  const [form, setForm] = useState<{ name: string; phone: string; email: string; consent: boolean; website: string }>(
    () => ({ name: gate?.body.name ?? "", phone: gate?.body.phone ?? "", email: gate?.body.email ?? "", consent: false, website: "" }));
  const [at, setAt] = useState<number>(0);
  const [touched, setTouched] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const current = ORDER[at];
  useEffect(() => { inputRef.current?.focus(); }, [at]);

  const problem = (k: FieldKey): string | null => {
    if (k === "name") return form.name.trim().length >= 2 ? null : t("errName");
    if (k === "phone") return validPhone(form.phone) ? null : t("errPhone");
    if (k === "email") return EMAIL.test(form.email.trim()) ? null : t("errEmail");
    return form.consent ? null : t("errConsent");
  };
  const apiErr = (k: FieldKey) => fieldError(error, k);
  const shown = (k: FieldKey) => (touched[k] ? problem(k) : null) ?? apiErr(k);

  const forward = async () => {
    setTouched((x) => ({ ...x, [current]: true }));
    if (problem(current)) return;
    if (at < ORDER.length - 1) { setAt(at + 1); return; }
    if (!draft) return;
    setBusy(true); setError(null);
    const body: GateBody = { name: form.name.trim(), phone: form.phone.trim(), email: form.email.trim(), consent: true, website: form.website };
    try {
      const r = await api.gate(draft.id, body);
      setGate({ draftId: draft.id, phone_display: r.phone_display, body });
      track("funnel_gate", { kind, step: ORDER.length, hook, industry: draft.answers.industry ?? null });
      onCodeSent();
    } catch (e) {
      const err = e as ApiError;
      setError(err);
      const bad = ORDER.findIndex((k) => fieldError(err, k));
      if (bad >= 0) setAt(bad);
    } finally { setBusy(false); }
  };

  const summary = (k: FieldKey, i: number) => (
    <button key={k} type="button" onClick={() => setAt(i)} className="w-full min-h-[48px] flex items-center gap-3 rounded-xl border-[1.5px] border-ink bg-white px-3.5 text-left cursor-pointer hover:bg-panel" aria-label={t("editAria", { field: t(k) })}>
      <span className="text-[12px] font-semibold uppercase tracking-[0.08em] text-muted w-[72px] shrink-0">{t(k)}</span>
      <span className="font-semibold text-[15px] text-ink truncate flex-1">{form[k as "name" | "phone" | "email"]}</span>
      <span className="text-[13px] text-accent font-semibold">{t("edit")}</span>
    </button>
  );

  return (
    <form onSubmit={(e) => { e.preventDefault(); void forward(); }} className="flex flex-col gap-5" data-gate={current} noValidate>
      <Question title={title} help={lead} />
      {error && !ORDER.some((k) => fieldError(error, k)) && <Alert>{error.message}</Alert>}
      {at > 0 && <div className="flex flex-col gap-2">{ORDER.slice(0, at).filter((k) => k !== "consent").map((k) => summary(k, ORDER.indexOf(k)))}</div>}

      {/* Honeypot: people never see it; a bot that fills it gets the same answer and no SMS. */}
      <div aria-hidden="true" className="absolute -left-[9999px] top-0 w-px h-px overflow-hidden">
        <label>Website<input type="text" name="website" tabIndex={-1} autoComplete="off" value={form.website} onChange={(e) => setForm({ ...form, website: e.target.value })} /></label>
      </div>

      {current !== "consent" ? (
        <label className="flex flex-col gap-1.5">
          <span className="text-[13px] font-semibold text-ink">{t(current)}</span>
          <input ref={inputRef} key={current} className={`${inputCls} min-h-[52px] text-[17px]`} enterKeyHint="next"
            type={current === "email" ? "email" : current === "phone" ? "tel" : "text"}
            inputMode={current === "phone" ? "tel" : current === "email" ? "email" : "text"}
            autoComplete={current === "name" ? "name" : current === "phone" ? "tel" : "email"}
            name={current} value={form[current]} placeholder={t(`${current}Ph`)} aria-invalid={!!shown(current)} aria-describedby={`gate-${current}-hint`}
            onChange={(e) => setForm({ ...form, [current]: e.target.value })} />
          <span id={`gate-${current}-hint`} className={`text-[13px] ${shown(current) ? "text-danger font-semibold" : "text-muted"}`} role={shown(current) ? "alert" : undefined}>{shown(current) ?? t(`${current}Hint`)}</span>
        </label>
      ) : (
        <label className="flex items-start gap-3 rounded-2xl border-2 border-ink bg-white p-4 cursor-pointer">
          <input ref={inputRef} type="checkbox" name="consent" checked={form.consent} onChange={(e) => setForm({ ...form, consent: e.target.checked })}
            className="mt-1 w-5 h-5 shrink-0 accent-[var(--color-accent)]" aria-describedby="gate-consent-hint" />
          <span className="flex flex-col gap-1.5">
            <span className="text-[15px] leading-normal text-ink">{consent}</span>
            <span className="text-[13px] text-muted">{t("consentPrivacyBefore")}<Link href="/privatliv" className="underline text-ink">{t("consentPrivacyLink")}</Link>{t("consentPrivacyAfter")}</span>
            {shown("consent") && <span id="gate-consent-hint" role="alert" className="text-[13px] text-danger font-semibold">{shown("consent")}</span>}
          </span>
        </label>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        <Button type="submit" disabled={busy} className="min-h-[52px] w-full sm:w-auto sm:min-w-[200px] text-[16px] rounded-2xl" data-next>
          {busy ? t("sending") : current === "consent" ? t("send") : t("next")}{!busy && <Ico name="arrow" size={18} stroke={2.8} />}
        </Button>
        {at > 0 && <button type="button" onClick={() => setAt(at - 1)} className="min-h-11 text-[14px] font-semibold text-ink underline underline-offset-2 bg-transparent border-0 cursor-pointer">{t("back")}</button>}
      </div>
    </form>
  );
}

/** The 6-digit SMS code. Auto-submits at six digits; «Send igen» opens after 30 s and repeats the gate call with the
 *  same data. On success the person is logged in (cookie set by the BFF route) and the page follows `next` with a full
 *  load, so the server sees the new session. */
export function CodeStep({ title, lead, gateStep, onBack }: { title: string; lead?: string; gateStep: number; onBack?: () => void }) {
  const t = useT("site.funnel.code");
  const { api, draft, kind, hook, gate, setGate, go } = useFunnel();
  const toGate = onBack ?? (() => go(gateStep));
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [left, setLeft] = useState(30);
  const [resent, setResent] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const sent = useRef<string | null>(null);

  useEffect(() => { inputRef.current?.focus(); }, []);
  useEffect(() => {
    if (left <= 0) return;
    const h = window.setTimeout(() => setLeft((s) => s - 1), 1000);
    return () => window.clearTimeout(h);
  }, [left]);

  const submit = async (value: string) => {
    if (!draft || busy || value.length !== 6 || sent.current === value) return;
    sent.current = value;
    setBusy(true); setError(null);
    try {
      const r = await api.verify(draft.id, value);
      track("funnel_verified", { kind, step: gateStep + 1, hook, industry: draft.answers.industry ?? null });
      window.location.assign(r.next);
    } catch (e) {
      setError(e as ApiError); setBusy(false); sent.current = null;
      setCode(""); inputRef.current?.focus();
    }
  };
  const onChange = (v: string) => {
    const d = v.replace(/\D/g, "").slice(0, 6);
    setCode(d);
    if (d.length === 6) void submit(d);
  };
  const resend = async () => {
    if (!draft || !gate || left > 0) return;
    setError(null);
    try {
      const r = await api.gate(draft.id, gate.body);
      setGate({ ...gate, phone_display: r.phone_display });
      setResent(true); setLeft(30); sent.current = null;
    } catch (e) { setError(e as ApiError); }
  };

  if (!gate) {
    return (
      <div className="flex flex-col gap-4">
        <Question title={title} />
        <Alert kind="info">{t("noGate")}</Alert>
        <Button variant="outline" onClick={toGate} className="self-start">{t("toGate")}</Button>
      </div>
    );
  }
  return (
    <form onSubmit={(e) => { e.preventDefault(); void submit(code); }} className="flex flex-col gap-5" data-code>
      <Question title={title} help={lead ?? t("lead", { phone: gate.phone_display })} />
      <label className="flex flex-col gap-1.5">
        <span className="text-[13px] font-semibold text-ink">{t("label")}</span>
        <input ref={inputRef} type="text" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]*" maxLength={6} value={code} onChange={(e) => onChange(e.target.value)}
          aria-invalid={!!error} aria-describedby="code-hint" disabled={busy} name="code"
          className={`${inputCls} min-h-[60px] text-center font-display font-extrabold text-[30px] tracking-[0.4em] pl-[0.4em]`} />
        <span id="code-hint" role={error ? "alert" : "status"} className={`text-[13px] ${error ? "text-danger font-semibold" : "text-muted"}`}>
          {error ? (fieldError(error, "code") ?? error.message) : busy ? t("verifying") : resent ? t("resent") : t("hint")}
        </span>
      </label>
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <button type="button" onClick={resend} disabled={left > 0} className="min-h-11 text-[14px] font-semibold text-ink underline underline-offset-2 bg-transparent border-0 cursor-pointer disabled:no-underline disabled:text-muted disabled:cursor-default" data-resend>
          {left > 0 ? t("resendIn", { s: left }) : t("resend")}
        </button>
        <button type="button" onClick={toGate} className="min-h-11 text-[14px] font-semibold text-ink underline underline-offset-2 bg-transparent border-0 cursor-pointer">{t("wrongNumber")}</button>
      </div>
    </form>
  );
}
