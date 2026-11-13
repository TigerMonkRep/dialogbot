"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import Link from "@/i18n/link";
import { InstallStep } from "@/components/install-step";
import { useLocale, useRaw, useT } from "@/i18n/client";
import { apiLanguage } from "@/i18n/config";
import { api, type ApiError } from "@/lib/client";
import { EMAIL, PHONE_DISPLAY, PHONE_TEL, SIGNUP_ERHVERV } from "@/lib/contact";
import { ArrowIcon, CloseIcon, PhoneIcon } from "@/components/site-icons";

/** The "Prøv den" conversation (Proev.dc.html): start → firma → branche (→ andet) → tlf → calling → done.
 *  The call is REAL: POST /demo-call (app/modules/sales) rings the number with our sales assistant. It needs the
 *  visitor's consent (markedsføringsloven § 10) and only works while demo calls are switched on, so the chat reads
 *  GET /demo-call first and says honestly when it cannot ring – it never pretends. Peter rings at once, day and night,
 *  every day (Fürster 12/11): there are no calling hours and no queue. «Opret dig» (self-service sign-up, open day
 *  and night) is always one click away (S0).
 *  Before Peter rings, the visitor proves the number with a 6-digit SMS code (F-AUD26-02-P06, Fürster 12/11 «A, SMS-kode
 *  først»): POST /demo-call/code → step «kode» («Vi har sendt en kode til …», «Send igen» after 30 s) →
 *  POST /demo-call/verify → POST /demo-call with the one-time token. Errors come by `code` in the page's language. */
type Info = {
  available: boolean; demo_number: string | null;
  consent_text: string; consent_version: string; industries: { key: string; label: string }[];
};
type Step = "start" | "firma" | "branche" | "andet" | "tlf" | "kode" | "calling" | "done" | "unavailable";
/** The SMS code sent to the number the visitor typed (POST /demo-call/code). */
type Pending = { id: string; phone: string; display: string; sentAt: number; resendAfter: number };
/** `signup`: the message carries an «Opret dig» button to the self-service sign-up. */
type Msg = { from: "bot" | "user"; text: string; signup?: boolean };

/** The chips: the backend's industry keys (app/modules/sales/script.py); null = "Noget andet", which asks for the
 *  visitor's own words. Labels: site.json → proev.chat.branches.<key> ("other" for null). Step labels:
 *  proev.chat.steps.<step>. */
const BRANCHES: (string | null)[] = ["haandvaerk", "klinik", "skoenhed", "restaurant", "raadgivning", null];
/** How long the phone card shows "ringer" before the chat moves on. We cannot see when the call ends. */
const CALL_WINDOW_MS = 45_000;

const chip = "min-h-11 px-4 rounded-full bg-white border-2 border-ink text-ink font-semibold text-[15px] cursor-pointer hover:bg-panel";
const avatar = "flex-none w-[30px] h-[30px] rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-[13px] text-white";

/** `embedded`: the chat stage alone, filling its container (the floating widget on every other page) – no side
 *  column, the log scrolls, and the header gets a close button. Default: the full /proev layout with the aside. */
export function ProevChat({ embedded = false, onClose }: { embedded?: boolean; onClose?: () => void } = {}) {
  const t = useT("site");
  const raw = useRaw();
  const locale = useLocale();
  const c = (key: string, vars?: Record<string, string | number>) => t(`proev.chat.${key}`, vars);
  const GREETING = c("greeting");
  const hours = c("hours");
  const [info, setInfo] = useState<Info | null | "error">(null);
  const [step, setStep] = useState<Step>("start");
  const [history, setHistory] = useState<Msg[]>([{ from: "bot", text: GREETING }]);
  const [typing, setTyping] = useState(false);
  const [draft, setDraft] = useState("");
  const [firma, setFirma] = useState("");
  const [industry, setIndustry] = useState<{ key: string | null; other: string }>({ key: null, other: "" });
  const [tlf, setTlf] = useState("");
  const [consent, setConsent] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const [pending, setPending] = useState(false);
  const [verif, setVerif] = useState<Pending | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const timers = useRef<number[]>([]);

  useEffect(() => {
    api<Info>("/demo-call").then((i) => setInfo({ ...i, industries: i.industries ?? [] })).catch(() => setInfo("error"));
    const t = timers.current;
    return () => t.forEach(clearTimeout);
  }, []);
  useEffect(() => { endRef.current?.scrollIntoView({ block: "nearest", behavior: "smooth" }); }, [history, typing]);
  useEffect(() => { if (step === "firma" || step === "andet" || step === "tlf" || step === "kode") inputRef.current?.focus(); }, [step]);
  // the «Send igen» countdown
  useEffect(() => {
    if (step !== "kode") return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [step]);

  const push = useCallback((m: Msg) => setHistory((h) => h.concat(m)), []);
  const later = useCallback((fn: () => void, ms: number) => { timers.current.push(window.setTimeout(fn, ms)); }, []);
  /** The bot "types" for 700 ms, then answers and moves to the next step. */
  const botSays = useCallback((text: string, next?: Step, ms = 700, signup = false) => {
    setTyping(true);
    later(() => { setTyping(false); push({ from: "bot", text, signup }); if (next) setStep(next); }, ms);
  }, [later, push]);

  /** Why we cannot ring at all – or null when we can (at once, at any hour). Honest copy; never claims a call was
   *  placed. */
  const blocker = (): string | null => {
    if (info === null) return null; // still loading: ask on, check again before dialling
    if (info === "error" || !info.available) {
      return c("blockerInactive", { phone: PHONE_DISPLAY, hours, email: EMAIL });
    }
    return null;
  };

  const startChips = [
    { label: c("chipCall"), act: () => {
      push({ from: "user", text: c("chipCall") });
      const why = blocker();
      if (why) botSays(why, "unavailable", 700, true);
      else botSays(c("askCompany"), "firma");
    } },
    { label: c("chipWhat"), act: () => { push({ from: "user", text: c("chipWhat") }); botSays(c("answerWhat"), "start"); } },
    { label: c("chipPrice"), act: () => { push({ from: "user", text: c("chipPrice") }); botSays(c("answerPrice"), "start", 700, true); } },
  ];
  const chooseBranch = (label: string, key: string | null) => () => {
    push({ from: "user", text: label });
    setIndustry({ key, other: "" });
    if (key === null) botSays(c("askOther"), "andet");
    else botSays(c("askNumber", { company: firma }), "tlf");
  };

  const reset = () => {
    timers.current.forEach(clearTimeout); timers.current = [];
    setStep("start"); setHistory([{ from: "bot", text: GREETING }]); setTyping(false); setDraft(""); setFirma("");
    setIndustry({ key: null, other: "" }); setTlf(""); setConsent(false); setConsentError(false); setPending(false);
    setVerif(null); setCodeError(null);
  };

  /** The visitor-facing text for an error of the code/verify/call endpoints, in the page's language. */
  const errorText = (a: ApiError | undefined): string => {
    switch (a?.code) {
      case "too_soon": return c("errTooSoon");
      case "sms_rate_limited": return c("errSmsLimit", { phone: PHONE_DISPLAY });
      case "sms_failed": return c("errSmsFailed", { phone: PHONE_DISPLAY });
      case "code_invalid": return c("errCodeWrong", { left: Number((a as ApiError & { attempts_left?: number }).attempts_left ?? 0) });
      case "code_expired": return c("errCodeExpired");
      case "too_many_attempts": return c("errTooManyAttempts");
      case "verification_invalid": case "verification_required": return c("errVerificationInvalid");
      case "demo_already_called": return c("errAlreadyCalled", { phone: PHONE_DISPLAY });
      case "demo_rate_limited": return c("errCallLimit", { phone: PHONE_DISPLAY });
      case "validation_failed": if (a.field_errors?.some((f) => f.field === "phone")) return c("errNumber");
    }
    return a?.message || c("callFailed"); // anything else: the server's own words, as before
  };

  /** Step 1: the code by SMS to the number (also «Send igen»). */
  const sendCode = async (phone: string, again: boolean): Promise<boolean> => {
    if (info === null || info === "error") return false;
    const r = await api<{ verification_id: string; phone_display: string | null; resend_after: number }>("/demo-call/code", {
      method: "POST", body: JSON.stringify({ phone, consent: true, consent_version: info.consent_version, website: "", language: apiLanguage(locale) }) });
    setVerif({ id: r.verification_id, phone, display: r.phone_display || phone, sentAt: Date.now(), resendAfter: r.resend_after || 30 });
    setNow(Date.now()); setCodeError(null); setTlf(r.phone_display || phone);
    push({ from: "bot", text: again ? c("codeResent", { number: r.phone_display || phone }) : c("codeSent", { number: r.phone_display || phone }) });
    return true;
  };

  const resend = async () => {
    if (!verif || pending) return;
    setPending(true);
    try { await sendCode(verif.phone, true); }
    catch (err) { setCodeError(errorText(err as ApiError)); }
    finally { setPending(false); }
  };

  const changeNumber = () => { setVerif(null); setCodeError(null); setDraft(""); setStep("tlf"); };

  /** Steps 2 and 3: the code → a one-time token → Peter rings the proven number at once. */
  const confirmCode = async (code: string) => {
    if (!verif || info === null || info === "error") return;
    if (!/^\d{6}$/.test(code)) { setCodeError(c("errCodeFormat")); return; }
    setPending(true); setCodeError(null);
    try {
      const v = await api<{ verification_token: string }>("/demo-call/verify", { method: "POST",
        body: JSON.stringify({ verification_id: verif.id, code }) });
      setDraft(""); setTyping(true);
      await api("/demo-call", { method: "POST", body: JSON.stringify({
        phone: verif.phone, company: firma, consent: true, consent_version: info.consent_version, website: "",
        industry: industry.key ?? "andet", industry_other: industry.key ? null : industry.other || null,
        verification_token: v.verification_token }) });
      setTyping(false);
      push({ from: "bot", text: c("callingNow", { number: verif.display, company: firma }) });
      setStep("calling");
      later(() => botSays(c("callSent", { phone: PHONE_DISPLAY }), "done", 700, true), CALL_WINDOW_MS);
    } catch (err) {
      setTyping(false);
      const a = err as ApiError;
      if (a?.code === "demo_unavailable") botSays(a.message || c("callFailed"), "unavailable", 700, true);
      else if (a?.code === "demo_call_failed") botSays(c("callRetry", { message: a.message || c("callFailed"), phone: PHONE_DISPLAY }), "tlf");
      else setCodeError(errorText(a));
    } finally { setPending(false); }
  };

  /** Anything that is not one of the scripted steps goes to Peter himself: POST /demo-call/chat answers from the
   *  sales workspace's approved knowledge. The step does not change, so the chips stay where they were. */
  const ask = async (v: string) => {
    push({ from: "user", text: v }); setDraft(""); setPending(true); setTyping(true);
    const messages = history.concat({ from: "user", text: v }).slice(-16)
      .map((m) => ({ role: m.from === "bot" ? "assistant" : "user", content: m.text.slice(0, 600) }));
    try {
      const r = await api<{ reply: string; signup_url?: string | null }>("/demo-call/chat", { method: "POST", body: JSON.stringify({ messages, website: "" }) });
      setTyping(false); push({ from: "bot", text: r.reply, signup: !!r.signup_url });
    } catch (err) {
      setTyping(false);
      const a = err as ApiError;
      push({ from: "bot", signup: true, text: a?.code === "demo_unavailable"
        ? c("chatNotReady", { phone: PHONE_DISPLAY, hours, email: EMAIL })
        : c("chatFailed", { phone: PHONE_DISPLAY }) });
    } finally { setPending(false); }
  };

  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const v = draft.trim();
    if (!v || pending) return;
    if (step === "start" || step === "unavailable" || step === "calling" || step === "done") { await ask(v); return; }
    if (step === "kode") {
      const code = v.replace(/\s/g, "");
      if (!/\d/.test(code)) { await ask(v); return; } // a question, not a code: Peter answers, the step stays
      await confirmCode(code); return;
    }
    if (step === "branche") {
      push({ from: "user", text: v }); setDraft(""); setIndustry({ key: null, other: v });
      botSays(c("askNumber", { company: firma }), "tlf");
      return;
    }
    if (step === "tlf" && !/\d{8}/.test(v.replace(/[\s+\-()]/g, ""))) { await ask(v); return; }
    if (step === "firma") {
      push({ from: "user", text: v }); setFirma(v); setDraft("");
      botSays(c("helloCompany", { company: v }), "branche");
      return;
    }
    if (step === "andet") {
      push({ from: "user", text: v }); setIndustry((i) => ({ ...i, other: v })); setDraft("");
      botSays(c("askNumber", { company: firma }), "tlf");
      return;
    }
    if (step !== "tlf") return;
    if (!consent) { setConsentError(true); return; }
    const why = blocker();
    push({ from: "user", text: v }); setTlf(v); setDraft("");
    if (why || info === null || info === "error") { botSays(why ?? c("serviceDown"), "unavailable"); return; }
    setPending(true); setTyping(true);
    try {
      await sendCode(v, false);
      setTyping(false);
      setStep("kode");
    } catch (err) {
      setTyping(false);
      const a = err as ApiError;
      if (a?.code === "demo_unavailable") botSays(a.message || c("callFailed"), "unavailable", 700, true);
      else botSays(c("callRetry", { message: errorText(a), phone: PHONE_DISPLAY }), "tlf");
    } finally { setPending(false); }
  };

  const hasInput = true; // the chips are shortcuts; the visitor can always write to Peter instead
  const placeholder = step === "firma" ? c("placeholderCompany") : step === "andet" ? c("placeholderOther")
    : step === "tlf" ? c("placeholderPhone") : step === "kode" ? c("placeholderCode") : step === "branche" ? c("placeholderBranch")
    : c("placeholderDefault");
  const done = step === "done";
  const calling = step === "calling";
  const pastOne = step === "tlf" || step === "kode" || calling || done;
  const waitLeft = verif ? Math.max(0, Math.ceil((verif.sentAt + verif.resendAfter * 1000 - now) / 1000)) : 0;
  const consentText = info && info !== "error" ? info.consent_text
    : c("consentFallback");

  const phone = calling ? null
    : done ? [c("phoneDoneTitle"), c("phoneDoneText")]
    : step === "unavailable" ? [c("phoneUnavailableTitle"), c("phoneUnavailableText", { hours, phone: PHONE_DISPLAY, email: EMAIL })]
    : [c("phoneIdleTitle"), c("phoneIdleText")];

  const stage = (
      <section aria-label={c("stageLabel")}
        className={`min-w-0 bg-white flex flex-col overflow-hidden ${embedded
 ?"h-full w-full"
 :"flex-[1_1_460px] max-w-[640px] border-2 border-ink rounded-[22px] shadow-block"}`}>
        <div className="flex items-center gap-3 px-4 py-3 sm:px-5 sm:py-4 border-b-2 border-ink">
          <span className="inline-flex w-10 h-10 rounded-xl bg-accent items-center justify-center font-display font-extrabold text-white text-lg">D</span>
          <div className="flex flex-col min-w-0">
            <span className="font-display font-bold text-[17px]">Dialogbot</span>
            <span className="text-[13px] text-muted flex items-center gap-1.5"><span aria-hidden className="w-2 h-2 rounded-full bg-[#1B9E5A]" />{c("status")}</span>
          </div>
          <span className={`ml-auto text-xs font-semibold tracking-[1.5px] uppercase px-2.5 py-1.5 rounded-full bg-highlight ${embedded ? "hidden sm:inline" : ""}`} aria-live="polite">{c(`steps.${step}`)}</span>
          {onClose && (
            <button type="button" onClick={onClose} aria-label={c("close")} className={`w-11 h-11 rounded-[10px] bg-white inline-flex items-center justify-center text-ink hover:bg-panel cursor-pointer ${embedded ? "ml-auto sm:ml-0" : "ml-2"}`}>
              <CloseIcon size={18} />
            </button>
          )}
        </div>

        <div className={`flex flex-col gap-3 p-4 sm:p-5 bg-white ${embedded ? "flex-1 min-h-0 overflow-y-auto" : "min-h-[360px]"}`} role="log" aria-live="polite">
          {history.map((m, i) => {
            const bot = m.from === "bot";
            return (
              <div key={i} className={`flex gap-2.5 items-end ${bot ? "" : "justify-end"}`}>
                {bot && <span className={avatar}>D</span>}
                <div className={`flex flex-col gap-2 min-w-0 ${bot ? "items-start" : "items-end"}`}>
                  <p className={`m-0 px-4 py-3 text-[15px] leading-normal max-w-[420px] whitespace-pre-line border-2 border-ink ${bot ? "rounded-[16px_16px_16px_4px] bg-white text-ink" : "rounded-[16px_16px_4px_16px] bg-ink text-white"}`}>{m.text}</p>
                  {bot && m.signup && (
                    <Link href={SIGNUP_ERHVERV} data-signup-link className="inline-flex items-center gap-2 min-h-11 px-4 rounded-xl bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[15px]">{c("signupCta")}<ArrowIcon size={16} /></Link>
                  )}
                </div>
              </div>
            );
          })}
          {typing && (
            <div className="flex gap-2.5 items-end" aria-label={c("typing")}>
              <span className={avatar}>D</span>
              <span className="inline-flex gap-[5px] px-4 py-3.5 rounded-[16px_16px_16px_4px] bg-white border-2 border-ink">
                <span className="dot1 w-[7px] h-[7px] rounded-full bg-ink" /><span className="dot2 w-[7px] h-[7px] rounded-full bg-ink" /><span className="dot3 w-[7px] h-[7px] rounded-full bg-ink" />
              </span>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <div className="flex flex-col gap-3 px-4 pt-4 pb-5 sm:px-5 border-t-2 border-ink bg-panel">
          {step === "start" && !typing && (
            <div className="flex flex-wrap gap-2">
              {startChips.map((q) => <button key={q.label} type="button" onClick={q.act} className={chip}>{q.label}</button>)}
              <Link href={SIGNUP_ERHVERV} className={`${chip} inline-flex items-center no-underline !bg-accent !border-accent !text-white`}>{c("signupCta")}</Link>
            </div>
          )}
          {(step === "done" || step === "unavailable" || step === "calling") && !typing && null}
          {step === "branche" && !typing && (
            <div className="flex flex-wrap gap-2">{BRANCHES.map((k) => { const l = c(`branches.${k ?? "other"}`); return <button key={k ?? "other"} type="button" onClick={chooseBranch(l, k)} className={chip}>{l}</button>; })}</div>
          )}
          {step === "unavailable" && !typing && (
            <div className="flex flex-wrap gap-2">
              <Link href={SIGNUP_ERHVERV} className={`${chip} inline-flex items-center no-underline !bg-accent !border-accent !text-white`}>{c("signupCta")}</Link>
              <a href={PHONE_TEL} className={`${chip} inline-flex items-center gap-2 no-underline`}><PhoneIcon size={16} />{c("callUs")}</a>
              <a href={`mailto:${EMAIL}?subject=${encodeURIComponent(c("mailSubject"))}`} className={`${chip} inline-flex items-center no-underline`}>{c("mailUs")}</a>
              <Link href="/byggevejledning" className={`${chip} inline-flex items-center no-underline`}>{c("seeGuide")}</Link>
              <button type="button" onClick={reset} className={chip}>{c("tryAgain")}</button>
            </div>
          )}
          {hasInput && (
            <form onSubmit={send} className="flex flex-col gap-3">
              <div className="flex gap-2.5">
                <label htmlFor="chat-input" className="sr-only">{step === "kode" ? c("codeLabel") : placeholder}</label>
                <input ref={inputRef} id="chat-input" type="text" inputMode={step === "tlf" ? "tel" : step === "kode" ? "numeric" : "text"} value={draft}
                  onChange={(e) => { setDraft(e.target.value); if (step === "kode") setCodeError(null); }} placeholder={placeholder}
                  autoComplete={step === "tlf" ? "tel" : step === "kode" ? "one-time-code" : "organization"} disabled={pending}
                  maxLength={step === "kode" ? 12 : undefined} aria-invalid={step === "kode" && !!codeError} aria-describedby={step === "kode" ? "code-hint" : undefined}
                  className="flex-1 min-w-0 min-h-12 px-4 rounded-xl border-2 border-ink text-base text-ink bg-white placeholder:text-muted/70" />
                <button type="submit" disabled={pending} className="inline-flex items-center gap-2 min-h-12 px-[18px] rounded-xl bg-accent hover:bg-accent-deep text-white font-semibold text-[15px] cursor-pointer disabled:opacity-60">
                  {step === "kode" ? c("confirmCode") : step === "tlf" && /\d{8}/.test(draft.replace(/[\s+\-()]/g, "")) ? c("callMe") : c("send")}<ArrowIcon size={16} />
                </button>
              </div>
              {step === "kode" && verif && (
                <div data-code-step className="flex flex-col gap-2 text-[14px] leading-normal">
                  <p className="m-0 font-semibold">{c("codeSentShort", { number: verif.display })}</p>
                  <p id="code-hint" role={codeError ? "alert" : undefined} className={`m-0 ${codeError ? "text-danger font-semibold" : "text-ink-soft"}`}>
                    {codeError ?? c("codeHelp")}
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <button type="button" data-resend onClick={resend} disabled={pending || waitLeft > 0} className={`${chip} disabled:opacity-60 disabled:cursor-not-allowed`}>
                      {waitLeft > 0 ? c("resendIn", { s: waitLeft }) : c("resend")}
                    </button>
                    <button type="button" onClick={changeNumber} disabled={pending} className={chip}>{c("changeNumber")}</button>
                  </div>
                </div>
              )}
              {step === "tlf" && (
                <>
                  {/* Honeypot: hidden from people, filled by bots; the backend then stores nothing and calls nobody. */}
                  <input type="text" name="website" tabIndex={-1} autoComplete="off" aria-hidden className="hidden" defaultValue="" />
                  <label className={`flex items-start gap-3 text-[13px] leading-normal cursor-pointer ${consentError ? "text-danger" : "text-ink-soft"}`}>
                    <input type="checkbox" checked={consent} onChange={(e) => { setConsent(e.target.checked); if (e.target.checked) setConsentError(false); }}
                      className="mt-0.5 w-5 h-5 shrink-0 accent-accent" aria-invalid={consentError} />
                    <span>{consentText}{consentError && <b className="block mt-1">{c("consentError")}</b>}</span>
                  </label>
                </>
              )}
            </form>
          )}
          {done && <InstallStep audience="erhverv" />}
          {done && (
            <div className="flex flex-wrap gap-2.5">
              <Link href="/signup" className="inline-flex items-center gap-2.5 min-h-12 px-5 rounded-xl bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[15px]">{c("buildNow")}</Link>
              <button type="button" onClick={reset} className="min-h-12 px-[18px] rounded-xl bg-white border-2 border-ink text-ink font-semibold text-[15px] cursor-pointer hover:bg-panel">{c("tryAgain")}</button>
            </div>
          )}
          {calling && <p className="m-0 text-sm font-semibold">{c("pickUp")}</p>}
          <Link href={SIGNUP_ERHVERV} className="self-start text-[14px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11" data-signup-line>{c("signupLine")}</Link>
          <span className="text-xs text-muted">{c("privacy")}</span>
        </div>
      </section>
  );

  if (embedded) return stage;
  const sideSteps = raw<string[]>("site.proev.chat.sideSteps");

  return (
    <div className="flex flex-wrap gap-8 items-start">
      {stage}

      {/* SIDE: what happens */}
      <aside className="flex-[1_1_320px] min-w-0 flex flex-col gap-5">
        <div className="bg-white border-2 border-ink rounded-[20px] p-6 flex flex-col gap-4 items-center text-center min-h-[250px] justify-center" aria-live="polite">
          {calling ? (
            <>
              <div className="relative w-24 h-24 flex items-center justify-center">
                <span aria-hidden className="ringwave absolute inset-0 rounded-full border-[3px] border-accent" />
                <span aria-hidden className="ringwave2 absolute inset-0 rounded-full border-[3px] border-accent" />
                <span className="w-[72px] h-[72px] rounded-full bg-accent inline-flex items-center justify-center"><PhoneIcon size={32} stroke="#FFFFFF" /></span>
              </div>
              <span className="font-display font-bold text-xl">{c("ringing", { number: tlf })}</span>
              <span className="text-sm text-ink-soft">{c("presentBefore")}<b>{firma}</b>{c("presentAfter")}</span>
            </>
          ) : (
            <>
              <span className="inline-flex w-[72px] h-[72px] rounded-full bg-panel border-2 border-ink items-center justify-center"><PhoneIcon size={32} /></span>
              <span className="font-display font-bold text-xl">{phone![0]}</span>
              <span className="text-sm text-ink-soft">{phone![1]}</span>
            </>
          )}
        </div>

        <ol className="m-0 p-0 list-none flex flex-col gap-2.5">
          {([["1", sideSteps[0], true], ["2", sideSteps[1], pastOne], ["3", sideSteps[2], done]] as [string, string, boolean][]).map(([n, label, on]) => (
            <li key={n} className="flex gap-3 items-center px-3.5 py-3 rounded-[14px] bg-white border-2 border-ink">
              <span className={`flex-none inline-flex w-9 h-9 rounded-[10px] items-center justify-center font-display font-extrabold text-lg ${on ? "bg-highlight" : "bg-panel"}`}>{n}</span>
              <span className="text-[15px] font-semibold">{label}</span>
            </li>
          ))}
        </ol>

        <p className="m-0 text-[13px] leading-normal text-muted">{c("sideNote")}</p>
      </aside>
    </div>
  );
}
