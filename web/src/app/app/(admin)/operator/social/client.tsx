"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Badge, Button, ErrorBox, Field, Icon, Select, Textarea, useSubmit } from "@/components/ui";

export type Platform = "facebook" | "instagram" | "tiktok";
export type Post = {
  id: string; platform: Platform; status: string; topic: string; extra?: boolean; slot_date: string; scheduled_for: string; caption: string;
  hashtags: string[]; slides: { role: string; kicker: string; title: string; body: string; bullets?: string[] }[]; link: string | null;
  generator: string; external_id: string | null; external_url: string | null; attempts: number; last_error: string | null;
  published_at: string | null; metrics: Record<string, number | string> | null; metrics_at: string | null; images: string[];
};
export type PlatformStats = {
  platform: Platform; enabled: boolean; connected: boolean; configured: boolean | null;
  followers: number | null; following: number | null; posts: number | null; likes: number | null; captured_on: string | null;
  delta_7d: number | null; delta_30d: number | null; series: { date: string; followers: number | null }[]; error: string | null;
};
export type Prospect = {
  id: string; cvr: string; name: string; industry: string; industry_label: string; industry_text: string | null; city: string | null;
  website: string | null; facebook_url: string | null; instagram_url: string | null; tiktok_url: string | null;
  suggested_comment: string; status: "new" | "done" | "skipped"; found_on: string; acted_platforms: Platform[]; note: string | null; acted_at: string | null;
};
export type Dashboard = {
  overview: { provider: string; require_approval: boolean; weekdays: number[]; plan_days_ahead: number; slot_times: Record<string, string>; topics: string[] };
  platforms: PlatformStats[]; pending: Post[]; scheduled: Post[]; recent: Post[]; failed: Post[];
  engagement_totals: Record<string, { posts: number; likes: number; comments: number; shares: number; views: number }>;
  prospects: Prospect[]; prospects_enabled: boolean; prospect_counts: { new: number; done: number; skipped: number };
  days: number; generated_at: string;
};

const PLATFORM: Record<Platform, { label: string; handle: string; icon: string }> = {
  facebook: { label: "Facebook", handle: "Dialogbot (side)", icon: "campaign" },
  instagram: { label: "Instagram", handle: "@dialogbotdenmark", icon: "visibility" },
  tiktok: { label: "TikTok", handle: "@dialogbot", icon: "play_circle" },
};
const WEEKDAY = ["man", "tir", "ons", "tor", "fre", "lør", "søn"];
const num = (n: number | null | undefined) => (n == null ? "–" : n.toLocaleString("da-DK"));
const when = (iso: string | null) => (iso ? new Date(iso).toLocaleString("da-DK", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }) : "–");
const topicLabel = (t: string) => t.replace(/_/g, " ");

export function SocialDashboard({ data }: { data: Dashboard }) {
  const router = useRouter();
  const [refreshed, setRefreshed] = useState<{ accounts: number; posts: number } | null>(null);
  const refresh = useSubmit(async () => {
    const r = await api<{ accounts: number; posts: number }>("/operator/social/metrics/refresh", { method: "POST", body: "{}" });
    setRefreshed(r); router.refresh();
  });
  const o = data.overview;
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-center justify-between gap-space-sm">
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          {o.provider === "live" ? <span className="text-secondary font-semibold">Automatisk opslag er slået til</span> : <span className="text-error font-semibold">Automatisk opslag er slået fra (SOCIAL_PROVIDER={o.provider})</span>}
          {" · "}{o.weekdays.length === 7 ? "alle dage" : o.weekdays.map((d) => WEEKDAY[d]).join(", ")}
          {" · "}{o.require_approval ? "kræver din godkendelse" : "postes uden godkendelse"}
          {" · "}kladder {o.plan_days_ahead} dage forud
        </p>
        <div className="flex items-center gap-space-xs">
          <Select value={String(data.days)} onChange={(e) => router.push(`/app/operator/social?days=${e.target.value}`)} aria-label="Periode" className="w-auto">
            <option value="7">Seneste 7 dage</option><option value="30">Seneste 30 dage</option><option value="90">Seneste 90 dage</option>
          </Select>
          <Button variant="outline" icon="autorenew" disabled={refresh.pending} onClick={() => refresh.run()}>{refresh.pending ? "Henter…" : "Opdater tal"}</Button>
        </div>
      </div>
      <ErrorBox error={refresh.error} />
      {refreshed && <Alert kind="ok">Tal hentet fra platformene: {refreshed.accounts} profil(er), {refreshed.posts} opslag.</Alert>}

      <div className="grid gap-space-md md:grid-cols-3">
        {data.platforms.map((p) => <PlatformCard key={p.platform} p={p} totals={data.engagement_totals[p.platform]} days={data.days} />)}
      </div>

      <Section title={`Venter på godkendelse (${data.pending.length})`} hint={data.pending.length ? "Læs teksten igennem, ret den om nødvendigt, og godkend – så går opslaget ud på det planlagte tidspunkt." : "Ingen kladder lige nu. Nye kladder laves automatisk, så der altid er opslag klar til de næste dage."}>
        {data.pending.map((p) => <PostCard key={p.id} p={p} editable />)}
      </Section>

      <Section title={`Planlagt (${data.scheduled.length})`} hint={data.scheduled.length ? "Godkendt og klar – worker'en poster dem på det planlagte tidspunkt." : undefined}>
        {data.scheduled.map((p) => <PostCard key={p.id} p={p} />)}
      </Section>

      {data.failed.length > 0 && (
        <Section title={`Fejlet (${data.failed.length})`} hint="Tjek altid profilen, før du poster igen: er opslaget allerede gået ud, så annullér det her i stedet.">
          {data.failed.map((p) => <PostCard key={p.id} p={p} />)}
        </Section>
      )}

      <Section title={`Gået ud de seneste ${data.days} dage (${data.recent.length})`} hint={data.recent.length ? undefined : "Ingen opslag er gået ud i perioden."}>
        {data.recent.map((p) => <PostCard key={p.id} p={p} compact />)}
      </Section>

      <ProspectsBox prospects={data.prospects} enabled={data.prospects_enabled} counts={data.prospect_counts} />

      <PlanBox topics={o.topics} />
    </div>
  );
}

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md space-y-space-md">
      <div>
        <h2 className="font-headline-sm text-headline-sm text-primary font-bold">{title}</h2>
        {hint && <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

function Delta({ n, label }: { n: number | null; label: string }) {
  if (n == null) return <span className="text-on-surface-variant">– {label}</span>;
  const cls = n > 0 ? "text-secondary" : n < 0 ? "text-error" : "text-on-surface-variant";
  return <span className={`${cls} font-semibold tabular-nums`}>{n > 0 ? "+" : ""}{num(n)} {label}</span>;
}

/** Follower curve as a plain inline SVG – no chart library in the app. */
function Sparkline({ series }: { series: { date: string; followers: number | null }[] }) {
  const pts = series.filter((s) => s.followers != null) as { date: string; followers: number }[];
  if (pts.length < 2) return <p className="font-label-sm text-label-sm text-on-surface-variant h-12 flex items-end">Kurven vises, når der er tal for mindst to dage.</p>;
  const W = 240, H = 48, min = Math.min(...pts.map((p) => p.followers)), max = Math.max(...pts.map((p) => p.followers));
  const y = (v: number) => (max === min ? H / 2 : H - 4 - ((v - min) / (max - min)) * (H - 8));
  const d = pts.map((p, i) => `${i ? "L" : "M"}${(i / (pts.length - 1)) * W},${y(p.followers)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-12" role="img" aria-label={`Følgere fra ${num(pts[0].followers)} til ${num(pts[pts.length - 1].followers)}`}>
      <path d={d} fill="none" stroke="currentColor" strokeWidth={2} className="text-primary" strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
}

function PlatformCard({ p, totals, days }: { p: PlatformStats; totals?: Dashboard["engagement_totals"][string]; days: number }) {
  const meta = PLATFORM[p.platform];
  const state = !p.enabled ? ["Slået fra", "bg-surface-container-highest text-on-surface-variant"] : p.connected ? ["Forbundet", "bg-secondary-container text-on-secondary-container"] : ["Ikke forbundet", "bg-error-container text-on-error-container"];
  return (
    <div className="rounded-xl bg-surface-container-lowest p-space-md shadow-sm flex flex-col gap-space-sm">
      <div className="flex items-start justify-between gap-space-xs">
        <div>
          <p className="font-label-lg text-label-lg font-semibold flex items-center gap-1"><Icon name={meta.icon} size={18} />{meta.label}</p>
          <p className="font-label-sm text-label-sm text-on-surface-variant">{meta.handle}</p>
        </div>
        <span className={`inline-flex rounded-full px-2 py-0.5 font-label-sm text-label-sm font-semibold ${state[1]}`}>{state[0]}</span>
      </div>
      <div>
        <p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold flex items-center gap-1"><Icon name="group" size={16} />Følgere</p>
        <p className="font-headline-md text-headline-md text-primary font-bold tabular-nums">{num(p.followers)}</p>
        <p className="font-label-sm text-label-sm flex gap-space-sm"><Delta n={p.delta_7d} label="7 d" /><Delta n={p.delta_30d} label="30 d" /></p>
      </div>
      <Sparkline series={p.series} />
      <dl className="grid grid-cols-3 gap-space-xs font-label-sm text-label-sm">
        <div><dt className="text-on-surface-variant">Opslag</dt><dd className="tabular-nums font-semibold">{num(p.posts)}</dd></div>
        <div><dt className="text-on-surface-variant">Følger</dt><dd className="tabular-nums font-semibold">{num(p.following)}</dd></div>
        <div><dt className="text-on-surface-variant">{p.platform === "facebook" ? "Synes godt om" : "Likes i alt"}</dt><dd className="tabular-nums font-semibold">{num(p.likes)}</dd></div>
      </dl>
      <div className="rounded-lg bg-surface-container-low p-space-sm font-label-sm text-label-sm">
        <p className="text-on-surface-variant font-bold uppercase tracking-wider flex items-center gap-1"><Icon name="bar_chart" size={14} />Engagement, {days} dage</p>
        {totals ? (
          <p className="tabular-nums mt-0.5">{totals.posts} opslag · {num(totals.likes)} likes · {num(totals.comments)} kommentarer · {num(totals.shares)} delinger{p.platform === "tiktok" ? ` · ${num(totals.views)} visninger` : ""}</p>
        ) : <p className="text-on-surface-variant mt-0.5">Ingen opslag i perioden.</p>}
      </div>
      {p.error && <p className="font-label-sm text-label-sm text-error">{p.error}</p>}
      {p.captured_on && <p className="font-label-sm text-label-sm text-on-surface-variant">Tal fra {new Date(p.captured_on).toLocaleDateString("da-DK", { day: "numeric", month: "short" })}</p>}
    </div>
  );
}

function Metrics({ m }: { m: Post["metrics"] }) {
  if (!m) return <span className="text-on-surface-variant">Tal hentes inden for en time</span>;
  if (typeof m.error === "string" && m.likes == null) return <span className="text-on-surface-variant">{m.error}</span>;
  const parts = [["likes", "likes"], ["comments", "kommentarer"], ["shares", "delinger"], ["views", "visninger"]].filter(([k]) => typeof m[k] === "number");
  return <span className="tabular-nums">{parts.map(([k, l]) => `${num(m[k] as number)} ${l}`).join(" · ")}</span>;
}

function PostCard({ p, editable = false, compact = false }: { p: Post; editable?: boolean; compact?: boolean }) {
  const router = useRouter();
  const [caption, setCaption] = useState(p.caption);
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const dirty = caption !== p.caption;
  const save = useSubmit(async () => { await api(`/operator/social/posts/${p.id}`, { method: "PATCH", body: JSON.stringify({ caption }) }); setEditing(false); router.refresh(); });
  const approve = useSubmit(async () => {
    if (dirty) await api(`/operator/social/posts/${p.id}`, { method: "PATCH", body: JSON.stringify({ caption }) });
    await api(`/operator/social/posts/${p.id}/approve`, { method: "POST" }); router.refresh();
  });
  const cancel = useSubmit(async () => { await api(`/operator/social/posts/${p.id}/cancel`, { method: "POST" }); router.refresh(); });
  const publish = useSubmit(async () => {
    if (dirty) await api(`/operator/social/posts/${p.id}`, { method: "PATCH", body: JSON.stringify({ caption }) });
    setNote("Poster… Instagram kan tage op til et minut.");
    // The call can outlive the proxy on Instagram; the post is marked `publishing` first, so poll instead of re-sending.
    const call = api<Post>(`/operator/social/posts/${p.id}/publish-now`, { method: "POST" }).catch(() => null);
    for (let i = 0; i < 24; i++) {
      const r = await Promise.race([call, new Promise<null>((res) => setTimeout(() => res(null), 5000))]);
      const st = r ? r.status : (await api<Post>(`/operator/social/posts/${p.id}`).catch(() => null))?.status;
      if (st && st !== "publishing" && st !== "scheduled" && st !== "draft") { setNote(st === "published" ? "Opslaget er gået ud." : "Opslaget gik ikke ud – se fejlen."); break; }
      if (r) break;
    }
    router.refresh();
  });
  const busy = save.pending || approve.pending || cancel.pending || publish.pending;
  const meta = PLATFORM[p.platform];
  const canAct = ["draft", "scheduled", "failed"].includes(p.status);
  return (
    <article className="rounded-lg bg-surface-container-low p-space-md flex flex-col gap-space-sm">
      <div className="flex flex-wrap items-center gap-space-xs font-label-sm text-label-sm">
        <span className="font-label-lg text-label-lg font-semibold flex items-center gap-1 text-primary"><Icon name={meta.icon} size={18} />{meta.label}</span>
        <Badge status={p.status} />
        {p.extra && <span className="inline-flex items-center rounded-full px-2 py-0.5 text-label-sm font-semibold bg-tertiary-fixed text-on-tertiary-fixed">Ekstra</span>}
        <span className="text-on-surface-variant">{topicLabel(p.topic)} · {p.status === "published" ? `gik ud ${when(p.published_at)}` : `planlagt ${when(p.scheduled_for)}`}{p.generator === "ai" ? " · AI-tekst" : ""}</span>
        {p.external_url && <a href={p.external_url} target="_blank" rel="noreferrer" className="underline text-primary flex items-center gap-0.5"><Icon name="link" size={14} />Se opslaget</a>}
      </div>
      {!compact && p.images.length > 0 && (
        <div className="flex gap-space-xs overflow-x-auto">
          {p.images.map((src, i) => <img key={src} src={src} alt={`Slide ${i + 1}`} loading="lazy" className="h-28 w-auto rounded-md shadow-sm" />)}
        </div>
      )}
      {editing ? (
        <Field label="Tekst" hint="Links og hashtags sættes på automatisk."><Textarea value={caption} onChange={(e) => setCaption(e.target.value)} rows={6} /></Field>
      ) : (
        <p className={`font-body-md text-body-md whitespace-pre-wrap ${compact ? "line-clamp-3" : ""}`}>{caption}</p>
      )}
      {p.status === "published" && <p className="font-label-sm text-label-sm flex items-center gap-1"><Icon name="bar_chart" size={14} /><Metrics m={p.metrics} /></p>}
      {p.last_error && <p className="font-label-sm text-label-sm text-error">{p.last_error}</p>}
      <ErrorBox error={save.error ?? approve.error ?? cancel.error ?? publish.error} />
      {note && <Alert kind="info">{note}</Alert>}
      {canAct && (
        <div className="flex flex-wrap gap-space-xs">
          {editable && !editing && <Button variant="outline" icon="edit" disabled={busy} onClick={() => setEditing(true)}>Ret tekst</Button>}
          {editing && <Button variant="outline" icon="save" disabled={busy || !dirty} onClick={() => save.run()}>Gem tekst</Button>}
          {editing && <Button variant="ghost" disabled={busy} onClick={() => { setCaption(p.caption); setEditing(false); }}>Fortryd</Button>}
          {p.status === "draft" && <Button icon="check" disabled={busy} onClick={() => approve.run()}>{approve.pending ? "Godkender…" : dirty ? "Gem og godkend" : "Godkend"}</Button>}
          <Button variant={p.status === "draft" ? "tonal" : "primary"} icon="send" disabled={busy} onClick={() => publish.run()}>{publish.pending ? "Poster…" : "Post nu"}</Button>
          <Button variant="ghost" icon="close" disabled={busy} onClick={() => cancel.run()}>Annullér</Button>
        </div>
      )}
    </article>
  );
}

function PlanBox({ topics }: { topics: string[] }) {
  const router = useRouter();
  const today = new Date().toISOString().slice(0, 10);
  const [day, setDay] = useState(today);
  const [topic, setTopic] = useState("");
  const [platforms, setPlatforms] = useState<Platform[]>(["facebook", "instagram", "tiktok"]);
  const [at, setAt] = useState("");
  const [made, setMade] = useState<number | null>(null);
  const toggle = (pl: Platform) => setPlatforms((c) => (c.includes(pl) ? c.filter((x) => x !== pl) : [...c, pl]));
  const make = useSubmit(async () => {
    const body = { day, topic: topic || null, platforms, at: at ? new Date(`${day}T${at}`).toISOString() : null };
    const r = await api<{ created: unknown[] }>("/operator/social/extra", { method: "POST", body: JSON.stringify(body) });
    setMade(r.created.length); router.refresh();
    if (r.created.length) window.scrollTo({ top: 0, behavior: "smooth" });
  });
  return (
    <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md space-y-space-sm">
      <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Generér nye opslag</h2>
      <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Laver nye kladder med det samme – også på en dag, der allerede har opslag. De lander øverst under <em>Venter på godkendelse</em>; tryk <em>Godkend</em> (går ud på det valgte tidspunkt, som standard om ti minutter) eller <em>Post nu</em>.</p>
      <div className="flex flex-wrap items-end gap-space-sm">
        <Field label="Dag"><input type="date" value={day} min={today} onChange={(e) => setDay(e.target.value)} className="px-3 py-2 rounded-lg bg-surface font-body-md text-body-md shadow-inner" /></Field>
        <Field label="Emne"><Select value={topic} onChange={(e) => setTopic(e.target.value)}><option value="">Automatisk (det der er længst siden)</option>{topics.map((t) => <option key={t} value={t}>{topicLabel(t)}</option>)}</Select></Field>
        <Field label="Klokken" hint="Tom = om ti minutter"><input type="time" value={at} onChange={(e) => setAt(e.target.value)} className="px-3 py-2 rounded-lg bg-surface font-body-md text-body-md shadow-inner" /></Field>
        <div className="flex items-center gap-space-sm pb-2">
          {(Object.keys(PLATFORM) as Platform[]).map((pl) => (
            <label key={pl} className="flex items-center gap-1 font-label-sm text-label-sm"><input type="checkbox" checked={platforms.includes(pl)} onChange={() => toggle(pl)} />{PLATFORM[pl].label}</label>
          ))}
        </div>
        <Button icon="auto_awesome" disabled={make.pending || platforms.length === 0} onClick={() => make.run()}>{make.pending ? "Genererer… (op til et minut)" : "Generér nye opslag"}</Button>
      </div>
      <ErrorBox error={make.error} />
      {made != null && <Alert kind={made ? "ok" : "info"}>{made ? `${made} nye kladde(r) lavet – de venter på din godkendelse øverst.` : "Ingen kladder lavet – er platformene forbundet?"}</Alert>}
    </section>
  );
}

const INDUSTRIES: [string, string][] = [["haandvaerkere", "Håndværkere"], ["klinikker", "Klinikker"], ["frisoerer", "Frisører og saloner"], ["autovaerksteder", "Autoværksteder"], ["raadgivere", "Rådgivere og kontorer"], ["restauranter", "Restauranter og hoteller"]];

/** Companies the system found; the operator follows and comments by hand (the platforms forbid doing it automatically). */
function ProspectsBox({ prospects, enabled, counts }: { prospects: Prospect[]; enabled: boolean; counts: Dashboard["prospect_counts"] }) {
  const router = useRouter();
  const [industry, setIndustry] = useState("");
  const [made, setMade] = useState<number | null>(null);
  const discover = useSubmit(async () => {
    const r = await api<{ created: unknown[] }>("/operator/social/prospects/discover", { method: "POST", body: JSON.stringify({ industry: industry || null }) });
    setMade(r.created.length); router.refresh();
  });
  return (
    <section className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md space-y-space-md">
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div>
          <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Profiler at følge ({prospects.length})</h2>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Hver morgen finder systemet ca. 20 danske virksomheder i Dialogbots brancher (CVR-registret → deres hjemmeside → deres profiler). Åbn profilen, følg den fra Dialogbots konto og læg evt. kommentaren – og markér så, hvad du gjorde. Platformene forbyder, at det sker automatisk, så det sidste klik er dit. {counts.done} fulgt · {counts.skipped} sprunget over.</p>
        </div>
        <div className="flex flex-wrap items-end gap-space-xs">
          <Select value={industry} onChange={(e) => setIndustry(e.target.value)} aria-label="Branche" className="w-auto"><option value="">Næste branche i rækken</option>{INDUSTRIES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</Select>
          <Button variant="outline" icon="search" disabled={discover.pending || !enabled} onClick={() => discover.run()}>{discover.pending ? "Finder…" : "Find flere nu"}</Button>
        </div>
      </div>
      {!enabled && <Alert kind="warn">Kræver adgang til CVR-registret (CVR_USERNAME/CVR_PASSWORD i Render). Adgangen er gratis og søges hos Erhvervsstyrelsen (cvrselvbetjening@erst.dk).</Alert>}
      <ErrorBox error={discover.error} />
      {made != null && <Alert kind={made ? "ok" : "info"}>{made ? `${made} virksomhed(er) fundet.` : "Ingen nye virksomheder med profiler fundet i denne omgang – prøv en anden branche."}</Alert>}
      {prospects.length === 0 && enabled && <p className="font-body-sm text-body-sm text-on-surface-variant">Listen er tom – den næste portion kommer i morgen tidlig, eller tryk <em>Find flere nu</em>.</p>}
      {prospects.length > 0 && <ul className="divide-y divide-outline-variant/40">{prospects.map((p) => <ProspectRow key={p.id} p={p} />)}</ul>}
    </section>
  );
}

function ProspectRow({ p }: { p: Prospect }) {
  const router = useRouter();
  const [chosen, setChosen] = useState<Platform[]>([]);
  const [copied, setCopied] = useState(false);
  const links: [Platform, string | null][] = [["facebook", p.facebook_url], ["instagram", p.instagram_url], ["tiktok", p.tiktok_url]];
  const done = useSubmit(async () => { await api(`/operator/social/prospects/${p.id}/done`, { method: "POST", body: JSON.stringify({ platforms: chosen }) }); router.refresh(); });
  const skip = useSubmit(async () => { await api(`/operator/social/prospects/${p.id}/skip`, { method: "POST", body: "{}" }); router.refresh(); });
  const toggle = (pl: Platform) => setChosen((c) => (c.includes(pl) ? c.filter((x) => x !== pl) : [...c, pl]));
  const copy = async () => { try { await navigator.clipboard.writeText(p.suggested_comment); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* clipboard blocked: the text is visible to copy by hand */ } };
  const busy = done.pending || skip.pending;
  return (
    <li className="py-space-sm flex flex-col gap-space-xs md:flex-row md:items-start">
      <div className="flex-1 min-w-0">
        <p className="font-label-lg text-label-lg font-semibold">{p.name} <span className="font-label-sm text-label-sm text-on-surface-variant font-normal">· {p.industry_label}{p.city ? ` · ${p.city}` : ""}{p.industry_text ? ` · ${p.industry_text}` : ""}</span></p>
        <p className="font-label-sm text-label-sm flex flex-wrap gap-space-sm mt-0.5">
          {links.map(([pl, url]) => url && (
            <a key={pl} href={url} target="_blank" rel="noreferrer" onClick={() => { if (!chosen.includes(pl)) toggle(pl); }} className="underline text-primary flex items-center gap-0.5"><Icon name={PLATFORM[pl].icon} size={14} />{PLATFORM[pl].label}</a>
          ))}
          {p.website && <a href={p.website} target="_blank" rel="noreferrer" className="underline text-on-surface-variant flex items-center gap-0.5"><Icon name="link" size={14} />hjemmeside</a>}
        </p>
        <p className="font-body-sm text-body-sm text-on-surface-variant mt-1 flex items-start gap-space-xs"><span className="flex-1">„{p.suggested_comment}“</span><button type="button" onClick={copy} className="shrink-0 underline text-primary font-label-sm text-label-sm">{copied ? "Kopieret" : "Kopiér"}</button></p>
        <ErrorBox error={done.error ?? skip.error} />
      </div>
      <div className="flex flex-wrap items-center gap-space-xs md:w-80 md:justify-end">
        {links.map(([pl, url]) => url && (
          <label key={pl} className="flex items-center gap-1 font-label-sm text-label-sm"><input type="checkbox" checked={chosen.includes(pl)} onChange={() => toggle(pl)} />{PLATFORM[pl].label}</label>
        ))}
        <Button icon="check" disabled={busy || chosen.length === 0} onClick={() => done.run()}>Fulgt</Button>
        <Button variant="ghost" icon="close" disabled={busy} onClick={() => skip.run()}>Spring over</Button>
      </div>
    </li>
  );
}
