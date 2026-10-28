"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Part } from "@/components/setup-parts";
import { SetupLater } from "@/components/setup-later";
import { Icon, inputCls } from "@/components/ui";
import { api, apiAudio, type ApiError } from "@/lib/client";
import { originOf } from "@/lib/setup";
import type { Telephony } from "@/app/app/(admin)/settings/telephony/client";

export type StandardVoice = { key: string; name: string; gender: "female" | "male"; image: string; description: string; sample: boolean };
export type VoicesData = { engine: "available" | "simulated" | "not_configured"; standard_voices: StandardVoice[]; settings: { version: number; standard_voice: string | null; standard_default: string; pronunciations: { term: string; say: string }[] } };
export type Webchat = { version: number; enabled: boolean; allowed_origins: string[]; greeting: string; embed_code: string; last_seen_at: string | null; available: boolean; unavailable_reasons: string[] };

const label = "text-[13px] font-semibold text-ink";
const btn = "inline-flex items-center justify-center gap-2 min-h-[44px] px-5 rounded-xl font-semibold disabled:opacity-60";
const primary = `${btn} bg-accent text-white hover:bg-accent-deep`;
const outline = `${btn} bg-paper text-ink border-2 border-ink hover:bg-panel`;

const msg = (e: unknown, fallback = "Det lykkedes ikke. Prøv igen.") => (e as ApiError)?.message ?? fallback;

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="px-3 py-1 rounded-full border-[1.5px] border-ink text-[12px] font-semibold uppercase tracking-[0.08em] whitespace-nowrap">{children}</span>;
}
const Err = ({ text }: { text: string | null }) => (text ? <p role="alert" className="text-[14px] text-danger">{text}</p> : null);

/* ---------------------------------------------------------------- A · Stemme */

function Voice({ wsId, data, canManage, company }: { wsId: string; data: VoicesData; canManage: boolean; company: string }) {
  const router = useRouter();
  const current = data.settings.standard_voice ?? data.settings.standard_default;
  const [chosen, setChosen] = useState(current);
  const [err, setErr] = useState<string | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const audio = useRef<HTMLAudioElement | null>(null);
  const ctrl = useRef<AbortController | null>(null);
  const stop = () => { ctrl.current?.abort(); audio.current?.pause(); setPlaying(null); };
  useEffect(() => stop, []);
  const hear = async (key: string) => {
    stop(); setErr(null);
    const c = new AbortController(); ctrl.current = c; setPlaying(key);
    try {
      const { blob } = await apiAudio(`/workspaces/${wsId}/voices/standard/${key}/sample`, {}, c.signal);
      const el = audio.current ?? new Audio(); audio.current = el;
      el.src = URL.createObjectURL(blob); el.onended = () => setPlaying(null);
      await el.play().catch(() => undefined);
    } catch (e) { if ((e as Error)?.name !== "AbortError") setErr(msg(e, "Prøven kunne ikke hentes.")); setPlaying(null); }
  };
  /** Settings are saved on top of the latest version, so two quick changes never collide. */
  const saveSettings = async (patch: Record<string, unknown>) => {
    const fresh = (await api<VoicesData>(`/workspaces/${wsId}/voices`)).settings;
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...fresh, expected_version: fresh.version, ...patch }) });
  };
  const choose = async (key: string) => {
    setChosen(key); setErr(null);
    try { await saveSettings({ standard_voice: key }); router.refresh(); } catch (e) { setErr(msg(e)); setChosen(current); }
  };
  const firstWord = company.split(/\s+/)[0] ?? "";
  const [fix, setFix] = useState<{ term: string; say: string } | null>(null);
  const [fixed, setFixed] = useState(false);
  const savePron = async () => {
    if (!fix || !fix.term.trim() || !fix.say.trim()) return;
    setErr(null);
    try {
      const fresh = (await api<VoicesData>(`/workspaces/${wsId}/voices`)).settings;
      const rest = fresh.pronunciations.filter((r) => r.term.toLowerCase() !== fix.term.trim().toLowerCase());
      await saveSettings({ pronunciations: [...rest, { term: fix.term.trim(), say: fix.say.trim() }] });
      setFixed(true); setFix(null);
    } catch (e) { setErr(msg(e)); }
  };
  return (
    <Part letter="A" title="Stemme" hint="Vælg én. Du kan altid skifte." aside={data.engine !== "available" ? <Tag>{data.engine === "simulated" ? "Prøvetone" : "Ikke klar"}</Tag> : undefined}>
      {data.engine === "simulated" && <p className="text-[13px] text-muted">Testmiljø: «Hør» afspiller en markeret prøvetone, ikke rigtig tale.</p>}
      <ul className="grid sm:grid-cols-2 gap-3" role="radiogroup" aria-label="Stemme">
        {data.standard_voices.map((v) => {
          const on = chosen === v.key;
          return (
            <li key={v.key} className={`rounded-2xl border-2 border-ink p-3 flex items-center gap-3 ${on ? "bg-highlight" : "bg-paper"}`}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={v.image} alt="" width={64} height={64} className="w-16 h-16 rounded-xl shrink-0 border-[1.5px] border-ink" />
              <div className="flex-1 min-w-0">
                <p className="font-display font-bold text-[18px] text-ink">{v.name}</p>
                <p className="text-[13px] text-ink-soft line-clamp-2">{v.description}</p>
                <div className="flex flex-wrap gap-2 mt-2">
                  {v.sample && (playing === v.key
                    ? <button type="button" onClick={stop} className={`${outline} min-h-[44px]`} aria-label={`Stop ${v.name}`}><Icon name="stop" size={16} />Stop</button>
                    : <button type="button" onClick={() => hear(v.key)} className={`${outline} min-h-[44px]`} aria-label={`Hør ${v.name}`}><Icon name="play_arrow" size={16} />Hør</button>)}
                  <button type="button" role="radio" aria-checked={on} disabled={!canManage} onClick={() => choose(v.key)} className={`${btn} min-h-[44px] border-2 border-ink ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{on ? "Valgt" : "Vælg"}</button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <Err text={err} />
      {canManage && (fix ? (
        <div className="rounded-xl border-[1.5px] border-ink p-3 flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="flex flex-col gap-1 flex-1"><span className={label}>Ordet</span><input className={inputCls} value={fix.term} onChange={(e) => setFix({ ...fix, term: e.target.value })} /></label>
          <label className="flex flex-col gap-1 flex-1"><span className={label}>Sådan skal det siges</span><input className={inputCls} value={fix.say} onChange={(e) => setFix({ ...fix, say: e.target.value })} placeholder="Skriv det, som det lyder" /></label>
          <button type="button" onClick={savePron} className={primary}>Gem</button>
        </div>
      ) : (
        <p className="text-[14px] text-ink-soft">Udtaler den «{firstWord || "firmanavnet"}» forkert?{" "}
          <button type="button" className="font-semibold text-ink underline underline-offset-2 min-h-[44px]" onClick={() => setFix({ term: firstWord, say: "" })}>Ret det</button>
          {fixed && <span className="text-success font-semibold"> · Gemt. Prøv «Hør» igen eller ring til jer selv.</span>}
        </p>
      ))}
    </Part>
  );
}

/* ---------------------------------------------------------------- B · Telefon */

const SUB = { mobile: "Mobilabonnement", landline: "Fastnet", ip_pbx: "Omstilling eller IP-telefoni", unknown: "Ved ikke" } as const;

function Phone({ wsId, t, canManage, profilePhone, company, cvr, address }: { wsId: string; t: Telephony; canManage: boolean; profilePhone: string; company: string; cvr: string; address: string }) {
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const act = async (name: string, fn: () => Promise<void>) => { setBusy(name); setErr(null); try { await fn(); router.refresh(); } catch (e) { setErr(msg(e)); } setBusy(null); };

  const [num, setNum] = useState(t.business_number ?? profilePhone);
  const [mode, setMode] = useState<string>(t.forwarding_mode === "always" ? "always" : "busy_or_no_answer");
  const [sub, setSub] = useState<string>(t.subscription_type && t.subscription_type !== "unknown" ? t.subscription_type : "mobile");
  const [code, setCode] = useState("");
  const [sent, setSent] = useState(false);
  const [doc, setDoc] = useState({ company_name: t.documents.company_name || company, cvr: t.documents.cvr ?? cvr, address: t.documents.address || address });
  const [file, setFile] = useState<File | null>(null);
  const [own, setOwn] = useState(true);
  const waiting = t.test?.status === "waiting";
  useEffect(() => {
    if (!waiting && t.status.code !== "provisioning") return;
    const id = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(id);
  }, [waiting, t.status.code, router]);

  const g = t.guide;
  const docsNeeded = t.documents.required && t.business_number && !["submitted", "approved"].includes(t.documents.status);
  const missing = t.status.missing;

  // Which single thing is next?
  let body: React.ReactNode;
  if (!t.business_number) {
    body = (
      <div className="flex flex-col gap-4">
        <div className="grid sm:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={label}>Dit nummer – det, kunderne ringer til</span><input className={inputCls} value={num} onChange={(e) => setNum(e.target.value)} inputMode="tel" placeholder="+45 12 34 56 78" disabled={!canManage} /></label>
          <label className="flex flex-col gap-1.5"><span className={label}>Hvad slags abonnement er det?</span>
            <select className={inputCls} value={sub} onChange={(e) => setSub(e.target.value)} disabled={!canManage}>{Object.entries(SUB).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select></label>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className={label}>Hvornår skal Dialogbot tage den?</legend>
          <div className="inline-flex p-1 rounded-full border-2 border-ink bg-paper self-start" role="radiogroup">
            {([["always", "Altid"], ["busy_or_no_answer", "Kun når jeg ikke tager den"]] as const).map(([k, l]) => (
              <button key={k} type="button" role="radio" aria-checked={mode === k} onClick={() => setMode(k)} disabled={!canManage} className={`min-h-[40px] px-4 rounded-full text-[14px] font-semibold ${mode === k ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>{l}</button>
            ))}
          </div>
        </fieldset>
        <p className="text-[14px] text-muted">Du beholder dit nummer og dit teleselskab. Dialogbot tager bare opkaldene, du viderestiller.</p>
        {canManage && <button type="button" className={`${primary} self-start`} disabled={!num.trim() || busy !== null} onClick={() => act("number", () => api(`/workspaces/${wsId}/telephony/business-number`, { method: "PUT", body: JSON.stringify({ e164: num, subscription_type: sub, carrier: t.carrier ?? "", forwarding_mode: mode, wants_new_number: false }) }).then(() => undefined))}>Gem nummer</button>}
      </div>
    );
  } else if (!t.verified) {
    body = (
      <div className="flex flex-col gap-3">
        <p className="text-[15px]"><b>{t.business_number}</b> – bekræft, at det er jeres. Vi ringer og læser en kode på 6 cifre op.</p>
        {canManage ? (
          <div className="flex flex-wrap items-end gap-3">
            <button type="button" className={outline} disabled={busy !== null} onClick={() => act("verify", async () => { await api(`/workspaces/${wsId}/telephony/verify`, { method: "POST" }); setSent(true); })}>{sent ? "Ring igen" : "Ring mig op med en kode"}</button>
            <label className="flex flex-col gap-1"><span className={label}>Koden</span><input className={`${inputCls} w-36`} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} autoComplete="one-time-code" /></label>
            <button type="button" className={primary} disabled={busy !== null || code.length < 6} onClick={() => act("confirm", () => api(`/workspaces/${wsId}/telephony/verify/confirm`, { method: "POST", body: JSON.stringify({ code }) }).then(() => undefined))}>Bekræft</button>
          </div>
        ) : <p className="text-[14px] text-muted">Kun ejere og administratorer kan bekræfte nummeret.</p>}
        {sent && <p className="text-[13px] text-muted">Opkaldet er på vej. Koden gælder i 10 minutter.</p>}
      </div>
    );
  } else if (docsNeeded) {
    body = (
      <div className="flex flex-col gap-3">
        <p className="text-[15px]">For at give jer et dansk nummer skal teleleverandøren kende virksomheden. Dialogbot sender oplysningerne videre – I opretter ingen konto. {t.documents.status === "rejected" && t.documents.note ? <b className="text-danger">{t.documents.note}</b> : null}</p>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1"><span className={label}>Virksomhedens navn</span><input className={inputCls} value={doc.company_name} onChange={(e) => setDoc({ ...doc, company_name: e.target.value })} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1"><span className={label}>CVR-nummer</span><input className={inputCls} value={doc.cvr} onChange={(e) => setDoc({ ...doc, cvr: e.target.value })} inputMode="numeric" maxLength={8} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1"><span className={label}>Adresse i Danmark</span><input className={inputCls} value={doc.address} onChange={(e) => setDoc({ ...doc, address: e.target.value })} disabled={!canManage} /></label>
        </div>
        <label className="flex flex-col gap-1"><span className={label}>Udskrift fra CVR-registeret (PDF, PNG eller JPG)</span><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={!canManage} className="text-[14px]" /></label>
        {canManage && <button type="button" className={`${primary} self-start`} disabled={busy !== null} onClick={() => act("docs", async () => {
          await api(`/workspaces/${wsId}/telephony/company`, { method: "PUT", body: JSON.stringify(doc) });
          if (file) {
            const r = await fetch(`/api/backend/workspaces/${wsId}/telephony/documents`, { method: "PUT", body: file, credentials: "same-origin", headers: { "content-type": file.type || "application/octet-stream", "x-requested-with": "dialogbot" } });
            if (!r.ok) throw await r.json();
          }
        })}>Send dokumentation</button>}
      </div>
    );
  } else if (!t.destination) {
    body = (
      <div className="flex flex-col gap-3">
        {t.status.code === "provisioning" ? <p className="rounded-xl bg-panel border-[1.5px] border-ink px-4 py-3 text-[14px]" role="status">{t.status.next_step}</p>
          : <p className="text-[15px]">Nummeret er bekræftet. Nu klargør Dialogbot et nummer til jer, som I viderestiller til. Det sker hos os – I opretter ingen konti.</p>}
        {missing.length > 0 && <ul className="list-disc pl-5 text-[14px]">{missing.map((m) => <li key={m.key}>{m.key === "agreement" ? <Link href="/app/konto/abonnement" className="underline font-semibold">{m.text}</Link> : m.text}</li>)}</ul>}
        {canManage && t.status.code !== "provisioning" && <button type="button" className={`${primary} self-start`} disabled={busy !== null || missing.length > 0} onClick={() => act("connect", () => api(`/workspaces/${wsId}/telephony/connect`, { method: "POST" }).then(() => undefined))}>Forbind telefonen</button>}
      </div>
    );
  } else {
    body = (
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border-[1.5px] border-ink p-4 flex flex-col gap-2">
          <span className="eyebrow">Dit nummer</span>
          <p className="font-display font-extrabold text-[28px] tracking-[-0.5px] tabular-nums text-ink">{t.business_number}</p>
          <span className="eyebrow mt-1">Hvornår skal Dialogbot tage den?</span>
          <p className="text-[15px] font-semibold text-ink">{t.forwarding_mode === "always" ? "Altid" : t.forwarding_mode === "no_answer" ? "Kun når I ikke tager den" : "Når I ikke tager den, eller linjen er optaget"}</p>
          {t.verified && <p className="text-[13px] text-success font-semibold">Nummeret er bekræftet.</p>}
        </div>
        <div className="rounded-2xl border-[1.5px] border-ink p-4 flex flex-col gap-3">
          <span className="eyebrow">Gør sådan – det tager 10 sekunder</span>
          {g.available && g.kind === "mobile_codes" ? (<>
            <p className="text-[15px] text-ink">Tast dette på din telefon og tryk ring:</p>
            <ul className="flex flex-col gap-2">{g.codes.map((c) => <li key={c.code} className="flex flex-wrap items-center gap-2"><code className="px-3 py-2 rounded-xl border-2 border-ink font-display font-extrabold text-[20px] select-all">{c.code}</code><span className="text-[13px] text-ink-soft">{c.label}</span></li>)}</ul>
            <p className="text-[13px] text-muted">Slå viderestillingen fra igen med <code className="select-all">{g.cancel_code}</code>. Koden passer til dit teleselskab. Virker det ikke? <Link href="/kontakt" className="underline font-semibold text-ink">Skriv til os</Link>, så gør vi det sammen.</p>
          </>) : g.available ? (<>
            <p className="text-[15px] text-ink">Viderestil til <b className="tabular-nums">{g.destination}</b>:</p>
            <ol className="list-decimal pl-5 text-[14px]">{g.steps.map((s) => <li key={s}>{s}</li>)}</ol>
            <p className="text-[13px] text-muted">{g.note}</p>
          </>) : null}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            {t.test?.status === "passed" ? <span className="text-[14px] text-success font-semibold">Prøveopkaldet lykkedes{t.test.simulated ? " (simuleret)" : ""}.</span>
              : waiting ? <span className="inline-flex items-center gap-2 text-[14px]" role="status"><span className="w-3 h-3 rounded-full bg-accent animate-pulse" aria-hidden />Ringer … ring nu fra en anden telefon til {t.business_number} (gælder til {new Date(t.test!.expires_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" })}).</span>
              : canManage && (<>
                <button type="button" className={primary} disabled={busy !== null} onClick={() => act("test", () => api(`/workspaces/${wsId}/telephony/tests`, { method: "POST", body: JSON.stringify({ called_business_number: own }) }).then(() => undefined))}>{t.test ? "Nyt prøveopkald" : "Start prøveopkald"}</button>
                <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className="w-5 h-5 accent-ink" checked={own} onChange={(e) => setOwn(e.target.checked)} />Jeg ringer til vores eget nummer, så viderestillingen testes.</label>
              </>)}
          </div>
          {(t.test?.status === "failed" || t.test?.status === "expired") && <p role="alert" className="text-[14px] text-danger">{t.test.reason ?? "Prøveopkaldet fejlede."}</p>}
        </div>
      </div>
    );
  }
  return (
    <Part letter="B" title="Telefon" hint="Du beholder dit nummer. Vi tager bare opkaldene." aside={<Tag>{t.status.label}</Tag>}>
      {body}
      <Err text={err} />
    </Part>
  );
}

/* ---------------------------------------------------------------- C · Webchat */

function Chat({ wsId, w, canManage, website }: { wsId: string; w: Webchat; canManage: boolean; website: string }) {
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [busy, setBusy] = useState(false);
  const origin = originOf(website);
  const turnOn = async () => {
    setBusy(true); setErr(null);
    try {
      // The allowed domain comes from the website given in trin 1; nothing else is allowed to load the chat.
      const origins = Array.from(new Set([...w.allowed_origins, ...(origin ? [origin] : [])]));
      await api(`/workspaces/${wsId}/webchat`, { method: "PUT", body: JSON.stringify({ expected_version: w.version, enabled: true, greeting: w.greeting, allowed_origins: origins }) });
      router.refresh();
    } catch (e) { setErr(msg(e)); }
    setBusy(false);
  };
  const mail = `mailto:?subject=${encodeURIComponent("Én linje til hjemmesiden")}&body=${encodeURIComponent(`Hej,\n\nKan du sætte denne ene linje ind på hjemmesiden (lige før </body>)?\n\n${w.embed_code}\n\nTak!`)}`;
  return (
    <Part letter="C" title="Webchat på hjemmesiden" hint="Valgfrit. Den samme assistent – bare som chat." aside={<Tag>{w.enabled ? (w.last_seen_at ? "Klar" : "Tændt") : "Slukket"}</Tag>}>
      {!w.enabled ? (
        <div className="flex flex-col gap-3">
          <p className="text-[15px]">{origin ? <>Chatten må kun vises på <b>{origin.replace(/^https?:\/\//, "")}</b> – adressen fra trin 1.</> : <>Giv hjemmesidens adresse i trin 1, så ved vi, hvor chatten må vises.</>}</p>
          {canManage && <button type="button" className={`${primary} self-start`} onClick={turnOn} disabled={busy || !origin}>{busy ? "Tænder …" : "Tænd webchatten"}</button>}
          {!canManage && <p className="text-[14px] text-muted">Kun ejere og administratorer kan tænde webchatten.</p>}
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          <p className="text-[15px]">Én linje skal på jeres hjemmeside. Du behøver ikke forstå den – send den til den, der passer siden.</p>
          <pre className="rounded-xl border-[1.5px] border-ink bg-panel p-3 text-[13px] overflow-x-auto whitespace-pre-wrap break-all font-mono" aria-label="Kodelinje">{w.embed_code}</pre>
          <div className="flex flex-wrap gap-2">
            <button type="button" className={outline} onClick={() => { void navigator.clipboard?.writeText(w.embed_code); setCopied(true); }}>{copied ? "Kopieret" : "Kopiér linjen"}</button>
            <a href={mail} className={outline}>Send til min webmand</a>
          </div>
          <p className="text-[13px] text-muted">{w.last_seen_at ? "Linjen er på siden – status er Klar." : "Når linjen er på siden, skifter status her til «Klar» af sig selv."}</p>
          {w.unavailable_reasons.length > 0 && <p className="text-[13px] text-muted">{w.unavailable_reasons.join(" ")}</p>}
        </div>
      )}
      <Err text={err} />
    </Part>
  );
}

/* ---------------------------------------------------------------- Tænd */

export function Step3(props: {
  wsId: string; canManage: boolean; goals: { inbound_phone: boolean; webchat: boolean; product_intent: string };
  voices: VoicesData; t: Telephony | null; webchat: Webchat | null; company: string; cvr: string; address: string; phone: string; website: string;
}) {
  const { wsId, canManage, goals, voices, t, webchat, company, cvr, address, phone, website } = props;
  const router = useRouter();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const phoneOn = goals.inbound_phone && t;
  const needs: string[] = [];
  if (phoneOn) {
    if (!t!.business_number || !t!.verified) needs.push("bekræft jeres nummer");
    else if (!t!.destination) needs.push("forbind telefonen");
    else if (t!.test?.status !== "passed" && !t!.active) needs.push("gennemfør prøveopkaldet");
    if (!t!.agreement_accepted && !t!.active) needs.push("bekræft abonnementet");
  }
  if (goals.webchat && webchat && !webchat.enabled && !phoneOn) needs.push("tænd webchatten");
  const ready = needs.length === 0;
  const alreadyOn = phoneOn ? t!.active : Boolean(webchat?.enabled);

  const turnOn = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      if (phoneOn && !t!.active) await api(`/workspaces/${wsId}/telephony/activate`, { method: "POST" });
      router.push("/app?taendt=1"); router.refresh();
    } catch (e) { setErr(msg(e)); setBusy(false); }
  }, [phoneOn, t, wsId, router]);

  return (
    <div className="flex flex-col gap-6">
      <Voice wsId={wsId} data={voices} canManage={canManage} company={company} />
      {phoneOn && <Phone wsId={wsId} t={t!} canManage={canManage} profilePhone={phone} company={company} cvr={cvr} address={address} />}
      {goals.webchat && webchat && <Chat wsId={wsId} w={webchat} canManage={canManage} website={website} />}
      {!phoneOn && !goals.webchat && <p className="rounded-2xl border-[1.5px] border-dashed border-ink px-4 py-3 text-[14px] text-ink-soft">I valgte ikke at tage telefonen eller svare på hjemmesiden i trin 1. Stemmen bruges til kampagner. <Link href="/opsaetning/1" className="underline font-semibold text-ink">Ret valget</Link></p>}

      <section className="rounded-[20px] bg-ink text-paper p-5 md:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4" aria-labelledby="taend-h">
        <div>
          <h2 id="taend-h" className="font-display font-extrabold text-[24px] leading-tight">{alreadyOn ? "Dialogbot er tændt" : ready ? "Alt er klar – tænd Dialogbot" : "Næsten klar"}</h2>
          <p className="text-[14px] text-line mt-1">{alreadyOn ? "Du kan altid pause den fra I dag." : ready ? (phoneOn ? "Prøveopkaldet lykkedes. Når du tænder, tager Dialogbot de opkald, du viderestiller." : "Når du tænder, er Dialogbot klar.") : `Mangler: ${needs.join(", ")}.`}</p>
          {err && <p role="alert" className="text-[14px] text-highlight mt-1">{err}</p>}
        </div>
        {canManage ? (
          alreadyOn ? <Link href="/app" className={`${btn} bg-highlight text-ink min-h-[52px] px-6`}>Gå til I dag</Link>
            : <button type="button" onClick={turnOn} disabled={!ready || busy} className={`${btn} bg-highlight text-ink min-h-[52px] px-6 text-[16px]`}><Icon name="power_settings_new" size={20} />{busy ? "Tænder …" : "Tænd Dialogbot"}</button>
        ) : <p className="text-[14px] text-line">Kun ejere og administratorer kan tænde.</p>}
      </section>
      {needs.includes("bekræft abonnementet") && <p className="text-[14px] text-ink-soft">Abonnementet er fra 2.495 kr./md. ekskl. moms, og udgående kampagneopkald koster 4 kr. pr. opkald ekskl. moms. <Link href="/app/konto/abonnement" className="underline font-semibold text-ink">Bekræft abonnement</Link></p>}
      <p className="text-[13px] text-muted">Du finder alt igen under profil-ikonet → Alle indstillinger. <SetupLater /></p>
    </div>
  );
}
