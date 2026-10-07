"use client";
import { useEffect, useRef, useState } from "react";
import { api, fieldError, type ApiError } from "@/lib/client";
import { Icon } from "@/components/ui";

type Voice = { key: string; name: string; gender: string; image: string; description: string; sample: boolean };
type Industry = { key: string; label: string; icon: string; examples: string };
type Info = {
  available: boolean; demo_number: string | null; open_now: boolean; hours: { from: string; to: string };
  consent_text: string; consent_version: string; voices: Voice[]; industries: Industry[];
};

const field = "w-full bg-surface-container-low rounded-xl px-4 py-3.5 text-on-surface text-body-md placeholder:text-outline/60 focus:outline-none focus:ring-2 focus:ring-primary";

/** "+4570123456" → "70 12 34 56" */
function pretty(e164: string) {
  const d = e164.replace(/^\+45/, "");
  return d.length === 8 ? d.replace(/(\d{2})(?=\d)/g, "$1 ") : e164;
}

/** The "Dialogbot taler" dots from the brand video: dark and lime dots that swell like a voice. */
export function VoiceDots({ light = false, className = "" }: { light?: boolean; className?: string }) {
  const dots: [number, "dark" | "lime"][] = [[8, "dark"], [16, "dark"], [14, "lime"], [30, "dark"], [14, "lime"], [16, "dark"], [8, "dark"]];
  return (
    <div aria-hidden className={`flex items-center gap-2.5 ${className}`}>
      {dots.map(([size, tone], i) => (
        <span key={i} className={`rounded-full animate-talk ${tone === "lime" ? "bg-secondary-fixed" : light ? "bg-on-primary/85" : "bg-primary"}`}
          style={{ width: size, height: size, animationDelay: `${(i % 4) * 140}ms` }} />
      ))}
    </div>
  );
}

/** "Hør den selv": the visitor picks a voice and their line of business, and our assistant rings them now with a
 *  sales demo adapted to that business. Consent is the ticked box and is stored with the call – markedsføringsloven
 *  § 10. Nothing is called without it. */
export function DemoCall() {
  const [info, setInfo] = useState<Info | null>(null);
  const [f, setF] = useState({ phone: "", name: "", company: "", consent: false, website: "", voice: "", industry: "" });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [done, setDone] = useState(false);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    api<Info>("/demo-call").then((raw) => {
      const i = { ...raw, voices: raw.voices ?? [], industries: raw.industries ?? [] };
      setInfo(i);
      setF((x) => ({ ...x, voice: x.voice || i.voices[0]?.key || "" }));
    })
      .catch(() => setInfo(null));
    return () => audio.current?.pause();
  }, []);

  const play = (key: string) => {
    audio.current?.pause();
    if (playing === key) { setPlaying(null); return; }
    const a = new Audio(`/api/backend/demo-call/voices/${key}/sample`);
    audio.current = a;
    a.onended = () => setPlaying(null);
    a.onerror = () => setPlaying(null);
    setPlaying(key);
    a.play().catch(() => setPlaying(null));
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!info) return;
    setPending(true); setError(null);
    try {
      await api("/demo-call", { method: "POST", body: JSON.stringify({
        phone: f.phone, name: f.name, company: f.company, consent: f.consent, website: f.website,
        voice: f.voice || null, industry: f.industry || null, consent_version: info.consent_version }) });
      audio.current?.pause();
      setDone(true);
    } catch (err) { setError(err as ApiError); } finally { setPending(false); }
  };

  const number = info?.demo_number;
  const voice = info?.voices.find((v) => v.key === f.voice);
  const step = (n: number, label: string) => (
    <span className="flex items-center gap-space-sm font-label-lg text-label-lg font-bold text-on-surface">
      <span className="w-7 h-7 rounded-full bg-primary text-secondary-fixed flex items-center justify-center font-label-md text-label-md">{n}</span>{label}
    </span>
  );

  return (
    <section id="demo" aria-labelledby="demo-title" className="bg-surface-container-low py-14 lg:py-24 scroll-mt-28">
      <div className="max-w-7xl mx-auto px-4 sm:px-margin-md lg:px-margin-lg">
        <div className="grid lg:grid-cols-12 rounded-[2rem] overflow-hidden shadow-xl bg-surface-container-lowest">
          {/* Pitch */}
          <div className="relative lg:col-span-5 bg-primary text-on-primary p-space-lg sm:p-space-xl lg:p-12 flex flex-col gap-space-lg overflow-hidden">
            <div aria-hidden className="absolute -bottom-24 -right-24 w-80 h-80 rounded-full bg-primary-container/70 blur-2xl" />
            <div aria-hidden className="absolute -top-28 -left-16 w-72 h-72 rounded-full bg-secondary/25 blur-3xl" />
            <span className="relative font-label-md text-label-md uppercase tracking-[0.18em] text-secondary-fixed">Hør det selv – på din egen telefon</span>
            <h2 id="demo-title" className="relative text-[2.6rem] sm:text-6xl lg:text-[4.1rem] font-bold tracking-tight text-balance leading-[0.98]">
              Hvem tager telefonen, når du er optaget?
            </h2>
            <p className="relative font-body-lg text-body-lg text-on-primary-container max-w-md">
              Lad Dialogbot ringe dig op <strong className="text-on-primary">nu</strong>. Vælg stemmen, fortæl hvad I laver – så tager assistenten telefonen, som var den receptionist hos jer.
            </p>
            <div className="relative flex flex-col gap-space-sm">
              <VoiceDots light />
              <span className="flex items-center gap-2 font-label-md text-label-md text-on-primary-container"><span className="w-2 h-2 rounded-full bg-secondary-fixed animate-pulse" />Dialogbot taler</span>
            </div>
            <ul className="relative flex flex-col gap-space-sm font-body-md text-body-md">
              {["Ringer op på under et minut", "Rollespil tilpasset din branche", "Hør hvordan vi guider jer gennem opsætningen", "Gratis · tager 3-4 minutter · læg på når som helst"].map((t) => (
                <li key={t} className="flex items-start gap-space-sm"><Icon name="check_circle" size={20} filled className="text-secondary-fixed mt-0.5 shrink-0" />{t}</li>
              ))}
            </ul>
            {number && (
              <div className="relative mt-auto flex items-center gap-space-md rounded-2xl bg-on-primary/10 p-space-md">
                <span className="w-11 h-11 rounded-full bg-secondary-fixed text-on-secondary-fixed flex items-center justify-center shrink-0"><Icon name="call" size={22} /></span>
                <div>
                  <p className="font-label-md text-label-md text-on-primary-container">Eller ring selv til os</p>
                  <p className="font-headline-sm text-headline-sm font-bold tabular-nums select-all">{pretty(number)}</p>
                </div>
              </div>
            )}
          </div>

          {/* Form */}
          <div className="lg:col-span-7 p-space-lg sm:p-space-xl lg:p-12">
            {info === null ? (
              <p className="font-body-md text-body-md text-on-surface-variant">Henter…</p>
            ) : done ? (
              <div role="status" className="h-full flex flex-col items-center justify-center text-center gap-space-md py-space-xl">
                <span className="relative w-24 h-24 rounded-full bg-secondary-fixed text-on-secondary-fixed flex items-center justify-center">
                  <span aria-hidden className="absolute inset-0 rounded-full bg-secondary-fixed animate-ping opacity-60" />
                  <Icon name="phone_in_talk" size={44} className="relative" />
                </span>
                <p className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg font-bold text-primary">Vi ringer til dig nu</p>
                <p className="font-body-lg text-body-lg text-on-surface-variant max-w-md">
                  Tag telefonen, når den ringer{number ? ` fra ${pretty(number)}` : ""}. {voice ? `${voice.name} tager samtalen.` : ""} Samtalen tager 3-4 minutter, og du kan lægge på når som helst.
                </p>
                <VoiceDots />
              </div>
            ) : (
              <form className="flex flex-col gap-space-lg" onSubmit={submit} noValidate>
                <fieldset className="flex flex-col gap-space-sm">
                  <legend className="mb-space-sm">{step(1, "Vælg stemme")}</legend>
                  <div className="grid sm:grid-cols-2 gap-space-sm">
                    {info.voices.map((v) => {
                      const on = f.voice === v.key;
                      return (
                        <div key={v.key} className={`relative rounded-2xl p-space-md flex items-center gap-space-md transition-all ${on ? "bg-primary text-on-primary shadow-md" : "bg-surface-container-low hover:bg-surface-container"}`}>
                          <label className="absolute inset-0 cursor-pointer rounded-2xl">
                            <input type="radio" name="voice" value={v.key} checked={on} onChange={() => setF({ ...f, voice: v.key })} className="sr-only" />
                            <span className="sr-only">{v.name}</span>
                          </label>
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img src={v.image} alt="" className={`w-14 h-14 rounded-full shrink-0 ${on ? "ring-4 ring-secondary-fixed" : ""}`} />
                          <div className="min-w-0 flex-1">
                            <p className="font-headline-sm text-headline-sm font-bold">{v.name}</p>
                            <p className={`font-body-sm text-body-sm line-clamp-2 ${on ? "text-on-primary-container" : "text-on-surface-variant"}`}>{v.description}</p>
                          </div>
                          {v.sample && (
                            <button type="button" onClick={() => play(v.key)} aria-label={playing === v.key ? `Stop ${v.name}` : `Hør ${v.name}`}
                              className={`relative z-10 w-11 h-11 rounded-full flex items-center justify-center shrink-0 transition-all ${on ? "bg-secondary-fixed text-on-secondary-fixed" : "bg-primary text-on-primary"}`}>
                              <Icon name={playing === v.key ? "stop" : "play_arrow"} size={24} filled />
                            </button>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </fieldset>

                <fieldset className="flex flex-col gap-space-sm">
                  <legend className="mb-space-sm">{step(2, "Hvad laver I?")}</legend>
                  <div className="flex flex-wrap gap-space-xs">
                    {[...info.industries, { key: "andet", label: "Noget andet", icon: "more_horiz", examples: "" }].map((i) => {
                      const on = f.industry === i.key;
                      return (
                        <label key={i.key} title={i.examples || undefined}
                          className={`cursor-pointer inline-flex items-center gap-1.5 rounded-full px-space-md py-2 font-label-md text-label-md font-semibold transition-all focus-within:ring-2 focus-within:ring-primary ${on ? "bg-secondary-fixed text-on-secondary-fixed shadow-sm" : "bg-surface-container-low text-on-surface-variant hover:bg-surface-container hover:text-on-surface"}`}>
                          <input type="radio" name="industry" value={i.key} checked={on} onChange={() => setF({ ...f, industry: i.key })} className="sr-only" />
                          <Icon name={i.icon} size={18} />{i.label}
                        </label>
                      );
                    })}
                  </div>
                </fieldset>

                <fieldset className="flex flex-col gap-space-sm">
                  <legend className="mb-space-sm">{step(3, "Hvor skal vi ringe?")}</legend>
                  <div>
                    <label htmlFor="demo-phone" className="sr-only">Dit telefonnummer</label>
                    <div className="relative">
                      <span className="absolute left-4 top-1/2 -translate-y-1/2 font-label-lg text-label-lg text-on-surface-variant tabular-nums">+45</span>
                      <input id="demo-phone" type="tel" inputMode="tel" autoComplete="tel" required value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })}
                        placeholder="20 30 40 50" className={`${field} pl-14 text-headline-sm font-bold tabular-nums`} />
                    </div>
                    {fieldError(error, "phone") && <p className="mt-1 font-body-sm text-body-sm text-error">Skriv et dansk telefonnummer med 8 cifre</p>}
                  </div>
                  <div className="grid sm:grid-cols-2 gap-space-sm">
                    <div>
                      <label htmlFor="demo-name" className="block font-label-md text-label-md text-on-surface-variant mb-1">Fornavn</label>
                      <input id="demo-name" autoComplete="given-name" maxLength={200} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} placeholder="Mette" className={field} />
                    </div>
                    <div>
                      <label htmlFor="demo-company" className="block font-label-md text-label-md text-on-surface-variant mb-1">Virksomhed</label>
                      <input id="demo-company" autoComplete="organization" maxLength={200} value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="Hansen VVS ApS" className={field} />
                    </div>
                  </div>
                </fieldset>

                <div aria-hidden className="absolute -left-[9999px] w-px h-px overflow-hidden">
                  <label htmlFor="demo-website">Hjemmeside</label>
                  <input id="demo-website" tabIndex={-1} autoComplete="off" value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} />
                </div>
                <label className="flex items-start gap-space-sm font-body-sm text-body-sm text-on-surface-variant">
                  <input type="checkbox" checked={f.consent} onChange={(e) => setF({ ...f, consent: e.target.checked })} className="mt-0.5 w-5 h-5 accent-primary shrink-0" />
                  <span>{info.consent_text} Læs <a href="/privatliv" className="underline text-primary">privatlivspolitikken</a>.</span>
                </label>
                {error && !fieldError(error, "phone") && <p role="alert" className="rounded-xl p-3 bg-error-container text-on-error-container font-body-sm text-body-sm">{error.message}</p>}
                {!info.available && <p role="status" className="rounded-xl p-3 bg-surface-container font-body-sm text-body-sm text-on-surface-variant">Demo-opkald åbner om lidt. Hør stemmerne her, eller skriv dig op, så ringer vi.</p>}
                <button type="submit" disabled={!info.available || pending || !f.consent || f.phone.trim().length < 8}
                  className="group w-full sm:w-auto sm:self-start inline-flex items-center justify-center gap-space-sm bg-secondary-fixed hover:bg-secondary-fixed-dim text-on-secondary-fixed font-headline-sm text-headline-sm font-bold py-4 px-10 rounded-full shadow-lg transition-all hover:-translate-y-0.5 disabled:opacity-50 disabled:hover:translate-y-0">
                  <Icon name="call" size={24} />{pending ? "Ringer op…" : `Ring mig op nu${voice ? ` med ${voice.name}` : ""}`}<Icon name="arrow_forward" size={22} className="transition-transform group-hover:translate-x-1" />
                </button>
                <p className="font-label-sm text-label-sm text-on-surface-variant -mt-space-sm">Vi ringer kl. {info.hours.from}–{info.hours.to}{info.open_now ? "" : " – prøv igen i det tidsrum"}. Kun danske numre. Gratis for dig.</p>
              </form>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
