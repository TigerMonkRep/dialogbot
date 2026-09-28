"use client";
import { useEffect, useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { Icon } from "@/components/ui";

type Info = { available: boolean; demo_number: string | null; open_now: boolean; hours: { from: string; to: string }; consent_text: string; consent_version: string };

const field = "w-full bg-surface-container-lowest rounded-lg px-4 py-3 text-on-surface text-body-md placeholder:text-outline/60 focus:outline-none focus:ring-2 focus:ring-primary shadow-sm";

/** "+4570123456" → "70 12 34 56" */
function pretty(e164: string) {
  const d = e164.replace(/^\+45/, "");
  return d.length === 8 ? d.replace(/(\d{2})(?=\d)/g, "$1 ") : e164;
}

/** "Hør den selv": the visitor asks our assistant to ring them now (consent is the ticked box and is stored with the
 *  call), or rings the public demo number. Nothing is called without the tick – markedsføringsloven § 10. */
export function DemoCall() {
  const [info, setInfo] = useState<Info | null>(null);
  const [f, setF] = useState({ phone: "", name: "", company: "", consent: false, website: "" });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);
  useEffect(() => { api<Info>("/demo-call").then(setInfo).catch(() => setInfo(null)); }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!info) return;
    setPending(true); setError(null);
    try {
      await api("/demo-call", { method: "POST", body: JSON.stringify({ ...f, consent_version: info.consent_version }) });
      setDone(true);
    } catch (err) { setError(err as ApiError); } finally { setPending(false); }
  };

  const number = info?.demo_number;
  return (
    <section id="demo" className="py-14 lg:py-20 scroll-mt-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg grid lg:grid-cols-2 gap-space-xl items-start">
        <div className="flex flex-col gap-space-md">
          <span className="self-start px-space-sm py-1 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold">Hør den selv</span>
          <h2 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-on-surface tracking-tight text-balance">Lad vores assistent ringe dig op – nu.</h2>
          <p className="font-body-lg text-body-lg text-on-surface-variant max-w-xl">Skriv dit nummer og din virksomhed. Assistenten ringer inden for et halvt minut og lader som om, den er receptionist hos jer. Prøv at ringe ind som en af jeres kunder, eller spørg den om Dialogbot.</p>
          {number && (
            <div className="flex items-center gap-space-md rounded-xl bg-surface-container-low p-space-md">
              <span className="w-10 h-10 rounded-full bg-primary text-on-primary flex items-center justify-center shrink-0"><Icon name="call" size={20} /></span>
              <div>
                <p className="font-label-md text-label-md text-on-surface-variant">Eller ring selv til demonummeret</p>
                <p className="font-headline-sm text-headline-sm font-bold text-primary tabular-nums select-all">{pretty(number)}</p>
              </div>
            </div>
          )}
        </div>

        <div className="rounded-2xl bg-surface-container-lowest shadow-md p-space-lg">
          {info === null ? (
            <p className="font-body-md text-body-md text-on-surface-variant">Henter…</p>
          ) : !info.available ? (
            <p className="font-body-md text-body-md text-on-surface-variant" role="status">Demo-opkald åbner ved lanceringen. Skriv dig på ventelisten, så giver vi besked.</p>
          ) : done ? (
            <div role="status" className="flex flex-col gap-space-sm">
              <p className="flex items-center gap-space-sm font-headline-sm text-headline-sm font-bold text-primary"><Icon name="phone_in_talk" size={24} />Vi ringer nu</p>
              <p className="font-body-md text-body-md text-on-surface-variant">Tag telefonen, når den ringer fra {number ? pretty(number) : "vores nummer"}. Samtalen varer højst fem minutter, og du kan lægge på når som helst.</p>
            </div>
          ) : (
            <form className="flex flex-col gap-space-md" onSubmit={submit} noValidate>
              <div>
                <label htmlFor="demo-phone" className="block font-label-md text-label-md text-on-surface mb-2 font-semibold">Dit telefonnummer</label>
                <input id="demo-phone" type="tel" inputMode="tel" autoComplete="tel" required value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="20 30 40 50" className={`${field} tabular-nums`} />
                {fieldError(error, "phone") && <p className="mt-1 font-body-sm text-body-sm text-error">Skriv et dansk telefonnummer med 8 cifre</p>}
              </div>
              <div className="grid sm:grid-cols-2 gap-space-md">
                <div>
                  <label htmlFor="demo-name" className="block font-label-md text-label-md text-on-surface mb-2 font-semibold">Fornavn</label>
                  <input id="demo-name" autoComplete="given-name" maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Mette" className={field} />
                </div>
                <div>
                  <label htmlFor="demo-company" className="block font-label-md text-label-md text-on-surface mb-2 font-semibold">Virksomhed</label>
                  <input id="demo-company" autoComplete="organization" maxLength={200} value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="Hansen Byg ApS" className={field} />
                </div>
              </div>
              <div aria-hidden className="absolute -left-[9999px] w-px h-px overflow-hidden">
                <label htmlFor="demo-website">Hjemmeside</label>
                <input id="demo-website" tabIndex={-1} autoComplete="off" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
              </div>
              <label className="flex items-start gap-space-sm font-body-sm text-body-sm text-on-surface">
                <input type="checkbox" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} className="mt-1 w-4 h-4 accent-primary shrink-0" />
                <span>{info.consent_text} Læs <a href="/privatliv" className="underline text-primary">privatlivspolitikken</a>.</span>
              </label>
              {error && !fieldError(error, "phone") && <p role="alert" className="rounded-lg p-3 bg-error-container text-on-error-container font-body-sm text-body-sm">{error.message}</p>}
              <button type="submit" disabled={pending || !f.consent || f.phone.trim().length < 8} className="bg-primary hover:bg-primary-container text-on-primary py-3.5 px-6 rounded-lg font-label-lg text-label-lg font-semibold flex items-center justify-center gap-2 shadow-sm transition-all disabled:opacity-60">
                <Icon name="call" size={20} className="text-secondary-fixed" />{pending ? "Ringer op…" : "Ring mig op nu"}
              </button>
              <p className="font-label-sm text-label-sm text-on-surface-variant">Vi ringer kl. {info.hours.from}–{info.hours.to}{info.open_now ? "" : " – prøv igen i det tidsrum"}. Kun danske numre. Gratis for dig.</p>
            </form>
          )}
        </div>
      </div>
    </section>
  );
}
