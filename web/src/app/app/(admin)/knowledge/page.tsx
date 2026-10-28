import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { AssistantPreview, usd } from "./assistant";
import { WebsiteImport, type SourceImport } from "./import";
import { AddPanel, ApproveNewButton, ItemCard, KeepButton, NewItemForm, ReviewCard, VersionActions } from "./client";
import { KIND_LABEL, dateDa, kr, summarize } from "./format";

export type Version = { id: string; item_id: string; version_no: number; status: string; title: string; content: Record<string, unknown>; edit_version: number; submitted_at: string | null; source_type?: string };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented" };
type Usage = { days: number; totals: { calls: number; input_tokens: number; output_tokens: number; cache_creation_input_tokens: number; cache_read_input_tokens: number; est_cost_usd_micros: number } };
type Profile = { legal_name?: string; description?: string; website_url: string | null; city?: string | null };
export type Item = { id: string; kind: string; key: string; approved_version: Version | null; open_draft: Version | null };

const TABS: [string, string, string, string][] = [
  ["k03", "Ydelser & viden", "Viden", "sell"],
  ["k04", "Tilbud", "Tilbud", "percent"],
  ["k05", "Godkend", "Godkend", "rule"],
  ["k01", "Hjemmeside & kilder", "Kilder", "cloud_sync"],
  ["r05", "Manuskript", "Manuskript", "support_agent"],
  ["r06", "Test", "Test", "play_circle"],
];
const OTHER_KINDS = ["opening_hours", "coverage_area", "fact", "known_answer", "unknown_answer"];

const CARD = "flex flex-col gap-3 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink";
const PILL_BTN = "inline-flex items-center gap-2 min-h-[44px] px-4 rounded-xl bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel";

/** "Det ved den": everything Dialogbot may say to customers, in four numbered boxes, plus the existing
 *  catalogue / offers / approval / sources / script / test flows underneath. Only approved knowledge reaches the assistant. */
export default async function KnowledgePage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "k03" } = await searchParams;
  const ws = await requireWorkspace();
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const [items, queue, active, caps, usage, profile, latest] = await Promise.all([
    backend<{ items: Item[]; total: number }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Version[]>(`/workspaces/${ws.id}/knowledge/review-queue`),
    backend<{ knowledge_revision: number; items: unknown[] }>(`/workspaces/${ws.id}/assistant/knowledge`),
    backend<{ items: Capability[] }>("/integrations/capabilities"),
    tab === "r06" && canApprove ? backend<Usage>(`/workspaces/${ws.id}/ai/usage?days=30`) : Promise.resolve(null),
    backend<Profile>(`/workspaces/${ws.id}/profile`).catch(() => ({ website_url: null }) as Profile),
    backend<{ import: SourceImport | null }>(`/workspaces/${ws.id}/knowledge/imports/latest`),
  ]);
  const importReady = caps.items.find((c) => c.key === "knowledge.source_import")?.status !== "not_implemented";
  const aiStatus = caps.items.find((c) => c.key === "ai.assistant_preview")?.status ?? "not_implemented";
  const canDraft = ws.role !== "reader";
  const all = items.items;
  const drafts = all.filter((i) => i.open_draft);
  const byId = new Map(all.map((i) => [i.id, i]));
  const services = all.filter((i) => i.kind === "service");
  const others = all.filter((i) => OTHER_KINDS.includes(i.kind));
  const offers = all.filter((i) => i.kind === "offer");
  const approvedOf = (kind: string) => all.filter((i) => i.kind === kind && i.approved_version);
  const hours = approvedOf("opening_hours")[0]?.approved_version;
  const area = approvedOf("coverage_area")[0]?.approved_version;
  const answers = approvedOf("known_answer");
  const rules = approvedOf("unknown_answer");
  const pending = drafts.length;
  const showTest = aiStatus !== "not_implemented" && canDraft && active.items.length > 0;

  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_560px] min-w-0 flex flex-col gap-5">
        {/* Header */}
        <div className="flex flex-wrap items-end gap-3 md:gap-6">
          <div className="flex flex-col gap-1.5 flex-[1_1_320px]">
            <span className="eyebrow">Det ved den om jer</span>
            <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Alt, Dialogbot må sige til jeres kunder</h1>
            <p className="text-[15px] leading-relaxed text-ink-soft max-w-[600px]">Står det ikke her, siger den det ikke – så tager den en besked til dig i stedet. Kun godkendt viden bruges: <b className="text-ink">{active.items.length} godkendte emner · revision {active.knowledge_revision}</b>.</p>
          </div>
          <div className="flex flex-wrap gap-2">
            {/* The knowledge step leads on to the personal plan (step 3 of the setup guide). */}
            <Link href="/app/setup" className={PILL_BTN}><Icon name="flag" size={18} />Fortsæt til personlig plan</Link>
            {canDraft && <Link href="/app/knowledge?tab=k01" className={PILL_BTN}><Icon name="download" size={18} />Hent fra hjemmesiden</Link>}
            {canDraft && <Link href="/app/knowledge?tab=k03#tilfoej" className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep"><Icon name="add" size={18} />Tilføj viden</Link>}
          </div>
        </div>

        {/* Approval banner */}
        {pending > 0 && tab !== "k05" && (
          <div className="flex flex-wrap items-center gap-3 px-5 py-4 rounded-2xl border-2 border-dashed border-ink bg-paper">
            <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.08em]">Godkend</span>
            <span className="flex-1 min-w-[200px] text-[15px] text-ink"><b>{pending} {pending === 1 ? "ændring" : "ændringer"} venter.</b> Den aktive version bruges uændret, indtil en ejer eller administrator godkender.</span>
            <Link href="/app/knowledge?tab=k05" className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep">Gennemgå nu</Link>
          </div>
        )}

        {/* The four boxes */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
          <Box n={1} title="Om jer" sub="Det, den siger først" href="/onboarding/business">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5">
              <Fact label="Navn" value={profile.legal_name || ws.name} />
              <Fact label="Hvad I laver" value={profile.description || null} empty="Ikke udfyldt endnu" />
              <Fact label="Åbningstider" value={hours ? summarize("opening_hours", hours.content).headline : null} empty="Ingen godkendte åbningstider" />
              <Fact label="Hvor I kører" value={area ? summarize("coverage_area", area.content).headline : null} empty="Ikke angivet" />
            </div>
          </Box>
          <Box n={2} title="Det I sælger" sub={`${services.filter((s) => s.approved_version).length} ydelser godkendt · ${offers.length} tilbud`} href="/app/knowledge?tab=k03">
            {services.length === 0 ? <Empty text="Ingen ydelser endnu – uden dem kan den ikke svare på priser." /> : (
              <ul className="flex flex-col border-t-[1.5px] border-ink">
                {services.slice(0, 4).map((s) => { const v = s.approved_version ?? s.open_draft!; return (
                  <li key={s.id} className="flex items-center gap-3 py-2 border-b-[1.5px] border-ink text-[14px]">
                    <span className="flex-1 min-w-0 font-semibold truncate text-ink">{v.title}</span>
                    <span className="font-display font-bold text-ink">{kr(v.content.price_net_minor) ?? "–"}</span>
                    {!s.approved_version && <span className="inline-flex px-2 py-0.5 rounded-full bg-highlight text-[11px] font-semibold uppercase tracking-[0.06em]">Kladde</span>}
                  </li>); })}
              </ul>
            )}
            {services.length > 4 && <span className="text-[13px] text-muted">+ {services.length - 4} mere</span>}
          </Box>
          <Box n={3} title="Spørgsmål kunderne stiller" sub={`${answers.length} svar godkendt`} href="/app/knowledge?tab=k03">
            {answers.length === 0 ? <Empty text="Ingen faste svar endnu. Tilføj dem som «Kendt svar»." /> : (
              <ul className="flex flex-col border-t-[1.5px] border-ink">
                {answers.slice(0, 3).map((a) => { const s = summarize("known_answer", a.approved_version!.content); return (
                  <li key={a.id} className="flex flex-col gap-0.5 py-2 border-b-[1.5px] border-ink text-[14px]"><span className="font-semibold text-ink">{s.headline}</span><span className="text-ink-soft line-clamp-2">{s.detail}</span></li>); })}
              </ul>
            )}
          </Box>
          <Box n={4} title="Det må den ikke" sub="Her tager den en besked til dig i stedet" href="/app/knowledge?tab=k03" dark>
            {rules.length === 0 ? <Empty text="Ingen regler endnu. Tilføj dem som «Må ikke besvares»." /> : (
              <div className="flex flex-wrap gap-2">
                {rules.map((r) => <span key={r.id} className="inline-flex items-center px-3 py-2 rounded-full border-[1.5px] border-ink text-[14px] font-medium text-ink">{summarize("unknown_answer", r.approved_version!.content).headline}</span>)}
              </div>
            )}
          </Box>
        </div>

        {/* Tabs */}
        <div className="overflow-x-auto no-scrollbar -mx-4 px-4 md:mx-0 md:px-0 pb-1">
          <nav className="inline-flex p-1 rounded-full border-2 border-ink bg-paper min-w-max" aria-label="Vidensfaner">
            {TABS.map(([key, label, short, icon]) => {
              const on = tab === key;
              return (
                <Link key={key} href={`/app/knowledge?tab=${key}`} aria-current={on ? "page" : undefined}
                  className={`inline-flex items-center gap-1.5 min-h-[40px] px-3.5 rounded-full text-[14px] font-semibold whitespace-nowrap ${on ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
                  <Icon name={icon} size={18} /><span className="hidden md:inline">{label}</span><span className="md:hidden">{short}</span>
                  {key === "k05" && pending > 0 && <span className={`inline-flex min-w-5 h-5 px-1.5 rounded-full items-center justify-center font-display text-[11px] font-extrabold ${on ? "bg-highlight text-ink" : "bg-ink text-paper"}`}>{pending}</span>}
                </Link>
              );
            })}
          </nav>
        </div>

        {tab === "k01" && (
          <div className="flex flex-col gap-5">
            {canDraft && <WebsiteImport wsId={ws.id} defaultUrl={profile.website_url ?? ""} initial={latest.import} aiReady={importReady} />}
            <div className={CARD}>
              <div className="flex items-start justify-between gap-3">
                <div>
                  <span className="eyebrow">Godkendt vidensbase</span>
                  <h2 className="font-display text-headline-sm text-ink">Hvor viden kommer fra</h2>
                  <p className="text-[14px] text-ink-soft mt-1 max-w-xl">Dialogbot bruger udelukkende godkendt viden. Hent forslag fra jeres hjemmeside ovenfor, eller indtast viden manuelt. Upload af dokumenter er ikke bygget endnu.</p>
                </div>
                <span className="inline-flex px-2.5 py-1 rounded-full bg-panel border-[1.5px] border-ink text-[12px] font-semibold flex-shrink-0">{latest.import?.status === "done" ? "Hjemmeside + manuel" : "Manuel"}</span>
              </div>
              <div className="grid grid-cols-3 gap-2 md:gap-3 p-3 md:p-4 rounded-xl bg-panel">
                <Stat label="Godkendte emner" value={String(active.items.length)} sub={`Revision ${active.knowledge_revision}`} />
                <Stat label="Åbne kladder" value={String(drafts.length)} sub="Påvirker ikke aktiv viden" />
                <Stat label="Sider læst" value={String(latest.import?.pages.length ?? 0)} sub={latest.import?.finished_at ? `Seneste import ${dateDa(latest.import.finished_at.slice(0, 10))}` : "Ingen import endnu"} />
              </div>
              <div className="p-4 rounded-xl border-[1.5px] border-dashed border-ink flex flex-col items-center text-center gap-1.5">
                <p className="text-[15px] font-semibold text-ink">Ingen eksterne kilder</p>
                <p className="text-[13px] text-ink-soft max-w-md">Automatisk kildeimport med kildehenvisning og konfliktdetektion er ikke implementeret endnu. Der vises derfor ingen fiktive kilder.</p>
              </div>
              <div className="flex items-start gap-2.5 p-3.5 rounded-xl bg-panel border-[1.5px] border-ink">
                <Icon name="shield" size={20} className="text-accent flex-shrink-0 mt-0.5" />
                <div><p className="text-[14px] font-semibold text-ink">Beskyttelse mod utilsigtede ændringer</p><p className="text-[13px] text-ink-soft">En ny kladde ændrer aldrig den aktive viden. Først når en ejer eller administrator godkender, bliver den nye version aktiv – og tidligere bestået tjek markeres som forældede.</p></div>
              </div>
            </div>
          </div>
        )}

        {tab === "k03" && (
          <div className="flex flex-col gap-5" id="tilfoej">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 px-5 py-4 rounded-2xl bg-panel border-[1.5px] border-ink">
              <div className="flex items-center gap-3">
                <span className="inline-flex w-10 h-10 rounded-[10px] bg-accent items-center justify-center text-white shrink-0"><Icon name="lock" size={22} /></span>
                <div><p className="text-[14px] font-semibold text-ink">Kun godkendte priser bruges af Dialogbot</p><p className="text-[13px] text-ink-soft">Ændringer gemmes som kladder og bliver først aktive efter godkendelse. Priser er ekskl. moms.</p></div>
              </div>
              {canDraft && <AddPanel wsId={ws.id} kinds={["service", ...OTHER_KINDS]} label="Tilføj viden" />}
            </div>
            {canDraft && (services.length === 0 || all.some((i) => i.open_draft?.source_type === "extraction")) && <WebsiteImport wsId={ws.id} defaultUrl={profile.website_url ?? ""} initial={latest.import} aiReady={importReady} compact={services.length > 0} />}
            {services.length === 0 && <Empty text="Ingen ydelser endnu. Hent forslag fra hjemmesiden ovenfor, eller tilføj dem manuelt – Dialogbot kan ikke svare på priser uden." />}
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
              {services.map((i) => <ItemCard key={`${i.id}-${i.open_draft?.edit_version ?? i.approved_version?.version_no}`} wsId={ws.id} item={i} canDraft={canDraft} canApprove={canApprove} />)}
            </div>
            {others.length > 0 && (
              <div>
                <h2 className="font-display text-headline-sm text-ink mb-3">Åbningstider, dækning og faste svar</h2>
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
                  {others.map((i) => <ItemCard key={`${i.id}-${i.open_draft?.edit_version ?? i.approved_version?.version_no}`} wsId={ws.id} item={i} canDraft={canDraft} canApprove={canApprove} />)}
                </div>
              </div>
            )}
          </div>
        )}

        {tab === "k04" && (
          <div className={`${CARD} gap-5`}>
            <div className="flex flex-col md:flex-row md:items-start justify-between gap-3">
              <div>
                <span className="eyebrow">Tilbud og rabatter</span>
                <h2 className="font-display text-headline-md text-ink">Automatiske tilbudsregler</h2>
                <p className="text-[14px] text-ink-soft">Et tilbud gælder ved mindst (≥) tærsklen og inden for datoerne – slutdatoen er inklusive. Kun den godkendte version bruges.</p>
              </div>
              {canDraft && <AddPanel wsId={ws.id} kinds={["offer"]} label="Opret tilbudsregel" />}
            </div>
            {offers.length === 0 && <Empty text="Ingen tilbud endnu." />}
            {offers.map((o) => {
              const v = o.approved_version ?? o.open_draft!;
              const c = v.content as { discount_percent?: number; condition?: { area_threshold_m2?: number }; starts_on?: string; ends_on_inclusive?: string };
              const today = new Date().toISOString().slice(0, 10);
              const live = o.approved_version && (!c.starts_on || c.starts_on <= today) && (!c.ends_on_inclusive || today <= c.ends_on_inclusive);
              return (
                <div key={o.id} className="p-4 md:p-5 rounded-2xl border-[1.5px] border-ink flex flex-col gap-3">
                  <div className="flex flex-col md:flex-row md:items-center gap-3">
                    <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center text-ink shrink-0"><Icon name="sell" size={24} /></span>
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-display text-headline-sm text-ink">{v.title}</span>
                        <span className={`inline-flex px-2.5 py-0.5 rounded-full border-[1.5px] text-[11px] font-semibold uppercase tracking-[0.06em] ${live ? "bg-success-soft text-success border-success-soft" : "bg-panel text-ink border-ink"}`}>{live ? "Aktiv nu" : o.approved_version ? "Godkendt – uden for perioden" : "Kladde"}</span>
                        {o.open_draft && o.approved_version && <span className="inline-flex px-2.5 py-0.5 rounded-full bg-highlight text-[11px] font-semibold uppercase tracking-[0.06em]">Ændring afventer</span>}
                      </div>
                      <p className="text-[15px] text-ink mt-1">Gælder automatisk ved arealer på <strong>mindst {c.condition?.area_threshold_m2 ?? 0} m²</strong>. Dialogbot beregner besparelsen i samtalen.</p>
                      <div className="flex flex-wrap items-center gap-3 mt-1.5 text-[13px] text-muted">
                        <span className="flex items-center gap-1"><Icon name="event_available" size={16} />{dateDa(c.starts_on)} – {dateDa(c.ends_on_inclusive)}</span>
                      </div>
                    </div>
                    <div className="rounded-xl px-4 py-2.5 text-center border-2 border-ink self-start md:self-auto">
                      <p className="font-display font-extrabold text-[24px] leading-none text-ink">-{c.discount_percent ?? 0}%</p>
                      <p className="text-[12px] text-muted mt-1">Min. {c.condition?.area_threshold_m2 ?? 0} m²</p>
                    </div>
                  </div>
                  <details className="group">
                    <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center gap-1.5 min-h-[40px] px-3.5 rounded-[10px] bg-paper border-[1.5px] border-ink text-ink text-[13px] font-semibold hover:bg-panel"><Icon name="edit" size={16} />Ret regel</summary>
                    <div className="mt-3"><ItemCard wsId={ws.id} item={o} canDraft={canDraft} canApprove={canApprove} /></div>
                  </details>
                </div>
              );
            })}
          </div>
        )}

        {tab === "k05" && (
          <div className={`${CARD} gap-5`}>
            <div>
              <span className="eyebrow">Godkend</span>
              <h2 className="font-display text-headline-md text-ink">{drafts.length === 0 ? "Ingen ændringer afventer" : `${drafts.length} ${drafts.length === 1 ? "ændring afventer" : "ændringer afventer"} din afgørelse`}</h2>
              <p className="text-[14px] text-ink-soft max-w-2xl">{canApprove ? "Se før og efter. Godkendelse erstatter den aktive version og markerer vidensafhængige tjek som forældede." : "Kun ejere og administratorer kan godkende. Du kan se og indsende kladder."}</p>
            </div>
            {drafts.map((i) => {
              const v = i.open_draft!;
              const cur = i.approved_version;
              const next = summarize(i.kind, v.content);
              const was = cur ? summarize(i.kind, cur.content) : null;
              const inQueue = queue.some((q) => q.id === v.id);
              return (
                <ReviewCard key={v.id} className="rounded-2xl border-2 border-dashed border-ink bg-panel p-4 md:p-5">
                  <div className="flex flex-col gap-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2"><h3 className="font-display text-headline-sm text-ink">{v.title}</h3><span className="inline-flex px-2 py-0.5 rounded-lg bg-paper border-[1.5px] border-ink text-[12px] font-semibold">{KIND_LABEL[i.kind]}</span></div>
                    <span className="text-[13px] text-muted">{inQueue ? "Sendt til gennemgang" : "Kladde – ikke sendt endnu"} · v{v.version_no}</span>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    <div className="bg-paper rounded-xl border-[1.5px] border-ink p-4 flex flex-col gap-2">
                      <div className="flex items-center justify-between"><span className="eyebrow">Før · aktiv nu</span></div>
                      {was ? <><p className={`${i.kind === "service" ? "text-[32px] leading-none" : "text-headline-sm"} font-display font-extrabold text-ink break-words`}>{i.kind === "service" ? `${kr(cur!.content.price_net_minor) ?? "–"} kr` : was.headline}</p>{was.detail && <p className="text-[13px] text-ink-soft">{was.detail}</p>}</> : <p className="text-[13px] text-ink-soft">Nyt emne – ingen aktiv version endnu.</p>}
                      {cur && canApprove && <div className="mt-auto pt-2"><KeepButton wsId={ws.id} v={v} label="Behold den gamle" /></div>}
                    </div>
                    <div className="bg-paper rounded-xl border-2 border-ink p-4 flex flex-col gap-2">
                      <div className="flex items-center justify-between"><span className="eyebrow">Efter · forslag</span><span className="inline-flex px-2 py-0.5 rounded-full bg-highlight text-[11px] font-semibold uppercase tracking-[0.06em]">Kladde</span></div>
                      <p className={`${i.kind === "service" ? "text-[32px] leading-none" : "text-headline-sm"} font-display font-extrabold text-ink break-words`}>{i.kind === "service" ? `${kr(v.content.price_net_minor) ?? "–"} kr` : next.headline}</p>
                      {next.detail && <p className="text-[13px] text-ink-soft">{next.detail}</p>}
                      <div className="mt-auto pt-2">{canApprove ? <ApproveNewButton wsId={ws.id} v={v} label="Godkend" /> : <VersionActions wsId={ws.id} v={v} canApprove={false} />}</div>
                    </div>
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-2 text-[13px] text-ink-soft">
                    <span className="flex items-center gap-1"><Icon name="info" size={18} />En godkendelse gør tidligere beståede tjek forældede.</span>
                    <Link href={`/app/knowledge?tab=${i.kind === "offer" ? "k04" : "k03"}`} className="font-semibold text-ink underline underline-offset-2">Ret manuelt i stedet</Link>
                  </div>
                  </div>
                </ReviewCard>
              );
            })}
            {drafts.length === 0 && <Empty text="Alt er godkendt. Nye kladder fra Viden og Tilbud vises her." />}
            {queue.filter((q) => !byId.get(q.item_id)?.open_draft).length > 0 && <p className="text-[13px] text-muted">Enkelte versioner i køen hører til emner, du ikke kan se.</p>}
          </div>
        )}

        {tab === "r06" && aiStatus !== "not_implemented" && (
          <div className={`${CARD} gap-4`}>
            <div className="flex flex-col md:flex-row md:items-end justify-between gap-2">
              <div>
                <span className="eyebrow">Test</span>
                <h2 className="font-display text-headline-md text-ink">Test den – spørg som en kunde</h2>
              </div>
              {usage && <p className="text-[13px] text-muted">Seneste {usage.days} dage: {usage.totals.calls} kald · {usage.totals.input_tokens + usage.totals.cache_creation_input_tokens + usage.totals.cache_read_input_tokens} ind / {usage.totals.output_tokens} ud tokens · {usd(usage.totals.est_cost_usd_micros)}</p>}
            </div>
            {active.items.length === 0 ? <Empty text="Der er ingen godkendt viden endnu. Godkend mindst ét emne, før Dialogbot kan testes." />
              : !canDraft ? <Empty text="Test kræver rollen medarbejder eller højere." />
              : <AssistantPreview wsId={ws.id} simulated={aiStatus === "simulated"} />}
          </div>
        )}

        {tab === "r05" && (
          <div className={`${CARD} sm:flex-row sm:items-center justify-between`}>
            <div>
              <h2 className="font-display text-headline-md text-ink">Manuskriptet</h2>
              <p className="text-[14px] text-ink-soft max-w-2xl">Hilsen, hvad Dialogbot spørger om, og hvornår et menneske overtager, retter du på Reception-siden.</p>
            </div>
            <Link href="/app/reception" className="inline-flex items-center gap-2 min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep self-start">Åbn manuskriptet <Icon name="arrow_forward" size={18} /></Link>
          </div>
        )}

        {tab === "r06" && aiStatus === "not_implemented" && (
          <div className={`${CARD} gap-4`}>
            <div>
              <span className="eyebrow">Test</span>
              <h2 className="font-display text-headline-md text-ink">Test af Dialogbot</h2>
            </div>
            <div className="p-5 rounded-xl border-[1.5px] border-dashed border-ink flex flex-col md:flex-row items-start gap-3">
              <span className="inline-flex px-2.5 py-1 rounded-full border-[1.5px] border-dashed border-ink text-[11px] font-semibold uppercase tracking-[0.08em] text-muted">Ikke sat op</span>
              <div className="space-y-1">
                <p className="text-[15px] font-semibold text-ink">Ikke tilgængelig endnu</p>
                <p className="text-[13px] text-ink-soft max-w-2xl">Testsamtaler kræver AI-adapteren. Når den er tilkoblet, køres testene mod den godkendte viden, og resultaterne logges pr. version.</p>
                <p className="text-[13px] text-ink-soft">Det du kan gøre nu: hold ydelser, åbningstider og faste svar godkendte – det er det, Dialogbot skal bygge på.</p>
              </div>
            </div>
          </div>
        )}

        {canDraft && tab === "k03" && all.length === 0 && (
          <div className={`${CARD} max-w-xl`}><NewItemForm wsId={ws.id} kinds={["service", ...OTHER_KINDS]} /></div>
        )}
      </section>

      {/* RIGHT: test it as a customer */}
      {tab !== "r06" && (
        <aside aria-label="Test Dialogbot" className="hidden xl:flex flex-[1_1_340px] min-w-0 max-w-[420px] sticky top-[88px] bg-paper border-2 border-ink rounded-2xl shadow-block flex-col overflow-hidden">
          <div className="flex items-center gap-3 px-4 py-3.5 border-b-2 border-ink">
            <span className="inline-flex w-9 h-9 rounded-[10px] bg-accent items-center justify-center font-display font-extrabold text-white">D</span>
            <div className="flex flex-col">
              <span className="font-display font-bold text-[16px] text-ink">Test den – spørg som en kunde</span>
              <span className="text-[12px] text-muted">Svarer kun ud fra det, der er godkendt</span>
            </div>
          </div>
          <div className="p-4">
            {showTest ? <AssistantPreview wsId={ws.id} simulated={aiStatus === "simulated"} />
              : aiStatus === "not_implemented" ? <p className="p-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[13px] text-ink-soft">Test er ikke tilgængelig endnu – AI-adapteren er ikke koblet på.</p>
              : active.items.length === 0 ? <p className="p-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[13px] text-ink-soft">Godkend mindst ét emne, så kan du teste her.</p>
              : <p className="p-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[13px] text-ink-soft">Test kræver rollen medarbejder eller højere.</p>}
          </div>
        </aside>
      )}
    </div>
  );
}

function Box({ n, title, sub, href, dark = false, children }: { n: number; title: string; sub: string; href: string; dark?: boolean; children: React.ReactNode }) {
  return (
    <div className={CARD}>
      <div className="flex flex-wrap items-center gap-3">
        <span className={`inline-flex w-10 h-10 rounded-[10px] items-center justify-center font-display font-extrabold text-[20px] ${dark ? "bg-ink text-paper" : "bg-highlight text-ink"}`} aria-hidden>{n}</span>
        <h2 className="font-display font-extrabold text-[20px] text-ink">{title}</h2>
        <span className="text-[13px] text-muted">{sub}</span>
        <Link href={href} className="ml-auto inline-flex items-center min-h-[36px] px-3 rounded-lg bg-paper border-[1.5px] border-ink text-[13px] font-semibold text-ink hover:bg-panel">Ret</Link>
      </div>
      {children}
    </div>
  );
}

function Fact({ label, value, empty }: { label: string; value: string | null; empty?: string }) {
  return (
    <div className={`flex flex-col gap-0.5 px-3.5 py-3 rounded-xl border-[1.5px] border-ink ${value ? "" : "border-dashed"}`}>
      <span className="eyebrow">{label}</span>
      <span className={`text-[15px] ${value ? "text-ink" : "text-muted"}`}>{value ?? empty ?? "–"}</span>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="p-1 md:p-2">
      <p className="text-[12px] text-muted">{label}</p>
      <p className="font-display font-extrabold text-[24px] leading-none text-ink">{value}</p>
      <p className="text-[12px] text-muted mt-1">{sub}</p>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="px-4 py-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">{text}</p>;
}
