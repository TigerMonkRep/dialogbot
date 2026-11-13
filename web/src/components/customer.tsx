"use client";
/* The business's own customers on their secure links (W09 /kunde/[token], W13 /booking/manage/[token]). No login, no
 * Dialogbot menu: the business's name leads, the page says who shows it. Texts in `widget.customer`, 8 languages. */
import { useEffect, useRef, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import { Button, Icon, LogoMark } from "./ui";
import { LanguageSwitcher } from "./language-switcher";

export function CustomerFrame({ business, title, icon, children }: { business: string | null; title: string; icon: string; children: React.ReactNode }) {
  const t = useT("widget");
  return (
    <div className="min-h-dvh bg-panel text-ink app-type flex flex-col">
      <header className="bg-paper border-b-2 border-ink">
        <div className="max-w-[720px] mx-auto min-h-16 px-4 flex items-center justify-between gap-3">
          <span className="font-display font-extrabold text-[20px] tracking-[-0.3px] text-ink truncate">{business ?? ""}</span>
          <div className="flex items-center gap-2 flex-shrink-0">
            <LanguageSwitcher compact />
            <span className="hidden sm:inline-flex items-center gap-1 px-2.5 py-1 rounded-full border-[1.5px] border-ink bg-paper text-[12px] font-semibold">
              <Icon name="lock" size={16} className="text-accent" />{t("customer.secure")}
            </span>
          </div>
        </div>
      </header>
      <main id="main" className="flex-1 flex justify-center px-4 py-6 md:py-10">
        <div className="w-full max-w-md flex flex-col gap-4">
          <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 flex flex-col gap-3">
            <span className="w-11 h-11 rounded-xl bg-accent flex items-center justify-center text-white"><Icon name={icon} size={22} /></span>
            <h1 className="font-display text-headline-lg-mobile md:text-[34px] md:leading-[1.05] md:tracking-[-0.8px] text-ink">{title}</h1>
          </section>
          {children}
          {business && (
            <p className="flex items-center gap-2 text-body-sm text-muted"><LogoMark size={18} />{t("customer.onBehalf", { business })}</p>
          )}
        </div>
      </main>
    </div>
  );
}

/** A Danish backend message is never shown: every known code has its own text in the visitor's language. */
export function useCustomerError() {
  const t = useT("widget");
  return (e: ApiError | null | undefined): string | null => {
    if (!e) return null;
    const code = (e as ApiError & { code?: string }).code ?? "";
    if (code === "code_invalid") {
      const left = Number((e as unknown as { attempts_left?: number }).attempts_left ?? 0);
      return left > 0 ? t("customer.errors.code_invalid", { n: left }) : t("customer.errors.code_invalid_last");
    }
    const known = ["link_invalid", "link_expired", "verification_required", "change_too_late", "booking_cancelled", "slot_taken",
      "too_soon", "sms_rate_limited", "sms_failed", "code_expired", "too_many_attempts"];
    return t(`customer.errors.${known.includes(code) ? code : "generic"}`);
  };
}

export function Note({ tone = "info", children }: { tone?: "info" | "ok" | "error"; children: React.ReactNode }) {
  const cls = { info: "bg-panel text-ink border-ink", ok: "bg-success-soft text-success border-success", error: "bg-danger-soft text-danger border-danger" }[tone];
  return <p role={tone === "error" ? "alert" : "status"} className={`rounded-xl border-[1.5px] px-3 py-2 text-body-md ${cls}`}>{children}</p>;
}

export function Card({ children }: { children: React.ReactNode }) {
  return <section className="bg-paper rounded-2xl border-2 border-ink p-5 md:p-6 shadow-block flex flex-col gap-3">{children}</section>;
}

/** Date/time in the business's time zone, in the visitor's language; plus the zone's long name ("centraleuropæisk normaltid"). */
export function useWhen() {
  const lang = HTML_LANG[useLocale()];
  return {
    date: (iso: string, tz: string) => new Date(iso).toLocaleDateString(lang, { weekday: "long", day: "numeric", month: "long", timeZone: tz }),
    time: (iso: string, tz: string) => new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", timeZone: tz }),
    zone: (iso: string, tz: string) =>
      new Intl.DateTimeFormat(lang, { timeZone: tz, timeZoneName: "long" }).formatToParts(new Date(iso)).find((p) => p.type === "timeZoneName")?.value ?? tz,
  };
}

/** W13 «verification where needed»: a 6-digit SMS code to the booking's own number before a change. */
export function CodeStep({ base, phone, onVerified }: { base: string; phone: string; onVerified: (session: string) => void }) {
  const t = useT("widget");
  const errText = useCustomerError();
  const [vid, setVid] = useState<string | null>(null);
  const [code, setCode] = useState("");
  const [left, setLeft] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => () => { if (timer.current) clearInterval(timer.current); }, []);
  function cooldown(s: number) {
    if (timer.current) clearInterval(timer.current);
    setLeft(s);
    timer.current = setInterval(() => setLeft((x) => { if (x <= 1 && timer.current) clearInterval(timer.current); return Math.max(0, x - 1); }), 1000);
  }
  async function send() {
    setPending(true); setError(null);
    try {
      const r = await api<{ verification_id: string; resend_after: number }>(`${base}/code`, { method: "POST", body: "{}" });
      setVid(r.verification_id); setCode(""); cooldown(r.resend_after);
    } catch (e) {
      const err = e as ApiError & { retry_after?: number };
      if (err.code === "too_soon" && err.retry_after) cooldown(err.retry_after);
      setError(errText(err));
    } finally { setPending(false); }
  }
  async function check(e: React.FormEvent) {
    e.preventDefault();
    const c = code.replace(/\s/g, "");
    if (!/^\d{6}$/.test(c)) { setError(t("customer.errors.code_format")); return; }
    setPending(true); setError(null);
    try {
      const r = await api<{ session: string }>(`${base}/verify`, { method: "POST", body: JSON.stringify({ verification_id: vid, code: c }) });
      onVerified(r.session);
    } catch (e) {
      const err = e as ApiError;
      setError(errText(err));
      if (err.code === "too_many_attempts" || err.code === "code_expired") setLeft(0);
    } finally { setPending(false); }
  }
  return (
    <Card>
      <h2 className="font-display text-headline-sm text-ink">{t("customer.code.title")}</h2>
      {!vid ? (
        <>
          <p className="text-body-md text-ink-soft">{t("customer.code.intro", { phone })}</p>
          {error && <Note tone="error">{error}</Note>}
          <Button icon="sms" onClick={send} disabled={pending} className="w-full min-h-[52px]">{t("customer.code.send")}</Button>
        </>
      ) : (
        <form onSubmit={check} className="flex flex-col gap-3" noValidate>
          <p className="text-body-md text-ink-soft">{t("customer.code.sent", { phone })}</p>
          <label className="flex flex-col gap-1 text-label-lg text-ink">{t("customer.code.label")}
            <input value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" autoComplete="one-time-code" maxLength={6}
              className="w-full min-h-[46px] px-3.5 py-2 rounded-xl bg-paper border-2 border-ink text-ink text-[18px] tracking-[0.3em] focus:outline-none focus:ring-[3px] focus:ring-accent focus:ring-offset-2" />
          </label>
          {error && <Note tone="error">{error}</Note>}
          <Button type="submit" icon="check_circle" disabled={pending} className="w-full min-h-[52px]">{t("customer.code.submit")}</Button>
          <Button type="button" variant="ghost" onClick={send} disabled={pending || left > 0}>
            {left > 0 ? t("customer.code.resendIn", { s: left }) : t("customer.code.resend")}
          </Button>
        </form>
      )}
    </Card>
  );
}
