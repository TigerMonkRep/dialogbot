"use client";
import Link from "@/i18n/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { Part } from "@/components/setup-parts";
import { SetupLater } from "@/components/setup-later";
import { Icon, inputCls } from "@/components/ui";
import { api, apiAudio, type ApiError } from "@/lib/client";
import { originOf } from "@/lib/setup";
import { useLocale, useT } from "@/i18n/client";
import { HTML_LANG } from "@/i18n/config";
import type { Telephony } from "@/app/app/(admin)/settings/telephony/client";

export type StandardVoice = { key: string; name: string; gender: "female" | "male"; image: string; description: string; sample: boolean };
export type VoicesData = { engine: "available" | "simulated" | "not_configured"; standard_voices: StandardVoice[]; settings: { version: number; standard_voice: string | null; standard_default: string; pronunciations: { term: string; say: string }[] } };
export type Webchat = { version: number; enabled: boolean; allowed_origins: string[]; greeting: string; effective_greeting: string; embed_code: string; last_seen_at: string | null; available: boolean; unavailable_reasons: string[]; setup_missing: string[]; subscription_paid: boolean };

const label = "text-[13px] font-semibold text-ink";
const btn = "inline-flex items-center justify-center gap-2 min-h-[44px] px-5 rounded-xl font-semibold disabled:opacity-60";
const primary = `${btn} bg-accent text-white hover:bg-accent-deep`;
const outline = `${btn} bg-paper text-ink border-2 border-ink hover:bg-panel`;

const msg = (e: unknown, fallback: string) => (e as ApiError)?.message ?? fallback;

function Tag({ children }: { children: React.ReactNode }) {
  return <span className="px-3 py-1 rounded-full border-[1.5px] border-ink text-[12px] font-semibold uppercase tracking-[0.08em] whitespace-nowrap">{children}</span>;
}
const Err = ({ text }: { text: string | null }) => (text ? <p role="alert" className="text-[14px] text-danger">{text}</p> : null);

/* ---------------------------------------------------------------- A · Stemme */

export function Voice({ wsId, data, canManage, company }: { wsId: string; data: VoicesData; canManage: boolean; company: string }) {
  const router = useRouter();
  const tr = useT("setup.step3");
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
    } catch (e) { if ((e as Error)?.name !== "AbortError") setErr(msg(e, tr("voice.sampleFailed"))); setPlaying(null); }
  };
  /** Settings are saved on top of the latest version, so two quick changes never collide. */
  const saveSettings = async (patch: Record<string, unknown>) => {
    const fresh = (await api<VoicesData>(`/workspaces/${wsId}/voices`)).settings;
    await api(`/workspaces/${wsId}/voices/settings`, { method: "PUT", body: JSON.stringify({ ...fresh, expected_version: fresh.version, ...patch }) });
  };
  const choose = async (key: string) => {
    setChosen(key); setErr(null);
    try { await saveSettings({ standard_voice: key }); router.refresh(); } catch (e) { setErr(msg(e, tr("failed"))); setChosen(current); }
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
    } catch (e) { setErr(msg(e, tr("failed"))); }
  };
  return (
    <Part letter="A" title={tr("voice.title")} hint={tr("voice.hint")} aside={data.engine !== "available" ? <Tag>{data.engine === "simulated" ? tr("voice.simulatedTag") : tr("voice.notReadyTag")}</Tag> : undefined}>
      {data.engine === "simulated" && <p className="text-[13px] text-muted">{tr("voice.simulatedNote")}</p>}
      <ul className="grid sm:grid-cols-2 gap-3" role="radiogroup" aria-label={tr("voice.groupAria")}>
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
                    ? <button type="button" onClick={stop} className={`${outline} min-h-[44px]`} aria-label={tr("voice.stopAria", { name: v.name })}><Icon name="stop" size={16} />{tr("voice.stop")}</button>
                    : <button type="button" onClick={() => hear(v.key)} className={`${outline} min-h-[44px]`} aria-label={tr("voice.hearAria", { name: v.name })}><Icon name="play_arrow" size={16} />{tr("voice.hear")}</button>)}
                  <button type="button" role="radio" aria-checked={on} disabled={!canManage} onClick={() => choose(v.key)} className={`${btn} min-h-[44px] border-2 border-ink ${on ? "bg-ink text-paper" : "bg-paper text-ink hover:bg-panel"}`}>{on ? tr("voice.chosen") : tr("voice.choose")}</button>
                </div>
              </div>
            </li>
          );
        })}
      </ul>
      <Err text={err} />
      {canManage && (fix ? (
        <div className="rounded-xl border-[1.5px] border-ink p-3 flex flex-col sm:flex-row sm:items-end gap-3">
          <label className="flex flex-col gap-1 flex-1"><span className={label}>{tr("voice.word")}</span><input className={inputCls} value={fix.term} onChange={(e) => setFix({ ...fix, term: e.target.value })} /></label>
          <label className="flex flex-col gap-1 flex-1"><span className={label}>{tr("voice.say")}</span><input className={inputCls} value={fix.say} onChange={(e) => setFix({ ...fix, say: e.target.value })} placeholder={tr("voice.sayPlaceholder")} /></label>
          <button type="button" onClick={savePron} className={primary}>{tr("voice.save")}</button>
        </div>
      ) : (
        <p className="text-[14px] text-ink-soft">{tr("voice.mispronounced", { word: firstWord || tr("voice.companyName") })}{" "}
          <button type="button" className="font-semibold text-ink underline underline-offset-2 min-h-[44px]" onClick={() => setFix({ term: firstWord, say: "" })}>{tr("voice.fixIt")}</button>
          {fixed && <span className="text-success font-semibold">{tr("voice.fixed")}</span>}
        </p>
      ))}
    </Part>
  );
}

/* ---------------------------------------------------------------- B · Telefon */

const SUB = ["mobile", "landline", "ip_pbx", "unknown"] as const;

export function Phone({ wsId, t, canManage, profilePhone, company, cvr, address }: { wsId: string; t: Telephony; canManage: boolean; profilePhone: string; company: string; cvr: string; address: string }) {
  const router = useRouter();
  const tr = useT("setup.step3");
  const locale = useLocale();
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const act = async (name: string, fn: () => Promise<void>) => { setBusy(name); setErr(null); try { await fn(); router.refresh(); } catch (e) { setErr(msg(e, tr("failed"))); } setBusy(null); };

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
          <label className="flex flex-col gap-1.5"><span className={label}>{tr("phone.yourNumber")}</span><input className={inputCls} value={num} onChange={(e) => setNum(e.target.value)} inputMode="tel" placeholder={tr("phone.numberPlaceholder")} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1.5"><span className={label}>{tr("phone.subscription")}</span>
            <select className={inputCls} value={sub} onChange={(e) => setSub(e.target.value)} disabled={!canManage}>{SUB.map((k) => <option key={k} value={k}>{tr(`phone.sub.${k}`)}</option>)}</select></label>
        </div>
        <fieldset className="flex flex-col gap-2">
          <legend className={label}>{tr("phone.when")}</legend>
          <div className="inline-flex p-1 rounded-full border-2 border-ink bg-paper self-start" role="radiogroup">
            {([["always", tr("phone.always")], ["busy_or_no_answer", tr("phone.whenNotAnswering")]] as const).map(([k, l]) => (
              <button key={k} type="button" role="radio" aria-checked={mode === k} onClick={() => setMode(k)} disabled={!canManage} className={`min-h-[40px] px-4 rounded-full text-[14px] font-semibold ${mode === k ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>{l}</button>
            ))}
          </div>
        </fieldset>
        <p className="text-[14px] text-muted">{tr("phone.keepNumber")}</p>
        {canManage && <button type="button" className={`${primary} self-start`} disabled={!num.trim() || busy !== null} onClick={() => act("number", () => api(`/workspaces/${wsId}/telephony/business-number`, { method: "PUT", body: JSON.stringify({ e164: num, subscription_type: sub, carrier: t.carrier ?? "", forwarding_mode: mode, wants_new_number: false }) }).then(() => undefined))}>{tr("phone.saveNumber")}</button>}
      </div>
    );
  } else if (!t.verified) {
    body = (
      <div className="flex flex-col gap-3">
        <p className="text-[15px]"><b>{t.business_number}</b>{tr("phone.confirmIntro")}</p>
        {canManage ? (
          <div className="flex flex-wrap items-end gap-3">
            <button type="button" className={outline} disabled={busy !== null} onClick={() => act("verify", async () => { await api(`/workspaces/${wsId}/telephony/verify`, { method: "POST" }); setSent(true); })}>{sent ? tr("phone.callAgain") : tr("phone.callMe")}</button>
            <label className="flex flex-col gap-1"><span className={label}>{tr("phone.code")}</span><input className={`${inputCls} w-36`} value={code} onChange={(e) => setCode(e.target.value)} inputMode="numeric" maxLength={6} autoComplete="one-time-code" /></label>
            <button type="button" className={primary} disabled={busy !== null || code.length < 6} onClick={() => act("confirm", () => api(`/workspaces/${wsId}/telephony/verify/confirm`, { method: "POST", body: JSON.stringify({ code }) }).then(() => undefined))}>{tr("phone.confirm")}</button>
          </div>
        ) : <p className="text-[14px] text-muted">{tr("phone.confirmManagersOnly")}</p>}
        {sent && <p className="text-[13px] text-muted">{tr("phone.callOnWay")}</p>}
      </div>
    );
  } else if (docsNeeded) {
    body = (
      <div className="flex flex-col gap-3">
        <p className="text-[15px]">{tr("phone.docsIntro")} {t.documents.status === "rejected" && t.documents.note ? <b className="text-danger">{t.documents.note}</b> : null}</p>
        <div className="grid sm:grid-cols-3 gap-3">
          <label className="flex flex-col gap-1"><span className={label}>{tr("phone.companyName")}</span><input className={inputCls} value={doc.company_name} onChange={(e) => setDoc({ ...doc, company_name: e.target.value })} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1"><span className={label}>{tr("phone.cvr")}</span><input className={inputCls} value={doc.cvr} onChange={(e) => setDoc({ ...doc, cvr: e.target.value })} inputMode="numeric" maxLength={8} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1"><span className={label}>{tr("phone.address")}</span><input className={inputCls} value={doc.address} onChange={(e) => setDoc({ ...doc, address: e.target.value })} disabled={!canManage} /></label>
        </div>
        <label className="flex flex-col gap-1"><span className={label}>{tr("phone.cvrExtract")}</span><input type="file" accept="application/pdf,image/png,image/jpeg" onChange={(e) => setFile(e.target.files?.[0] ?? null)} disabled={!canManage} className="text-[14px]" /></label>
        {canManage && <button type="button" className={`${primary} self-start`} disabled={busy !== null} onClick={() => act("docs", async () => {
          await api(`/workspaces/${wsId}/telephony/company`, { method: "PUT", body: JSON.stringify(doc) });
          if (file) {
            const r = await fetch(`/api/backend/workspaces/${wsId}/telephony/documents`, { method: "PUT", body: file, credentials: "same-origin", headers: { "content-type": file.type || "application/octet-stream", "x-requested-with": "dialogbot" } });
            if (!r.ok) throw await r.json();
          }
        })}>{tr("phone.sendDocs")}</button>}
      </div>
    );
  } else if (!t.destination) {
    body = (
      <div className="flex flex-col gap-3">
        {t.status.code === "provisioning" ? <p className="rounded-xl bg-panel border-[1.5px] border-ink px-4 py-3 text-[14px]" role="status">{t.status.next_step}</p>
          : <p className="text-[15px]">{tr("phone.verifiedIntro")}</p>}
        {missing.length > 0 && <ul className="list-disc pl-5 text-[14px]">{missing.map((m) => <li key={m.key}>{m.key === "agreement" ? <Link href="/opsaetning/betaling" className="underline font-semibold">{m.text}</Link> : m.text}</li>)}</ul>}
        {canManage && t.status.code !== "provisioning" && <button type="button" className={`${primary} self-start`} disabled={busy !== null || missing.length > 0} onClick={() => act("connect", () => api(`/workspaces/${wsId}/telephony/connect`, { method: "POST" }).then(() => undefined))}>{tr("phone.connect")}</button>}
      </div>
    );
  } else {
    body = (
      <div className="grid lg:grid-cols-2 gap-4">
        <div className="rounded-2xl border-[1.5px] border-ink p-4 flex flex-col gap-2">
          <span className="eyebrow">{tr("phone.numberEyebrow")}</span>
          <p className="font-display font-extrabold text-[28px] tracking-[-0.5px] tabular-nums text-ink">{t.business_number}</p>
          <span className="eyebrow mt-1">{tr("phone.when")}</span>
          <p className="text-[15px] font-semibold text-ink">{t.forwarding_mode === "always" ? tr("phone.always") : t.forwarding_mode === "no_answer" ? tr("phone.modeNoAnswer") : tr("phone.modeBusy")}</p>
          {t.verified && <p className="text-[13px] text-success font-semibold">{tr("phone.verified")}</p>}
        </div>
        <div className="rounded-2xl border-[1.5px] border-ink p-4 flex flex-col gap-3">
          <span className="eyebrow">{tr("phone.howTo")}</span>
          {g.available && g.kind === "mobile_codes" ? (<>
            <p className="text-[15px] text-ink">{tr("phone.dial")}</p>
            <ul className="flex flex-col gap-2">{g.codes.map((c) => <li key={c.code} className="flex flex-wrap items-center gap-2"><code className="px-3 py-2 rounded-xl border-2 border-ink font-display font-extrabold text-[20px] select-all">{c.code}</code><span className="text-[13px] text-ink-soft">{c.label}</span></li>)}</ul>
            <p className="text-[13px] text-muted">{tr("phone.cancelBefore")}<code className="select-all">{g.cancel_code}</code>{tr("phone.cancelAfter")}<Link href="/kontakt" className="underline font-semibold text-ink">{tr("phone.writeUs")}</Link>{tr("phone.together")}</p>
          </>) : g.available ? (<>
            <p className="text-[15px] text-ink">{tr("phone.forwardTo")}<b className="tabular-nums">{g.destination}</b>:</p>
            <ol className="list-decimal pl-5 text-[14px]">{g.steps.map((s) => <li key={s}>{s}</li>)}</ol>
            <p className="text-[13px] text-muted">{g.note}</p>
          </>) : null}
          <div className="flex flex-wrap items-center gap-3 pt-1">
            {t.test?.status === "passed" ? <span className="text-[14px] text-success font-semibold">{tr("phone.testPassed", { simulated: t.test.simulated ? tr("phone.simulated") : "" })}</span>
              : waiting ? <span className="inline-flex items-center gap-2 text-[14px]" role="status"><span className="w-3 h-3 rounded-full bg-accent animate-pulse" aria-hidden />{tr("phone.calling", { number: t.business_number ?? "", time: new Date(t.test!.expires_at).toLocaleTimeString(HTML_LANG[locale], { hour: "2-digit", minute: "2-digit" }) })}</span>
              : canManage && (<>
                <button type="button" className={primary} disabled={busy !== null} onClick={() => act("test", () => api(`/workspaces/${wsId}/telephony/tests`, { method: "POST", body: JSON.stringify({ called_business_number: own }) }).then(() => undefined))}>{t.test ? tr("phone.newTest") : tr("phone.startTest")}</button>
                <label className="flex items-center gap-2 text-[13px]"><input type="checkbox" className="w-5 h-5 accent-ink" checked={own} onChange={(e) => setOwn(e.target.checked)} />{tr("phone.ownNumber")}</label>
              </>)}
          </div>
          {(t.test?.status === "failed" || t.test?.status === "expired") && <p role="alert" className="text-[14px] text-danger">{t.test.reason ?? tr("phone.testFailed")}</p>}
        </div>
      </div>
    );
  }
  return (
    <Part letter="B" title={tr("phone.title")} hint={tr("phone.hint")} aside={<Tag>{t.status.label}</Tag>}>
      {body}
      <Err text={err} />
    </Part>
  );
}


/* ---------------------------------------------------------------- Chat: widget, udseende, kode, forhåndsvisning */

const CHAT_REASONS = ["no_approved_knowledge", "no_allowed_origins", "ai_not_configured"];

/** The website chat, set up before it is paid: where it may be shown, how it greets, the one line for the website and a
 *  preview where the owner tries it. Visitors get no chat until the subscription is in place (the backend refuses them);
 *  once paid it is switched on here or under Betaling. */
export function ChatSetup({ wsId, w, canManage, website, company, onDirty }: { wsId: string; w: Webchat; canManage: boolean; website: string; company: string; onDirty?: (save: (() => Promise<boolean>) | null) => void }) {
  const router = useRouter();
  const tr = useT("setup.chat");
  const [origin, setOrigin] = useState((w.allowed_origins[0] ?? originOf(website) ?? "").replace(/\/$/, ""));
  const [greeting, setGreeting] = useState(w.greeting);
  const [err, setErr] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [copied, setCopied] = useState(false);
  const ver = useRef(w.version);
  const dirty = origin !== (w.allowed_origins[0] ?? originOf(website) ?? "").replace(/\/$/, "") || greeting !== w.greeting || (!w.allowed_origins.length && Boolean(origin));
  const save = useCallback(async (enabled = w.enabled): Promise<boolean> => {
    setBusy(true); setErr(null); setSaved(false);
    try {
      const o = origin.trim();
      const origins = o ? [/^https?:\/\//.test(o) ? o : `https://${o}`] : [];
      const r = await api<Webchat>(`/workspaces/${wsId}/webchat`, { method: "PUT", body: JSON.stringify({ expected_version: ver.current, enabled, greeting: greeting.trim(), allowed_origins: origins }) });
      ver.current = r.version; setSaved(true); router.refresh(); setBusy(false);
      return true;
    } catch (e) {
      const x = e as ApiError & { reasons?: string[] };
      const reasons = (x.reasons ?? []).filter((r) => CHAT_REASONS.includes(r));
      setErr(x.code === "subscription_required" ? tr("liveWhenPaid") : reasons.length ? reasons.map((r) => tr(`missing.${r}`)).join(" ") : msg(e, tr("saveFailed")));
      setBusy(false);
      return false;
    }
  }, [wsId, origin, greeting, w.enabled, router, tr]);
  useEffect(() => { onDirty?.(dirty && canManage ? () => save() : null); }, [dirty, canManage, save, onDirty]);
  const mail = `mailto:?subject=${encodeURIComponent(tr("mailSubject"))}&body=${encodeURIComponent(tr("mailBody", { code: w.embed_code }))}`;
  const missing = w.setup_missing.filter((r) => CHAT_REASONS.includes(r));
  const live = w.enabled && w.available;
  return (
    <div className="flex flex-col gap-6">
      <Part letter="A" title={tr("widget.title")} hint={tr("widget.hint")} aside={<Tag>{live ? tr("live") : w.enabled ? tr("onNotLive") : tr("notLive")}</Tag>}>
        <div className="grid md:grid-cols-2 gap-4">
          <label className="flex flex-col gap-1.5"><span className={label}>{tr("widget.domain")}</span>
            <input className={inputCls} value={origin} onChange={(e) => setOrigin(e.target.value)} inputMode="url" autoCapitalize="none" placeholder={tr("widget.domainPlaceholder")} disabled={!canManage} /></label>
          <label className="flex flex-col gap-1.5"><span className={label}>{tr("look.greeting")}</span>
            <input className={inputCls} value={greeting} maxLength={300} onChange={(e) => setGreeting(e.target.value)} placeholder={w.effective_greeting} disabled={!canManage} /></label>
        </div>
        {/* Udseende: how the chat opens on the website – the same frame, the same greeting. */}
        <div className="flex flex-col gap-2" aria-label={tr("look.previewAria")} role="img">
          <span className="eyebrow">{tr("look.title")}</span>
          <div className="w-full max-w-[340px] rounded-2xl border-2 border-ink bg-paper overflow-hidden">
            <div className="bg-ink text-paper px-4 py-2.5 font-display font-bold text-[15px]">{tr("look.header", { name: company })}</div>
            <div className="p-3"><p className="inline-block max-w-[85%] rounded-xl bg-panel px-3 py-2 text-[14px] text-ink">{greeting.trim() || w.effective_greeting}</p></div>
          </div>
        </div>
        {canManage && <div className="flex flex-wrap items-center gap-3">
          <button type="button" className={outline} disabled={busy || !dirty} onClick={() => void save()}>{busy ? tr("saving") : tr("save")}</button>
          {saved && !dirty && <span role="status" className="text-[14px] text-success font-semibold">{tr("saved")}</span>}
        </div>}
        {missing.length > 0 && <ul className="list-disc pl-5 text-[14px] text-ink">{missing.map((r) => <li key={r}>{r === "no_approved_knowledge" ? <Link href="/opsaetning/viden" className="underline font-semibold">{tr(`missing.${r}`)}</Link> : tr(`missing.${r}`)}</li>)}</ul>}
        <Err text={err} />
      </Part>

      <Part letter="B" title={tr("code.title")} hint={tr("code.hint")}>
        <pre className="rounded-xl border-[1.5px] border-ink bg-panel p-3 text-[13px] overflow-x-auto whitespace-pre-wrap break-all font-mono" aria-label={tr("code.aria")}>{w.embed_code}</pre>
        <div className="flex flex-wrap gap-2">
          <button type="button" className={outline} onClick={() => { void navigator.clipboard?.writeText(w.embed_code); setCopied(true); }}>{copied ? tr("code.copied") : tr("code.copy")}</button>
          <a href={mail} className={outline}>{tr("code.sendWebmaster")}</a>
        </div>
        <p className="text-[13px] text-muted">{w.last_seen_at ? tr("code.seen") : tr("code.notSeen")}</p>
      </Part>

      <Part letter="C" title={tr("preview.title")} hint={tr("preview.hint")}>
        <ChatPreview wsId={wsId} greeting={greeting.trim() || w.effective_greeting} canManage={canManage} />
      </Part>

      <ChatLiveNote wsId={wsId} w={w} canManage={canManage} missing={missing.length > 0} />
    </div>
  );
}

/** «Chatten går live, når abonnementet er på plads» – or, paid: switch it on here. */
function ChatLiveNote({ wsId, w, canManage, missing }: { wsId: string; w: Webchat; canManage: boolean; missing: boolean }) {
  const router = useRouter();
  const tr = useT("setup.chat");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (w.enabled && w.available) return <p role="status" className="rounded-2xl bg-success-soft px-4 py-3 text-[15px] font-semibold text-success">{tr("isLive")}</p>;
  if (!w.subscription_paid) {
    return (
      <p className="rounded-2xl border-2 border-ink bg-highlight px-4 py-3 text-[15px] text-ink" data-testid="chat-live-when-paid">
        <b>{tr("liveWhenPaid")}</b>{" "}<Link href="/opsaetning/betaling" className="underline font-semibold">{tr("toPayment")}</Link>
      </p>
    );
  }
  const turnOn = async () => {
    setBusy(true); setErr(null);
    try { await api(`/workspaces/${wsId}/webchat`, { method: "PUT", body: JSON.stringify({ expected_version: w.version, enabled: true, greeting: w.greeting, allowed_origins: w.allowed_origins }) }); router.refresh(); }
    catch (e) { setErr(msg(e, tr("saveFailed"))); }
    setBusy(false);
  };
  return (
    <div className="flex flex-col gap-2 rounded-2xl border-2 border-ink bg-paper px-4 py-3">
      <p className="text-[15px] text-ink">{tr("paidTurnOn")}</p>
      {canManage && <button type="button" className={`${primary} self-start`} onClick={turnOn} disabled={busy || missing}>{busy ? tr("turningOn") : tr("turnOn")}</button>}
      <Err text={err} />
    </div>
  );
}

type Turn = { role: "user" | "assistant"; content: string };

/** The owner tries the chat in the app – the same assistant and approved knowledge; nothing is stored, no visitor sees it. */
export function ChatPreview({ wsId, greeting, canManage }: { wsId: string; greeting: string; canManage: boolean }) {
  const tr = useT("setup.chat");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const send = async (e: React.FormEvent) => {
    e.preventDefault();
    const q = text.trim();
    if (!q || busy) return;
    const next = [...turns, { role: "user" as const, content: q }];
    setTurns(next); setText(""); setBusy(true); setErr(null);
    try {
      const r = await api<{ reply: string }>(`/workspaces/${wsId}/webchat/preview`, { method: "POST", body: JSON.stringify({ messages: next.slice(-12) }) });
      setTurns([...next, { role: "assistant", content: r.reply }]);
    } catch (x) { setErr(msg(x, tr("preview.failed"))); }
    setBusy(false);
  };
  return (
    <div className="flex flex-col gap-3 max-w-[560px]" data-testid="chat-preview">
      <span className="self-start px-3 py-1 rounded-full border-[1.5px] border-ink bg-highlight text-[12px] font-semibold uppercase tracking-[0.08em]">{tr("preview.onlyYou")}</span>
      <ol className="flex flex-col gap-2 rounded-xl border-[1.5px] border-ink bg-panel p-3 min-h-[120px]" aria-live="polite" aria-label={tr("preview.aria")}>
        <li className="self-start max-w-[85%] rounded-xl bg-paper px-3 py-2 text-[14px]">{greeting}</li>
        {turns.map((m, i) => <li key={i} className={`max-w-[85%] rounded-xl px-3 py-2 text-[14px] ${m.role === "user" ? "self-end bg-ink text-paper" : "self-start bg-paper text-ink"}`}>{m.content}</li>)}
        {busy && <li className="self-start text-[13px] text-muted">{tr("preview.thinking")}</li>}
      </ol>
      {canManage ? (
        <form className="flex gap-2" onSubmit={send}>
          <label htmlFor="chat-preview-input" className="sr-only">{tr("preview.input")}</label>
          <input id="chat-preview-input" className={`${inputCls} flex-1 min-w-0`} value={text} maxLength={1000} onChange={(e) => setText(e.target.value)} placeholder={tr("preview.placeholder")} />
          <button type="submit" className={primary} disabled={busy || !text.trim()}>{tr("preview.send")}</button>
        </form>
      ) : <p className="text-[14px] text-muted">{tr("managersOnly")}</p>}
      <Err text={err} />
    </div>
  );
}

/* ---------------------------------------------------------------- Gå live (Betaling) */

/** The last thing in Betaling: once the subscription is paid, the chosen channels go live – the phone after its test call,
 *  the website chat at once. Before that it says plainly that it goes live when the subscription is in place. */
export function GoLive(props: {
  wsId: string; canManage: boolean; reader?: boolean; paid: boolean; goals: { inbound_phone: boolean; webchat: boolean; product_intent: string };
  t: Telephony | null; webchat: Webchat | null; company: string; cvr: string; address: string; phone: string;
}) {
  const { wsId, canManage, reader = false, paid, goals, t, webchat, company, cvr, address, phone } = props;
  const router = useRouter();
  const tr = useT("setup.step3");
  const tc = useT("setup.betaling");
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const phoneOn = goals.inbound_phone && t;
  const chatOn = goals.webchat && webchat;
  const needs: string[] = [];
  if (phoneOn) {
    if (!t!.business_number || !t!.verified) needs.push(tr("needs.confirmNumber"));
    else if (!t!.destination) needs.push(tr("needs.connectPhone"));
    else if (t!.test?.status !== "passed" && !t!.active) needs.push(tr("needs.testCall"));
  }
  if (chatOn && webchat!.setup_missing.length > 0) needs.push(tc("needs.chat"));
  const ready = needs.length === 0;
  const noChannel = !goals.inbound_phone && !goals.webchat;
  const outbound = goals.product_intent !== "reception";
  const alreadyOn = (!phoneOn || t!.active) && (!chatOn || (webchat!.enabled && webchat!.available)) && !noChannel;

  const goLive = useCallback(async () => {
    setBusy(true); setErr(null);
    try {
      if (phoneOn && !t!.active) await api(`/workspaces/${wsId}/telephony/activate`, { method: "POST" });
      if (chatOn && !webchat!.enabled) await api(`/workspaces/${wsId}/webchat`, { method: "PUT", body: JSON.stringify({ expected_version: webchat!.version, enabled: true, greeting: webchat!.greeting, allowed_origins: webchat!.allowed_origins }) });
      router.push("/app?taendt=1"); router.refresh();
    } catch (e) { setErr(msg(e, tr("failed"))); setBusy(false); }
  }, [phoneOn, chatOn, t, webchat, wsId, router, tr]);

  if (noChannel) {
    return (
      <section className="rounded-[20px] bg-ink text-paper p-5 md:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4" aria-labelledby="live-h">
        <div>
          <h2 id="live-h" className="font-display font-extrabold text-[24px] leading-tight">{outbound ? tr("campaignsTitle") : tr("nothingTitle")}</h2>
          <p className="text-[14px] text-line mt-1">{outbound ? tr("campaignsText") : tc("nothingText")}</p>
        </div>
        {outbound
          ? <Link href="/app/kampagner" className={`${btn} bg-highlight text-ink min-h-[52px] px-6 text-[16px]`}>{tr("campaignsCta")}</Link>
          : <Link href="/opsaetning/virksomhed" className={`${btn} bg-highlight text-ink min-h-[52px] px-6 text-[16px]`}>{tr("changeChoice")}</Link>}
      </section>
    );
  }
  const whenPaid = goals.webchat && goals.inbound_phone ? tc("liveWhenPaidBoth") : goals.webchat ? tc("liveWhenPaidChat") : tc("liveWhenPaidPhone");
  return (
    <div className="flex flex-col gap-4">
      {/* Paid: the phone's next single thing (connect the Dialogbot number, the test call) is done right here. */}
      {paid && phoneOn && !t!.active && <Phone wsId={wsId} t={t!} canManage={canManage} profilePhone={phone} company={company} cvr={cvr} address={address} />}
      {paid && chatOn && webchat!.setup_missing.length > 0 && <p className="text-[14px] text-ink">{tc("needs.chat")} <Link href="/opsaetning/chat" className="underline font-semibold">{tc("toChat")}</Link></p>}
      <section className="rounded-[20px] bg-ink text-paper p-5 md:p-6 flex flex-col sm:flex-row sm:items-center justify-between gap-4" aria-labelledby="live-h">
        <div>
          <h2 id="live-h" className="font-display font-extrabold text-[24px] leading-tight">{reader ? tr("readerTitle") : alreadyOn && paid ? tr("isOn") : !paid ? tc("notYet") : ready ? tc("allReady") : tr("almost")}</h2>
          {!reader && <p className="text-[14px] text-line mt-1">{!paid ? whenPaid : alreadyOn ? tr("pauseNote") : ready ? (phoneOn ? tr("readyPhone") : tr("readyNoPhone")) : tr("missing", { list: needs.join(", ") })}</p>}
          {err && <p role="alert" className="text-[14px] text-highlight mt-1">{err}</p>}
        </div>
        {canManage ? (
          alreadyOn && paid ? <Link href="/app" className={`${btn} bg-highlight text-ink min-h-[52px] px-6`}>{tr("goToday")}</Link>
            : <button type="button" onClick={goLive} disabled={!paid || !ready || busy} className={`${btn} bg-highlight text-ink min-h-[52px] px-6 text-[16px]`}><Icon name="power_settings_new" size={20} />{busy ? tr("turningOn") : tc("goLive")}</button>
        ) : <p className="text-[14px] text-line">{tr("managersOnly")}</p>}
      </section>
    </div>
  );
}
