"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { Icon, inputCls } from "@/components/ui";

const field = inputCls;
const label = "block text-[13px] font-semibold text-ink mb-1.5";

export const INDUSTRIES: [string, string, string][] = [
  ["craft", "Håndværk & Byggeri", "construction"],
  ["clinic", "Salon, Klinik & Behandling", "spa"],
  ["service", "Service, Rådgivning & Ejendom", "support_agent"],
  ["retail", "B2B Handel & Kontor", "storefront"],
  ["other", "Anden branche", "more_horiz"],
];
const INTERESTS: [string, string, string][] = [
  ["missed_calls", "Tabte opkald i åbningstiden", "phone_in_talk"],
  ["calendar_booking", "Automatisk kalenderbooking", "calendar_add_on"],
  ["quote_followup", "Opfølgning på tilbud", "quickreply"],
];

function Feedback({ tone, children }: { tone: "ok" | "error"; children: React.ReactNode }) {
  return <div role={tone === "error" ? "alert" : "status"} className={`rounded-xl border-[1.5px] p-3.5 text-[15px] leading-normal ${tone === "ok" ? "bg-success-soft text-success border-success" : "bg-danger-soft text-danger border-danger"}`}>{children}</div>;
}

/** Card A: invitation code, checked on the server (/api/preview/unlock). */
export function UnlockForm({ next }: { next: string }) {
  const router = useRouter();
  const [code, setCode] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPending(true); setError(null);
    try {
      const r = await fetch("/api/preview/unlock", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ code, next }) });
      const body = await r.json().catch(() => ({}));
      if (!r.ok) { setError(body.message ?? "Koden kunne ikke kontrolleres."); return; }
      router.push(body.next ?? "/");
      router.refresh();
    } finally { setPending(false); }
  };
  return (
    <form className="space-y-4" onSubmit={submit}>
      <div>
        <label className={label} htmlFor="invite-code">Invitationskode</label>
        <input id="invite-code" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={64} required value={code} onChange={(e) => setCode(e.target.value)} placeholder="F.eks. DGB-XXXX-XXXX"
          className={`${field} font-mono font-semibold text-[17px] uppercase tracking-widest placeholder:font-sans placeholder:normal-case placeholder:tracking-normal`} />
      </div>
      {error && <Feedback tone="error">{error}</Feedback>}
      <button type="submit" disabled={pending || !code.trim()} className="w-full min-h-[52px] bg-accent hover:bg-accent-deep text-white px-6 rounded-[14px] text-[17px] font-semibold flex items-center justify-center gap-2.5 transition-colors disabled:opacity-60 disabled:cursor-not-allowed">
        {pending ? "Tjekker koden…" : "Lås op og se forsiden"}<Icon name="arrow_forward" size={20} />
      </button>
    </form>
  );
}

/** Card B: waitlist. Same answer for new and existing e-mails (no enumeration). */
export function WaitlistForm() {
  const [email, setEmail] = useState("");
  const [industry, setIndustry] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [consent, setConsent] = useState(false);
  const [website, setWebsite] = useState("");
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const toggle = (k: string) => setInterests((xs) => (xs.includes(k) ? xs.filter((x) => x !== k) : [...xs, k]));
  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setPending(true); setError(null);
    try {
      await api("/waitlist", { method: "POST", body: JSON.stringify({ email, industry: industry || null, interests, consent, website, source: "p00" }) });
      setDone(email.trim());
    } catch (err) { setError(err as ApiError); } finally { setPending(false); }
  };
  if (done) {
    return (
      <Feedback tone="ok">
        <span className="flex items-start gap-2"><Icon name="mark_email_read" size={20} /><span><strong className="block">Tak – du står på ventelisten.</strong>Vi skriver til {done}, når vi åbner for nye virksomheder. Vi sender ikke andet.</span></span>
      </Feedback>
    );
  }
  return (
    <form className="space-y-4" onSubmit={submit} noValidate={false}>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className={label} htmlFor="work-email">Din arbejds-e-mail</label>
          <input id="work-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="navn@virksomhed.dk" className={field} aria-invalid={Boolean(fieldError(error, "email"))} />
        </div>
        <div>
          <label className={label} htmlFor="business-type">Virksomhedstype</label>
          <div className="relative">
            <select id="business-type" value={industry} onChange={(e) => setIndustry(e.target.value)} className={`${field} appearance-none cursor-pointer`}>
              <option value="">Vælg din branche…</option>
              {INDUSTRIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <Icon name="expand_more" size={20} className="text-ink pointer-events-none absolute right-3.5 top-1/2 -translate-y-1/2" />
          </div>
        </div>
      </div>
      <fieldset className="pt-1">
        <legend className="block text-[13px] font-semibold text-ink mb-2">Hvad vil I primært løse først?</legend>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map(([k, l, icon]) => {
            const on = interests.includes(k);
            return (
              <button key={k} type="button" aria-pressed={on} onClick={() => toggle(k)}
                className={`min-h-[44px] px-4 rounded-full border-2 border-ink text-[14px] font-semibold transition-colors flex items-center gap-1.5 ${on ? "bg-ink text-white" : "bg-white hover:bg-panel text-ink"}`}>
                <Icon name={on ? "check" : icon} size={16} className={on ? "" : "text-accent"} />{l}
              </button>
            );
          })}
        </div>
      </fieldset>
      {/* Honeypot: invisible for people, tempting for bots. */}
      <div aria-hidden className="absolute -left-[9999px] w-px h-px overflow-hidden">
        <label htmlFor="website">Hjemmeside</label>
        <input id="website" tabIndex={-1} autoComplete="off" value={website} onChange={(e) => setWebsite(e.target.value)} />
      </div>
      <label className="flex items-start gap-2.5 text-[14px] leading-normal text-ink-soft cursor-pointer">
        <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 w-5 h-5 accent-accent flex-shrink-0" />
        <span>Ja, I må skrive til mig, når Dialogbot åbner. Vi gemmer kun e-mail og svarene ovenfor til det formål, og du kan altid bede om at blive slettet. <Link href="/privatliv" className="text-accent font-semibold underline underline-offset-4">Læs hvordan</Link>.</span>
      </label>
      {error && <Feedback tone="error">{error.status === 422 ? "Tjek e-mailadressen og at du har sat flueben." : error.message}</Feedback>}
      <button type="submit" disabled={pending} className="w-full min-h-[52px] bg-white hover:bg-panel text-ink border-2 border-ink px-6 rounded-[14px] text-[17px] font-semibold flex items-center justify-center gap-2.5 transition-colors disabled:opacity-60 disabled:cursor-not-allowed">
        {pending ? "Skriver dig op…" : "Skriv mig på ventelisten"}<Icon name="notifications_active" size={20} />
      </button>
    </form>
  );
}
