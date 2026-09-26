import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { AssistantPreview, usd } from "./assistant";
import { AddPanel, ApproveNewButton, ItemCard, KeepButton, NewItemForm, VersionActions } from "./client";
import { KIND_LABEL, dateDa, kr, summarize } from "./format";

export type Version = { id: string; item_id: string; version_no: number; status: string; title: string; content: Record<string, unknown>; edit_version: number; submitted_at: string | null };
type Capability = { key: string; status: "available" | "simulated" | "not_implemented" };
type Usage = { days: number; totals: { calls: number; input_tokens: number; output_tokens: number; cache_creation_input_tokens: number; cache_read_input_tokens: number; est_cost_usd_micros: number } };
export type Item = { id: string; kind: string; key: string; approved_version: Version | null; open_draft: Version | null };

const TABS: [string, string, string, string][] = [
  ["k01", "Kilder & URL-crawler", "Kilder", "cloud_sync"],
  ["k03", "Ydelseskatalog & priser", "Katalog", "sell"],
  ["k04", "Aktive tilbud", "Tilbud", "percent"],
  ["k05", "Gennemgang & godkendelse", "Gennemgang", "rule"],
  ["r05", "Receptionsmanuskript", "Manuskript", "support_agent"],
  ["r06", "Manuskripttest", "Test", "play_circle"],
];
const OTHER_KINDS = ["opening_hours", "coverage_area", "fact", "known_answer", "unknown_answer"];

/** K01–K05 (+ honest R05/R06) — Stitch "k01_k05_r05_r06_viden_katalog_receptionsmanuskript". Only approved knowledge reaches the assistant. */
export default async function KnowledgePage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "k03" } = await searchParams;
  const ws = await requireWorkspace();
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const [items, queue, active, caps, usage] = await Promise.all([
    backend<{ items: Item[]; total: number }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Version[]>(`/workspaces/${ws.id}/knowledge/review-queue`),
    backend<{ knowledge_revision: number; items: unknown[] }>(`/workspaces/${ws.id}/assistant/knowledge`),
    tab === "r06" ? backend<{ items: Capability[] }>("/integrations/capabilities") : Promise.resolve({ items: [] as Capability[] }),
    tab === "r06" && canApprove ? backend<Usage>(`/workspaces/${ws.id}/ai/usage?days=30`) : Promise.resolve(null),
  ]);
  const aiStatus = caps.items.find((c) => c.key === "ai.assistant_preview")?.status ?? "not_implemented";
  const canDraft = ws.role !== "reader";
  const all = items.items;
  const drafts = all.filter((i) => i.open_draft);
  const byId = new Map(all.map((i) => [i.id, i]));
  const services = all.filter((i) => i.kind === "service");
  const others = all.filter((i) => OTHER_KINDS.includes(i.kind));
  const offers = all.filter((i) => i.kind === "offer");

  return (
    <div className="flex flex-col gap-space-lg">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="flex flex-col gap-space-xs">
          <div className="hidden md:flex items-center gap-space-xs font-label-md text-label-md text-on-surface-variant">
            <span>Viden &amp; svar</span><Icon name="chevron_right" size={14} />
            <Link href="/app/knowledge" className="hover:text-primary transition-colors text-primary font-semibold">Videnscenter</Link>
          </div>
          <span className="md:hidden font-label-sm text-label-sm text-secondary font-bold uppercase tracking-wider">Styring &amp; konfiguration</span>
          <div className="flex flex-wrap items-center gap-space-md md:mt-space-xs">
            <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight">Videnscenter<span className="hidden md:inline"> &amp; assistentstyring</span></h1>
            <span className="md:hidden inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold"><span className="w-1.5 h-1.5 rounded-full bg-primary" />{active.items.length} godkendt</span>
            <span className="hidden md:inline-flex items-center gap-space-xs px-space-md py-0.5 rounded-full bg-surface-container-high text-on-surface font-label-sm text-label-sm"><span className="w-2 h-2 rounded-full bg-primary" />{ws.name}</span>
          </div>
        </div>
        <div className="hidden md:flex items-center gap-space-md shrink-0">
          <div className="bg-surface-container-lowest px-space-md py-space-sm rounded-xl flex items-center gap-space-md shadow-sm">
            <div className="flex flex-col md:items-end">
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase">Aktiv viden</span>
              <span className="font-label-md text-label-md text-primary font-bold">{active.items.length} godkendte emner · revision {active.knowledge_revision}</span>
            </div>
            <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary"><Icon name="verified" size={20} /></div>
          </div>
        </div>
      </div>

      {/* K05 banner */}
      {queue.length + drafts.filter((d) => d.open_draft?.status === "draft").length > 0 && tab !== "k05" && (
        <div className="bg-error-container/40 p-space-md rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-space-md shadow-sm">
          <div className="flex items-center gap-space-md">
            <div className="w-10 h-10 rounded-xl bg-error text-on-error flex items-center justify-center shrink-0"><Icon name="pending_actions" size={22} /></div>
            <div className="flex flex-col">
              <div className="flex flex-wrap items-center gap-space-sm">
                <span className="font-label-lg text-label-lg text-on-error-container font-bold">Ændringer afventer godkendelse</span>
                <span className="px-space-xs py-0.5 rounded-md bg-error text-on-error font-label-sm text-[10px] uppercase font-bold tracking-wider">{drafts.length} handling påkrævet</span>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface mt-0.5">Kladder bliver først aktiv viden, når en ejer eller administrator har godkendt dem. Den aktive version bruges uændret indtil da.</p>
            </div>
          </div>
          <Link href="/app/knowledge?tab=k05" className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest text-primary font-label-md text-label-md hover:bg-surface-container-low shadow-sm shrink-0">Gennemgå nu</Link>
        </div>
      )}

      {/* Tabs */}
      <div className="overflow-x-auto no-scrollbar -mx-margin px-margin md:mx-0 md:px-0 pb-space-xs">
        <nav className="flex items-center gap-space-xs min-w-max md:p-1 md:bg-surface-container-low md:rounded-xl" aria-label="Vidensfaner">
          {TABS.map(([key, label, short, icon]) => {
            const on = tab === key;
            return (
              <Link key={key} href={`/app/knowledge?tab=${key}`} aria-current={on ? "page" : undefined}
                className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-full md:rounded-lg font-label-md text-label-md transition-all ${on ? "bg-primary-container text-on-primary shadow-sm" : "bg-surface-container md:bg-transparent text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high"}`}>
                <Icon name={icon} size={18} /><span className="hidden md:inline">{label}</span><span className="md:hidden">{short}</span>
                {key === "k05" && drafts.length > 0 && <span className="px-1.5 rounded-full bg-error text-on-error font-label-sm text-[10px] font-bold">{drafts.length}</span>}
              </Link>
            );
          })}
        </nav>
      </div>

      {tab === "k01" && (
        <div className="flex flex-col gap-space-lg">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-space-lg">
            <div className="lg:col-span-2 bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
              <div className="flex items-start justify-between gap-space-md">
                <div>
                  <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Godkendt vidensbase</span>
                  <h2 className="font-headline-sm text-headline-sm md:font-headline-md md:text-headline-md text-primary">Aktive forretningskilder<span className="hidden md:inline"> for {ws.name}</span></h2>
                  <p className="font-body-sm text-body-sm text-on-surface-variant mt-1 max-w-xl">Assistenten bruger udelukkende godkendt viden. I dag indtastes al viden manuelt; automatisk udtræk fra hjemmeside og dokumenter er ikke bygget endnu.</p>
                </div>
                <span className="px-2 py-1 rounded-full bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm font-semibold flex-shrink-0">Kun manuel</span>
              </div>
              <div className="grid grid-cols-3 gap-space-xs md:gap-space-sm p-space-sm md:p-space-md rounded-xl bg-surface-container-low">
                <Stat label="Godkendte emner" value={String(active.items.length)} sub={`Revision ${active.knowledge_revision}`} />
                <Stat label="Åbne kladder" value={String(drafts.length)} sub="Påvirker ikke aktiv viden" />
                <Stat label="Eksterne kilder" value="0" sub="Kildeimport ikke bygget" />
              </div>
            </div>
            <div className="bg-gradient-to-br from-primary-container to-primary text-on-primary rounded-xl p-space-md md:p-space-lg shadow-md flex flex-col justify-between gap-space-md">
              <div>
                <div className="w-10 h-10 rounded-lg bg-surface-container-lowest/15 flex items-center justify-center mb-space-sm"><Icon name="note_add" size={22} className="text-secondary-fixed" /></div>
                <h3 className="font-headline-sm text-headline-sm">Udvid assistentens viden</h3>
                <p className="font-body-sm text-body-sm text-primary-fixed-dim mt-1">Tilføj ydelser, priser, åbningstider og faste svar manuelt. Upload af PDF og URL-crawler kommer senere.</p>
              </div>
              <Link href="/app/knowledge?tab=k03" className="w-full py-2.5 rounded-xl bg-secondary-fixed text-on-secondary-fixed font-label-lg text-label-lg font-bold flex items-center justify-center gap-space-xs hover:brightness-105"><Icon name="add_circle" size={20} />Tilføj viden manuelt</Link>
            </div>
          </div>
          <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
            <div>
              <h3 className="font-headline-sm text-headline-sm text-primary">Tilknyttede kilder &amp; crawlere</h3>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Oversigt over automatiske udtræk og uploadede dokumenter.</p>
            </div>
            <div className="p-space-lg rounded-xl bg-surface-container-low flex flex-col items-center text-center gap-space-sm">
              <Icon name="cloud_off" size={32} className="text-outline" />
              <p className="font-label-lg text-label-lg text-primary">Ingen eksterne kilder</p>
              <p className="font-body-sm text-body-sm text-on-surface-variant max-w-md">Kildeimport med udtræk, kildehenvisning og konfliktdetektion er ikke implementeret endnu. Der vises derfor ingen fiktive kilder eller udtræk.</p>
            </div>
            <div className="flex items-start gap-space-sm p-space-md rounded-lg bg-surface-container-high">
              <Icon name="shield" size={20} className="text-secondary flex-shrink-0 mt-0.5" />
              <div><p className="font-label-md text-label-md text-primary font-bold">Beskyttelse mod utilsigtede ændringer</p><p className="font-body-sm text-body-sm text-on-surface-variant">En ny kladde ændrer aldrig den aktive viden. Først når en ejer eller administrator godkender, bliver den nye version aktiv – og tidligere bestået tjek markeres som forældede.</p></div>
            </div>
          </div>
        </div>
      )}

      {tab === "k03" && (
        <div className="flex flex-col gap-space-lg">
          <div className="p-space-md rounded-xl bg-secondary-container/60 flex flex-col md:flex-row md:items-center justify-between gap-space-md">
            <div className="flex items-center gap-space-md">
              <div className="w-10 h-10 rounded-xl bg-secondary-fixed flex items-center justify-center text-on-secondary-fixed shrink-0"><Icon name="lock" size={22} /></div>
              <div><p className="font-label-md text-label-md text-on-secondary-fixed font-bold">Kun godkendte priser bruges af assistenten</p><p className="font-body-sm text-body-sm text-on-surface">Ændringer gemmes som kladder og bliver først aktive efter godkendelse. Priser er ekskl. moms.</p></div>
            </div>
            {canDraft && <AddPanel wsId={ws.id} kinds={["service", ...OTHER_KINDS]} label="Tilføj viden" />}
          </div>
          {services.length === 0 && <Empty text="Ingen ydelser endnu. Tilføj mindst én – assistenten kan ikke svare på priser uden." />}
          <div className="grid grid-cols-1 xl:grid-cols-2 gap-space-lg">
            {services.map((i) => <ItemCard key={`${i.id}-${i.open_draft?.edit_version ?? i.approved_version?.version_no}`} wsId={ws.id} item={i} canDraft={canDraft} canApprove={canApprove} />)}
          </div>
          <div>
            <h2 className="font-headline-sm text-headline-sm text-primary mb-space-md">Åbningstider, dækning og faste svar</h2>
            <div className="grid grid-cols-1 xl:grid-cols-2 gap-space-lg">
              {others.map((i) => <ItemCard key={`${i.id}-${i.open_draft?.edit_version ?? i.approved_version?.version_no}`} wsId={ws.id} item={i} canDraft={canDraft} canApprove={canApprove} />)}
            </div>
          </div>
        </div>
      )}

      {tab === "k04" && (
        <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-lg">
          <div className="flex flex-col md:flex-row md:items-start justify-between gap-space-md">
            <div>
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Kampagne- &amp; tilbudseditor</span>
              <h2 className="font-headline-md text-headline-md text-primary">Automatiserede tilbudsregler</h2>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Et tilbud gælder ved mindst (≥) tærsklen og inden for datoerne – slutdatoen er inklusive. Kun den godkendte version evalueres.</p>
            </div>
            {canDraft && <AddPanel wsId={ws.id} kinds={["offer"]} label="Opret ny tilbudsregel" />}
          </div>
          {offers.length === 0 && <Empty text="Ingen tilbud endnu." />}
          {offers.map((o) => {
            const v = o.approved_version ?? o.open_draft!;
            const c = v.content as { discount_percent?: number; condition?: { area_threshold_m2?: number }; starts_on?: string; ends_on_inclusive?: string };
            const today = new Date().toISOString().slice(0, 10);
            const live = o.approved_version && (!c.starts_on || c.starts_on <= today) && (!c.ends_on_inclusive || today <= c.ends_on_inclusive);
            return (
              <div key={o.id} className="p-space-md md:p-space-lg rounded-xl bg-surface-container-low flex flex-col gap-space-md">
                <div className="flex flex-col md:flex-row md:items-center gap-space-md">
                  <div className="w-12 h-12 rounded-xl bg-secondary-fixed flex items-center justify-center text-on-secondary-fixed shrink-0"><Icon name="sell" size={24} /></div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-space-sm">
                      <span className="font-headline-sm text-headline-sm text-primary">{v.title}</span>
                      <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-bold ${live ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-highest text-on-surface-variant"}`}>{live ? "Aktiv kampagnerabat" : o.approved_version ? "Godkendt – uden for perioden" : "Kladde"}</span>
                      {o.open_draft && o.approved_version && <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed font-label-sm text-label-sm font-bold">Ændring afventer</span>}
                    </div>
                    <p className="font-body-md text-body-md text-on-surface mt-1">Gælder automatisk ved arealer på <strong>mindst {c.condition?.area_threshold_m2 ?? 0} m²</strong>. Assistenten beregner besparelsen i samtalen.</p>
                    <div className="flex flex-wrap items-center gap-space-md mt-space-sm font-label-sm text-label-sm text-on-surface-variant">
                      <span className="flex items-center gap-1"><Icon name="event_available" size={16} />{dateDa(c.starts_on)} – {dateDa(c.ends_on_inclusive)}</span>
                      <span className="flex items-center gap-1"><Icon name="domain" size={16} />{ws.name}</span>
                    </div>
                  </div>
                  <div className="bg-surface-container-lowest rounded-xl px-space-md py-space-sm text-center shadow-sm self-start md:self-auto">
                    <p className="font-headline-md text-headline-md text-primary font-bold">-{c.discount_percent ?? 0}%</p>
                    <p className="font-label-sm text-label-sm text-on-surface-variant">Min. {c.condition?.area_threshold_m2 ?? 0} m²</p>
                  </div>
                </div>
                <details className="group">
                  <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-surface-container text-primary font-label-md text-label-md font-semibold hover:bg-surface-container-high"><Icon name="edit" size={16} />Redigér regel</summary>
                  <div className="mt-space-md"><ItemCard wsId={ws.id} item={o} canDraft={canDraft} canApprove={canApprove} /></div>
                </details>
              </div>
            );
          })}
        </div>
      )}

      {tab === "k05" && (
        <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-lg">
          <div className="flex items-start justify-between gap-space-md">
            <div>
              <span className="font-label-sm text-label-sm text-error uppercase tracking-wider font-bold">Ændringsgennemgang</span>
              <h2 className="font-headline-md text-headline-md text-primary">{drafts.length === 0 ? "Ingen ændringer afventer" : `${drafts.length} ${drafts.length === 1 ? "ændring afventer" : "ændringer afventer"} din afgørelse`}</h2>
              <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">{canApprove ? "Sammenlign den aktive version med forslaget. Godkendelse erstatter den aktive version og markerer vidensafhængige tjek som forældede." : "Kun ejere og administratorer kan godkende. Du kan se og indsende kladder."}</p>
            </div>
          </div>
          {drafts.map((i) => {
            const v = i.open_draft!;
            const cur = i.approved_version;
            const next = summarize(i.kind, v.content);
            const was = cur ? summarize(i.kind, cur.content) : null;
            const inQueue = queue.some((q) => q.id === v.id);
            return (
              <div key={v.id} className="rounded-xl bg-surface-container-low p-space-md md:p-space-lg flex flex-col gap-space-md">
                <div className="flex flex-wrap items-center justify-between gap-space-sm">
                  <div className="flex items-center gap-space-sm"><Icon name="difference" size={22} className="text-error" /><h3 className="font-headline-sm text-headline-sm text-primary">{v.title}</h3><span className="px-2 py-0.5 rounded bg-surface-container-high font-label-sm text-label-sm">{KIND_LABEL[i.kind]}</span></div>
                  <span className="font-label-sm text-label-sm text-on-surface-variant">{inQueue ? "Sendt til gennemgang" : "Kladde – ikke sendt endnu"} · v{v.version_no}</span>
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-space-md">
                  <div className="bg-surface-container-lowest rounded-xl p-space-md flex flex-col gap-space-sm">
                    <div className="flex items-center justify-between"><span className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Nuværende godkendte version</span>{cur && <span className="px-1.5 rounded bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold">Aktiv nu</span>}</div>
                    {was ? <><p className={`${i.kind === "service" ? "font-display-lg text-display-lg" : "font-headline-sm text-headline-sm"} text-primary font-bold break-words`}>{i.kind === "service" ? `${kr(cur!.content.price_net_minor) ?? "–"} kr` : was.headline}</p>{was.detail && <p className="font-body-sm text-body-sm text-on-surface-variant">{was.detail}</p>}</> : <p className="font-body-sm text-body-sm text-on-surface-variant">Nyt emne – ingen aktiv version endnu.</p>}
                    {cur && canApprove && <div className="mt-auto pt-space-sm"><KeepButton wsId={ws.id} v={v} label="Behold eksisterende" /></div>}
                  </div>
                  <div className="bg-surface-container-lowest rounded-xl p-space-md flex flex-col gap-space-sm">
                    <div className="flex items-center justify-between"><span className="font-label-sm text-label-sm uppercase tracking-wider text-error font-bold">Foreslået ny version</span><span className="px-1.5 rounded bg-error-container text-on-error-container font-label-sm text-label-sm font-bold">Manuel kladde</span></div>
                    <p className={`${i.kind === "service" ? "font-display-lg text-display-lg" : "font-headline-sm text-headline-sm"} text-error font-bold break-words`}>{i.kind === "service" ? `${kr(v.content.price_net_minor) ?? "–"} kr` : next.headline}</p>
                    {next.detail && <p className="font-body-sm text-body-sm text-on-surface-variant">{next.detail}</p>}
                    <div className="mt-auto pt-space-sm">{canApprove ? <ApproveNewButton wsId={ws.id} v={v} label="Godkend ny version" /> : <VersionActions wsId={ws.id} v={v} canApprove={false} />}</div>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-space-sm font-body-sm text-body-sm text-on-surface-variant">
                  <span className="flex items-center gap-1"><Icon name="info" size={18} />En godkendelse gør tidligere beståede tjek forældede.</span>
                  <Link href={`/app/knowledge?tab=${i.kind === "offer" ? "k04" : "k03"}`} className="font-label-md text-label-md text-primary font-semibold hover:underline">Redigér manuelt i stedet →</Link>
                </div>
              </div>
            );
          })}
          {drafts.length === 0 && <Empty text="Alt er godkendt. Nye kladder fra Katalog og Tilbud vises her." />}
          {queue.filter((q) => !byId.get(q.item_id)?.open_draft).length > 0 && <p className="font-body-sm text-body-sm text-on-surface-variant">Enkelte versioner i køen hører til emner, du ikke kan se.</p>}
        </div>
      )}

      {tab === "r06" && aiStatus !== "not_implemented" && (
        <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
          <div className="flex flex-col md:flex-row md:items-end justify-between gap-space-sm">
            <div>
              <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">Test</span>
              <h2 className="font-headline-md text-headline-md text-primary">Test assistenten</h2>
            </div>
            {usage && <p className="font-body-sm text-body-sm text-on-surface-variant">Seneste {usage.days} dage: {usage.totals.calls} kald · {usage.totals.input_tokens + usage.totals.cache_creation_input_tokens + usage.totals.cache_read_input_tokens} ind / {usage.totals.output_tokens} ud tokens · {usd(usage.totals.est_cost_usd_micros)}</p>}
          </div>
          {active.items.length === 0 ? <Empty text="Der er ingen godkendt viden endnu. Godkend mindst ét emne under Katalog og Gennemgang, før assistenten kan testes." />
            : !canDraft ? <Empty text="Test af assistenten kræver rollen medarbejder eller højere." />
            : <AssistantPreview wsId={ws.id} simulated={aiStatus === "simulated"} />}
        </div>
      )}

      {(tab === "r05" || (tab === "r06" && aiStatus === "not_implemented")) && (
        <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
          <div>
            <span className="font-label-sm text-label-sm text-on-surface-variant uppercase tracking-wider">{tab === "r05" ? "Manuskript" : "Test"}</span>
            <h2 className="font-headline-md text-headline-md text-primary">{tab === "r05" ? "Receptionsmanuskript & persona" : "Manuskripttest & simulation"}</h2>
          </div>
          <div className="p-space-lg rounded-xl bg-surface-container-low flex flex-col md:flex-row items-start gap-space-md">
            <Icon name="construction" size={28} className="text-secondary flex-shrink-0" />
            <div className="space-y-1">
              <p className="font-label-lg text-label-lg text-primary">Ikke tilgængelig endnu</p>
              <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">{tab === "r05" ? "Manuskriptet (velkomst, introduktion, behovsafdækning, vidensgrænser og menneskelig overtagelse) kræver AI-/stemmeadapteren, som ikke er tilkoblet. Indtil da vises der intet udkast, der kunne forveksles med et aktivt manuskript." : "Testsamtaler mod assistenten kræver AI-adapteren. Når den er tilkoblet, køres testene mod den godkendte viden, og resultaterne logges pr. version."}</p>
              <p className="font-body-sm text-body-sm text-on-surface-variant">Det du kan gøre nu: hold ydelser, åbningstider og faste svar godkendte under Katalog – det er det, assistenten skal bygge på.</p>
            </div>
          </div>
        </div>
      )}

      {canDraft && tab === "k03" && all.length === 0 && (
        <div className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm max-w-xl"><NewItemForm wsId={ws.id} kinds={["service", ...OTHER_KINDS]} /></div>
      )}
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub: string }) {
  return (
    <div className="p-space-xs md:p-space-sm">
      <p className="font-label-sm text-label-sm text-on-surface-variant">{label}</p>
      <p className="font-headline-sm text-headline-sm md:font-headline-md md:text-headline-md text-primary font-bold">{value}</p>
      <p className="font-body-sm text-body-sm text-on-surface-variant">{sub}</p>
    </div>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="p-space-md rounded-xl bg-surface-container-low font-body-sm text-body-sm text-on-surface-variant">{text}</p>;
}
