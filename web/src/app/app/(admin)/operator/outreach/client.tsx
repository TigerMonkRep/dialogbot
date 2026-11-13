"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Input, Select, Textarea } from "@/components/ui";

export type Todo = { key: string; title: string; how: string; done: boolean; kind: "auto" | "manual"; needed_for: "dry_run" | "live" | "optional"; done_at?: string | null };
export type Market = { code: string; name: string; tier: number; state: "email" | "call_list" | "hold" | "blocked"; regime: string; rules: string; price: string | null; demo_available: boolean };
export type Batch = { name: string; created_at: string; leads: number; totals: Record<string, number> };
export type Overview = {
  mode: "off" | "dry_run" | "live"; ready_for_dry_run: boolean; ready_for_live: boolean; open_todos: number; todos: Todo[];
  markets: Market[]; niches: { key: string; label: string }[]; search_available: boolean; batches: Batch[];
  stats: { leads: Record<string, number>; queued: number; sent_today: number; daily_capacity: number; suppressed: number; call_list_open: number; call_list_review: number };
};
type Draft = { status: string; subject: string; body: string; footer: string; words: number; rendered: string | null; sender_inbox: string | null; audit: { passed?: boolean; issues?: string[] } };
export type BatchReport = {
  batch: string; mode: string; totals: Record<string, number>; tokens: { input_tokens: number; output_tokens: number };
  leads: { company: string; email: string; country: string; niche: string | null; status: string; compliance: { reasons?: string[] }; confidence: number | null; hook: string | null; email_draft: Draft | null; call_queue: { scrub_status: string } | null }[];
};
type Candidate = { company_name: string; country: string; city: string | null; niche: string; website: string | null; phone: string | null; email: string | null; email_source: string; email_source_url: string | null; context: string | null; problem: string | null };

const MODE: Record<Overview["mode"], [string, string, string]> = {
  off: ["Slukket", "bg-paper text-muted border-[1.5px] border-line", "Intet kører. Følg første punkt under «Inden du går live» for at tænde."],
  dry_run: ["Tørkørsel", "bg-highlight text-ink", "Alt bliver tjekket, researchet, skrevet og kontrolleret – men intet sendes."],
  live: ["Live", "bg-success-soft text-success", "E-mails i køen sendes, når du trykker «Send køen nu»."],
};
/** Lead status → [label, badge colours] */
const STATUS: Record<string, [string, string]> = {
  qualified: ["Klar til research", "bg-highlight text-ink"], queued: ["E-mail klar", "bg-success-soft text-success"],
  sent: ["Sendt", "bg-success-soft text-success"], blocked: ["Blokeret", "bg-danger-soft text-danger"],
  held: ["Afventer jurist", "bg-paper text-muted border-[1.5px] border-line"], call_queue: ["På ringelisten", "bg-accent text-white"],
  disqualified: ["Sorteret fra", "bg-paper text-muted border-[1.5px] border-line"], low_confidence: ["For lidt at skrive om", "bg-paper text-muted border-[1.5px] border-line"],
  audit_failed: ["E-mail afvist i kontrol", "bg-danger-soft text-danger"], replied: ["Har svaret", "bg-accent text-white"],
  bounced: ["Afvist af modtager", "bg-danger-soft text-danger"], unsubscribed: ["Frameldt", "bg-paper text-muted border-[1.5px] border-line"],
  error: ["Fejl – prøv igen", "bg-danger-soft text-danger"], researched: ["Researchet", "bg-highlight text-ink"], new: ["Ny", "bg-highlight text-ink"],
};
const MARKET: Record<Market["state"], string> = { email: "E-mail tilladt", call_list: "Kun ringeliste", hold: "Afventer jurist", blocked: "Blokeret" };
const card = "rounded-2xl bg-paper border-2 border-ink p-space-md flex flex-col gap-3";
const btn = "min-h-[46px] px-5 rounded-xl text-[14px] font-semibold disabled:opacity-50";
const badge = "inline-flex px-2.5 py-0.5 rounded-full text-[12px] font-semibold whitespace-nowrap";
const label = "flex flex-col gap-1 text-[13px] font-semibold text-ink";
const errText = (e: unknown) => (e as ApiError).message ?? "Noget gik galt – prøv igen.";
const slug = (s: string) => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 28);
const tail = () => Date.now().toString(36).slice(-5);

export function Outreach({ data, report }: { data: Overview; report: BatchReport | null }) {
  const [mLabel, mCls, mText] = MODE[data.mode];
  const s = data.stats;
  const figures: [string, string | number][] = [
    ["E-mails klar i køen", s.queued], ["Sendt i dag", data.mode === "live" ? `${s.sent_today} af ${s.daily_capacity}` : 0],
    ["Frameldte og afviste", s.suppressed], ["På ringelisten (DK)", s.call_list_open], ["Mangler før live", data.open_todos],
  ];
  return (
    <div className="flex flex-col gap-space-lg">
      <section aria-label="Status" className={card}>
        <div className="flex flex-wrap items-center gap-3">
          <span className={`${badge} text-[14px] px-3.5 py-1 ${mCls}`}>{mLabel}</span>
          <p className="m-0 text-[15px] text-ink">{mText}</p>
        </div>
        <dl className="grid grid-cols-2 md:grid-cols-5 gap-3 m-0">
          {figures.map(([k, v]) => (
            <div key={k} className="rounded-xl bg-panel border-[1.5px] border-ink px-3 py-2">
              <dt className="text-[12px] text-muted">{k}</dt>
              <dd className="m-0 font-display font-extrabold text-[22px] text-ink tabular-nums">
                {k === "Mangler før live" && data.open_todos > 0 ? <a href="#todo-h" className="underline">{v}</a> : v}
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <Starter data={data} />
      <Batches data={data} active={report?.batch ?? ""} />
      {report && <BatchDetail report={report} mode={data.mode} queued={s.queued} />}
      <Todos todos={data.todos} readyLive={data.ready_for_live} />
      <CallList open={s.call_list_open} review={s.call_list_review} off={data.mode === "off"} />
      <Markets markets={data.markets} />
    </div>
  );
}

/* ------------------------------------------------------------------ the go-live list */

function Todos({ todos, readyLive }: { todos: Todo[]; readyLive: boolean }) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const tick = async (t: Todo) => {
    setBusy(t.key); setErr("");
    try { await api(`/operator/outreach/todos/${t.key}`, { method: "PUT", body: JSON.stringify({ done: !t.done }) }); router.refresh(); }
    catch (e) { setErr(errText(e)); }
    setBusy("");
  };
  const groups: [string, Todo[]][] = [
    ["For at prøve det af (tørkørsel)", todos.filter((t) => t.needed_for === "dry_run")],
    ["Før der må sendes rigtigt", todos.filter((t) => t.needed_for === "live")],
    ["Valgfrit", todos.filter((t) => t.needed_for === "optional")],
  ];
  const left = todos.filter((t) => !t.done && t.needed_for !== "optional").length;
  return (
    <section aria-labelledby="todo-h" className={card}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="todo-h" className="scroll-mt-4 font-display font-extrabold text-[22px] text-ink m-0">Inden du går live</h2>
        <span className={`${badge} ${left ? "bg-highlight text-ink" : "bg-success-soft text-success"}`}>{left ? `${left} punkt${left === 1 ? "" : "er"} mangler` : "Alt er på plads"}</span>
      </div>
      <p className="m-0 text-[14px] text-muted">Grønne punkter er tjekket automatisk i opsætningen. Punkter med en knap hakker du selv af, når de er gjort.{readyLive ? "" : " Systemet sender ikke rigtigt, før de røde er løst."}</p>
      {groups.filter(([, list]) => list.length > 0).map(([title, list]) => (
        <div key={title} className="flex flex-col gap-2">
          <h3 className="eyebrow m-0">{title}</h3>
          <ol className="m-0 p-0 list-none flex flex-col gap-2">
            {list.map((t) => (
              <li key={t.key} className={`rounded-xl border-[1.5px] px-3.5 py-3 flex flex-wrap items-start gap-3 ${t.done ? "border-line bg-panel" : "border-ink bg-paper"}`}>
                <span aria-hidden className={`mt-0.5 inline-flex items-center justify-center w-6 h-6 rounded-full text-[13px] font-bold shrink-0 ${t.done ? "bg-success-soft text-success" : t.needed_for === "optional" ? "bg-panel text-muted border-[1.5px] border-line" : "bg-danger-soft text-danger"}`}>{t.done ? "✓" : "!"}</span>
                <div className="min-w-0 flex-[1_1_300px]">
                  <p className="m-0 font-semibold text-[15px] text-ink">{t.title} <span className="sr-only">{t.done ? "(klaret)" : "(mangler)"}</span></p>
                  {!t.done && <p className="m-0 mt-0.5 text-[14px] text-muted break-words">{t.how}</p>}
                </div>
                {t.kind === "manual" && (
                  <button type="button" onClick={() => tick(t)} disabled={busy === t.key}
                    className={`${btn} min-h-[40px] ${t.done ? "bg-paper text-ink border-2 border-ink" : "bg-ink text-paper"}`}>{t.done ? "Fortryd" : "Det er gjort"}</button>
                )}
              </li>
            ))}
          </ol>
        </div>
      ))}
      {err && <p role="alert" className="m-0 text-[14px] text-danger">{err}</p>}
    </section>
  );
}

/* ------------------------------------------------------------------ start a campaign */

function Starter({ data }: { data: Overview }) {
  const router = useRouter();
  const open = data.markets.filter((m) => m.state === "email");
  const [country, setCountry] = useState(open[0]?.code ?? "US");
  const [city, setCity] = useState("");
  const [niche, setNiche] = useState(data.niches[0]?.key ?? "plumber");
  const [limit, setLimit] = useState(10);
  const [found, setFound] = useState<Candidate[] | null>(null);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [csv, setCsv] = useState("");
  const [name, setName] = useState("");
  const [busy, setBusy] = useState<"" | "search" | "run">("");
  const [progress, setProgress] = useState("");
  const [err, setErr] = useState("");
  const off = data.mode === "off";
  const market = data.markets.find((m) => m.code === country);

  const search = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy("search"); setErr(""); setFound(null);
    try {
      const r = await api<{ candidates: Candidate[] }>("/operator/outreach/search", { method: "POST", body: JSON.stringify({ country, city: city.trim(), niche, limit }) });
      setFound(r.candidates);
      setPicked(new Set(r.candidates.map((c, i) => (c.email ? i : -1)).filter((i) => i >= 0)));
      setName(slug(`${country}-${city}-${niche}`));
    } catch (e2) { setErr(errText(e2)); }
    setBusy("");
  };

  /** Step 1 in one request (rules, MX – no AI), then one lead per request, so a long batch never hangs. */
  const run = async (body: Record<string, unknown>, batch: string) => {
    setBusy("run"); setErr(""); setProgress("Tjekker landeregler og e-mailadresser …");
    try {
      const rep = await api<BatchReport>("/operator/outreach/batches", { method: "POST", body: JSON.stringify({ ...body, name: batch, research: false }) });
      const total = rep.totals.qualified ?? 0;
      let remaining = total;
      while (remaining > 0) {
        setProgress(`Researcher og skriver e-mail ${total - remaining + 1} af ${total} …`);
        const r = await api<{ processed: number; remaining: number }>(`/operator/outreach/batches/${batch}/process?limit=1`, { method: "POST" });
        if (r.processed === 0) break;
        remaining = r.remaining;
      }
      setProgress(""); setFound(null); setCsv("");
      router.push(`/app/operator/outreach?batch=${batch}#kampagne`); router.refresh();
    } catch (e2) { setErr(errText(e2)); setProgress(""); router.refresh(); }
    setBusy("");
  };
  const chosen = (found ?? []).filter((_, i) => picked.has(i));
  const toggle = (i: number) => setPicked((p) => { const n = new Set(p); if (n.has(i)) n.delete(i); else n.add(i); return n; });
  const leadOf = (c: Candidate) => ({ company_name: c.company_name, email: c.email, country: c.country, city: c.city, niche: c.niche, website: c.website, phone: c.phone, email_source: c.email_source, email_source_url: c.email_source_url, context: c.context });

  return (
    <section aria-labelledby="start-h" className={card}>
      <h2 id="start-h" className="font-display font-extrabold text-[22px] text-ink m-0">Start en kampagne</h2>
      {off && <p className="m-0 rounded-xl bg-highlight px-3.5 py-2.5 text-[14px] text-ink">Outreach er slukket. Sæt <code>OUTREACH_MODE=dry_run</code> på Render (første punkt på listen nederst), så bliver værktøjerne her aktive.</p>}

      <form onSubmit={search} className="flex flex-col gap-3">
        <h3 className="eyebrow m-0">1 · Vælg hvor og hvem</h3>
        <div className="grid grid-cols-1 md:grid-cols-[1fr_1fr_1fr_110px_auto] gap-2 items-end">
          <label className={label}>Land
            <Select value={country} onChange={(e) => setCountry(e.target.value)} disabled={off}>
              {data.markets.map((m) => <option key={m.code} value={m.code} disabled={m.state !== "email"}>{m.name}{m.state !== "email" ? ` – ${MARKET[m.state].toLowerCase()}` : ""}</option>)}
            </Select>
          </label>
          <label className={label}>By eller område
            <Input value={city} onChange={(e) => setCity(e.target.value)} placeholder="fx Austin, TX" required minLength={2} maxLength={80} disabled={off} />
          </label>
          <label className={label}>Branche
            <Select value={niche} onChange={(e) => setNiche(e.target.value)} disabled={off}>
              {data.niches.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
            </Select>
          </label>
          <label className={label}>Antal
            <Select value={limit} onChange={(e) => setLimit(Number(e.target.value))} disabled={off}>{[5, 10, 20].map((n) => <option key={n} value={n}>{n}</option>)}</Select>
          </label>
          <button type="submit" disabled={off || busy !== "" || !data.search_available} className={`${btn} bg-ink text-paper`}>{busy === "search" ? "Søger …" : "Find virksomheder"}</button>
        </div>
        {market && (
          <p className="m-0 text-[14px] text-muted">
            <strong className="text-ink">{market.name}:</strong> {market.rules}{market.price && <> Pris i e-mailen: {market.price}.</>}
            {market.state === "email" && !market.demo_available && <> <span className="text-danger font-semibold">Demo-opkaldet virker ikke i dette land endnu – e-mails kan skrives og læses, men holdes tilbage ved afsendelse.</span></>}
          </p>
        )}
        {!data.search_available && !off && <p className="m-0 text-[14px] text-muted">Søgningen kræver <code>GOOGLE_PLACES_API_KEY</code>. Indtil den er sat, kan du indsætte en CSV herunder.</p>}
      </form>

      {found && (
        <div className="flex flex-col gap-3">
          <h3 className="eyebrow m-0">2 · Vælg virksomheder ({chosen.length} af {found.length} valgt)</h3>
          {found.length === 0 ? <p className="m-0 text-[14px] text-muted">Ingen virksomheder fundet. Prøv en større by eller en anden branche.</p> : (
            <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
              {found.map((c, i) => (
                <li key={`${c.company_name}-${i}`} className={`rounded-xl border-[1.5px] px-3 py-2 ${c.email ? "border-ink" : "border-line bg-panel"}`}>
                  <label className="flex items-start gap-3 cursor-pointer">
                    <input type="checkbox" className="mt-1 w-5 h-5" disabled={!c.email} checked={picked.has(i)} onChange={() => toggle(i)} />
                    <span className="min-w-0">
                      <span className="block font-semibold text-[15px] text-ink break-words">{c.company_name} <span className="font-normal text-muted">· {c.city}</span></span>
                      <span className="block text-[13px] text-muted break-all">{c.email ?? c.problem}{c.website && <> · {c.website.replace(/^https?:\/\//, "").replace(/\/$/, "")}</>}</span>
                    </span>
                  </label>
                </li>
              ))}
            </ul>
          )}
          {found.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-2 items-end">
              <label className={label}>3 · Kampagnens navn
                <Input value={name} onChange={(e) => setName(slug(e.target.value))} maxLength={28} placeholder="us-austin-plumber" />
              </label>
              <button type="button" disabled={busy !== "" || chosen.length === 0} onClick={() => run({ leads: chosen.map(leadOf) }, `${name || "kampagne"}-${tail()}`)}
                className={`${btn} bg-accent text-white hover:bg-accent-deep`}>{busy === "run" ? "Arbejder …" : `Tjek og skriv ${chosen.length} e-mail${chosen.length === 1 ? "" : "s"}`}</button>
            </div>
          )}
        </div>
      )}

      <details className="rounded-xl border-[1.5px] border-ink">
        <summary className="cursor-pointer px-3.5 py-2.5 font-semibold text-[14px] text-ink">Har du selv en liste? Indsæt en CSV</summary>
        <div className="p-3.5 pt-0 flex flex-col gap-2">
          <p className="m-0 text-[13px] text-muted">Første linje er kolonnenavne: <code>company_name,email,country</code> er påkrævet; <code>city,niche,website,phone,registration_number,email_source,email_source_url,context</code> er valgfri. Højst 50 linjer. Danske ApS og A/S med CVR-nummer havner på ringelisten, ikke i e-mailkøen.</p>
          <Textarea value={csv} onChange={(e) => setCsv(e.target.value)} disabled={off} aria-label="CSV med virksomheder" className="font-mono text-[13px] min-h-[120px]" placeholder={"company_name,email,country,city,niche\nBrightwater Plumbing LLC,office@brightwater.com,US,Austin,plumber"} />
          <button type="button" disabled={off || busy !== "" || csv.trim().split("\n").length < 2} onClick={() => run({ csv }, `csv-${tail()}`)}
            className={`${btn} self-start bg-ink text-paper`}>Tjek listen og skriv e-mails</button>
        </div>
      </details>
      {progress && <p role="status" className="m-0 rounded-xl bg-panel border-[1.5px] border-ink px-3.5 py-2.5 text-[14px] text-ink">{progress} Luk ikke siden.</p>}
      {err && <p role="alert" className="m-0 text-[14px] text-danger">{err}</p>}
    </section>
  );
}

/* ------------------------------------------------------------------ campaigns */

function Batches({ data, active }: { data: Overview; active: string }) {
  if (!data.batches.length) return null;
  return (
    <section aria-labelledby="batches-h" className={card}>
      <h2 id="batches-h" className="font-display font-extrabold text-[22px] text-ink m-0">Kampagner</h2>
      <ul className="m-0 p-0 list-none flex flex-col gap-1.5">
        {data.batches.map((b) => (
          <li key={b.name}>
            <Link href={`/app/operator/outreach?batch=${b.name}#kampagne`} aria-current={b.name === active ? "page" : undefined}
              className={`flex flex-wrap items-center gap-2 rounded-xl border-[1.5px] border-ink px-3.5 py-2.5 ${b.name === active ? "bg-panel" : "bg-paper hover:bg-panel"}`}>
              <span className="font-semibold text-[15px] text-ink flex-[1_1_200px] break-all">{b.name}</span>
              <span className="text-[13px] text-muted">{new Date(b.created_at).toLocaleDateString("da-DK", { timeZone: "Europe/Copenhagen" })} · {b.leads} virksomheder</span>
              {Object.entries(b.totals).map(([st, n]) => <span key={st} className={`${badge} ${(STATUS[st] ?? STATUS.new)[1]}`}>{(STATUS[st] ?? [st])[0]} {n}</span>)}
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function BatchDetail({ report, mode, queued }: { report: BatchReport; mode: Overview["mode"]; queued: number }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const waiting = report.totals.qualified ?? 0;
  const act = async (fn: () => Promise<string>) => {
    setBusy(true); setMsg(null);
    try { setMsg({ ok: true, text: await fn() }); } catch (e) { setMsg({ ok: false, text: errText(e) }); }
    setBusy(false); setConfirm(false); router.refresh();
  };
  const finish = () => act(async () => {
    let done = 0;
    for (;;) {
      const r = await api<{ processed: number; remaining: number }>(`/operator/outreach/batches/${report.batch}/process?limit=1`, { method: "POST" });
      done += r.processed;
      if (r.processed === 0 || r.remaining === 0) break;
    }
    return `${done} virksomhed${done === 1 ? "" : "er"} behandlet.`;
  });
  const dispatch = () => act(async () => {
    const r = await api<{ mode: string; sent: number; waiting: number; cancelled: number; failed: number }>("/operator/outreach/dispatch?limit=50", { method: "POST" });
    return r.mode === "dry_run"
      ? `Tørkørsel: ${r.sent} e-mail${r.sent === 1 ? "" : "s"} gjort færdig med frameldingslink – intet er sendt. Åbn en e-mail herunder for at se den, som den ville blive sendt.`
      : `${r.sent} sendt · ${r.waiting} venter (demo eller dagsgrænse) · ${r.cancelled} annulleret · ${r.failed} fejlet.`;
  });
  return (
    <section id="kampagne" aria-labelledby="detail-h" className={`${card} scroll-mt-4`}>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="detail-h" className="font-display font-extrabold text-[22px] text-ink m-0 break-all">{report.batch}</h2>
        <span className="text-[13px] text-muted">Claude-forbrug: {report.tokens.input_tokens.toLocaleString("da-DK")} ind / {report.tokens.output_tokens.toLocaleString("da-DK")} ud (tokens)</span>
      </div>
      <div className="flex flex-wrap gap-2 items-center">
        {waiting > 0 && <button type="button" disabled={busy} onClick={finish} className={`${btn} bg-ink text-paper`}>{busy ? "Arbejder …" : `Research og skriv de ${waiting} der mangler`}</button>}
        {mode === "dry_run" && queued > 0 && <button type="button" disabled={busy} onClick={dispatch} className={`${btn} bg-accent text-white hover:bg-accent-deep`}>Gør e-mails færdige (sender intet)</button>}
        {mode === "live" && queued > 0 && !confirm && <button type="button" disabled={busy} onClick={() => setConfirm(true)} className={`${btn} bg-accent text-white hover:bg-accent-deep`}>Send køen nu ({queued})</button>}
        {mode === "live" && confirm && (
          <span className="flex flex-wrap items-center gap-2 rounded-xl bg-highlight px-3 py-2">
            <span className="text-[14px] font-semibold text-ink">Sender op til {Math.min(queued, 50)} rigtige e-mails fra alle kampagner. Sikker?</span>
            <button type="button" disabled={busy} onClick={dispatch} className={`${btn} min-h-[40px] bg-ink text-paper`}>Ja, send</button>
            <button type="button" disabled={busy} onClick={() => setConfirm(false)} className={`${btn} min-h-[40px] bg-paper text-ink border-2 border-ink`}>Nej</button>
          </span>
        )}
      </div>
      {msg && <p role={msg.ok ? "status" : "alert"} className={`m-0 text-[14px] ${msg.ok ? "text-success" : "text-danger"}`}>{msg.text}</p>}
      <ul className="m-0 p-0 list-none flex flex-col gap-2">
        {report.leads.map((l) => {
          const [sLabel, sCls] = STATUS[l.status] ?? [l.status, "bg-panel text-ink"];
          const d = l.email_draft;
          const issues = d?.audit.issues ?? [];
          return (
            <li key={l.email} className="rounded-xl border-[1.5px] border-ink px-3.5 py-3 flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-[15px] text-ink flex-[1_1_220px] break-words">{l.company} <span className="font-normal text-muted break-all">· {l.email} · {l.country}</span></span>
                {l.confidence != null && <span className="text-[13px] text-muted">sikkerhed {Math.round(l.confidence * 100)} %</span>}
                <span className={`${badge} ${sCls}`}>{sLabel}</span>
              </div>
              {(l.status === "blocked" || l.status === "held") && l.compliance.reasons && <p className="m-0 text-[14px] text-muted">{l.compliance.reasons.join(" · ")}</p>}
              {l.status === "low_confidence" && <p className="m-0 text-[14px] text-muted">Researchen fandt ikke noget konkret nok at åbne med, så der blev ikke skrevet en e-mail (hellere ingen end en generisk).</p>}
              {issues.length > 0 && <ul className="m-0 pl-5 text-[14px] text-danger">{issues.map((x) => <li key={x}>{x}</li>)}</ul>}
              {d && (
                <details>
                  <summary className="cursor-pointer text-[14px] font-semibold text-ink">{d.rendered ? "Sådan ville den blive sendt" : "Læs e-mailen"} · «{d.subject}» · {d.words} ord</summary>
                  <pre className="mt-2 whitespace-pre-wrap break-words rounded-xl bg-panel border-[1.5px] border-line p-3 text-[14px] leading-6 font-body text-ink">{`Emne: ${d.subject}\n\n${d.rendered ?? `${d.body}\n\n${d.footer}`}`}</pre>
                </details>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

/* ------------------------------------------------------------------ call list + markets */

function CallList({ open, review, off }: { open: number; review: number; off: boolean }) {
  if (off || open + review === 0) return null;
  return (
    <section aria-labelledby="call-h" className={card}>
      <h2 id="call-h" className="font-display font-extrabold text-[22px] text-ink m-0">Ringeliste (Danmark)</h2>
      <p className="m-0 text-[14px] text-muted">Danske virksomheder må ikke få kold e-mail. ApS og A/S uden reklamebeskyttelse i CVR står her, så et menneske kan ringe til dem.{review > 0 && ` ${review} mangler CVR-tjek (ingen CVR-adgang sat op) og skal tjekkes i hånden, før nogen ringer.`}</p>
      <div className="flex flex-wrap gap-2">
        <a href="/api/backend/operator/outreach/call-queue.csv" download="ringeliste.csv" className={`${btn} inline-flex items-center bg-ink text-paper`}>Hent ringelisten ({open})</a>
        {review > 0 && <a href="/api/backend/operator/outreach/call-queue.csv?include_needs_review=true" download="ringeliste-med-utjekkede.csv" className={`${btn} inline-flex items-center bg-paper text-ink border-2 border-ink`}>Hent også de utjekkede ({review})</a>}
      </div>
    </section>
  );
}

function Markets({ markets }: { markets: Market[] }) {
  const cls: Record<Market["state"], string> = { email: "bg-success-soft text-success", call_list: "bg-accent text-white", hold: "bg-highlight text-ink", blocked: "bg-danger-soft text-danger" };
  return (
    <details className="rounded-2xl border-2 border-ink bg-paper">
      <summary className="cursor-pointer px-space-md py-3 font-semibold text-ink">Landeregler – hvem må du skrive til</summary>
      <ul className="m-0 p-space-md pt-0 list-none flex flex-col gap-1.5">
        {markets.map((m) => (
          <li key={m.code} className="flex flex-wrap items-baseline gap-2 text-[14px]">
            <span className="font-semibold text-ink w-36">{m.name}</span>
            <span className={`${badge} ${cls[m.state]}`}>{MARKET[m.state]}</span>
            <span className="text-muted flex-[1_1_260px]">{m.rules} <span className="text-[12px]">({m.regime})</span></span>
          </li>
        ))}
      </ul>
    </details>
  );
}
