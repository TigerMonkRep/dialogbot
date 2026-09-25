"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { Icon } from "@/components/ui";

const field = "w-full bg-surface-container-lowest rounded-lg px-4 py-3 text-primary text-body-md placeholder:text-outline/60 focus:outline-none focus:ring-2 focus:ring-primary shadow-sm";

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
  return <div role={tone === "error" ? "alert" : "status"} className={`rounded-lg p-3 font-body-sm text-body-sm ${tone === "ok" ? "bg-secondary-container text-on-secondary-container" : "bg-error-container text-on-error-container"}`}>{children}</div>;
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
        <label className="block font-label-md text-label-md text-on-surface mb-2 font-semibold" htmlFor="invite-code">Invitationskode</label>
        <input id="invite-code" autoComplete="off" autoCapitalize="characters" spellCheck={false} maxLength={64} required value={code} onChange={(e) => setCode(e.target.value)} placeholder="F.eks. DGB-XXXX-XXXX"
          className={`${field} font-mono font-semibold text-body-lg uppercase tracking-widest placeholder:font-sans placeholder:normal-case placeholder:tracking-normal`} />
      </div>
      {error && <Feedback tone="error">{error}</Feedback>}
      <button type="submit" disabled={pending || !code.trim()} className="w-full bg-primary hover:bg-primary-container text-on-primary py-3.5 px-6 rounded-lg font-label-lg text-label-lg font-semibold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60">
        {pending ? "Tjekker koden…" : "Lås op og se forsiden"}<Icon name="arrow_forward" size={20} className="text-secondary-fixed" />
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
          <label className="block font-label-md text-label-md text-on-surface mb-2 font-semibold" htmlFor="work-email">Din arbejds-e-mail</label>
          <input id="work-email" type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="navn@virksomhed.dk" className={field} aria-invalid={Boolean(fieldError(error, "email"))} />
        </div>
        <div>
          <label className="block font-label-md text-label-md text-on-surface mb-2 font-semibold" htmlFor="business-type">Virksomhedstype</label>
          <div className="relative">
            <select id="business-type" value={industry} onChange={(e) => setIndustry(e.target.value)} className={`${field} appearance-none cursor-pointer`}>
              <option value="">Vælg din branche…</option>
              {INDUSTRIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </select>
            <Icon name="expand_more" size={20} className="text-outline pointer-events-none absolute right-3.5 top-3.5" />
          </div>
        </div>
      </div>
      <fieldset className="pt-1">
        <legend className="block font-label-sm text-label-sm text-on-surface-variant mb-2">Hvad vil I primært løse først?</legend>
        <div className="flex flex-wrap gap-2">
          {INTERESTS.map(([k, l, icon]) => {
            const on = interests.includes(k);
            return (
              <button key={k} type="button" aria-pressed={on} onClick={() => toggle(k)}
                className={`px-3 py-1.5 rounded-full font-label-sm text-label-sm transition-all flex items-center gap-1.5 ${on ? "bg-primary text-on-primary" : "bg-surface-container-low hover:bg-surface-container text-on-surface-variant"}`}>
                <Icon name={on ? "check" : icon} size={16} className={on ? "" : "text-primary"} />{l}
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
      <label className="flex items-start gap-2 font-body-sm text-body-sm text-on-surface-variant cursor-pointer">
        <input type="checkbox" required checked={consent} onChange={(e) => setConsent(e.target.checked)} className="mt-0.5 rounded text-primary focus:ring-primary" />
        <span>Ja, I må skrive til mig, når Dialogbot åbner. Vi gemmer kun e-mail og svarene ovenfor til det formål, og du kan altid bede om at blive slettet.</span>
      </label>
      {error && <Feedback tone="error">{error.status === 422 ? "Tjek e-mailadressen og at du har sat flueben." : error.message}</Feedback>}
      <button type="submit" disabled={pending} className="w-full bg-secondary-fixed hover:bg-secondary-fixed-dim text-on-secondary-fixed py-3.5 px-6 rounded-lg font-label-lg text-label-lg font-bold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60">
        {pending ? "Skriver dig op…" : "Skriv mig på ventelisten"}<Icon name="notifications_active" size={20} />
      </button>
    </form>
  );
}
