import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Alert, Breadcrumb, Icon, SectionLabel } from "@/components/ui";
import { KnowledgeList, NewItemForm, ReviewQueue } from "./client";

export type Version = { id: string; item_id: string; version_no: number; status: string; title: string; content: Record<string, unknown>; edit_version: number; submitted_at: string | null };
export type Item = { id: string; kind: string; key: string; approved_version: Version | null; open_draft: Version | null };

const TABS: [string, string, string][] = [["k01", "Kilder & URL-crawler (K01–K02)", "cloud_sync"], ["k03", "Ydelseskatalog & priser (K03)", "sell"], ["k04", "Aktive tilbud (K04)", "percent"], ["k05", "Gennemgang & godkendelse (K05)", "fact_check"]];
const KINDS: Record<string, string[]> = { k03: ["service", "coverage_area", "opening_hours", "fact", "known_answer", "unknown_answer"], k04: ["offer"] };

/** K01–K05 — after Stitch "k01_k05_r05_r06_viden_katalog". Only approved knowledge reaches the assistant. */
export default async function KnowledgePage({ searchParams }: { searchParams: Promise<{ tab?: string }> }) {
  const { tab = "k03" } = await searchParams;
  const ws = await requireWorkspace();
  const [items, queue, active] = await Promise.all([
    backend<{ items: Item[]; total: number }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Version[]>(`/workspaces/${ws.id}/knowledge/review-queue`),
    backend<{ knowledge_revision: number; items: unknown[] }>(`/workspaces/${ws.id}/assistant/knowledge`),
  ]);
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const canDraft = ws.role !== "reader";
  const visible = items.items.filter((i) => (KINDS[tab] ?? []).includes(i.kind));
  return (
    <div className="flex flex-col gap-space-lg">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md">
        <div className="space-y-1">
          <Breadcrumb items={[["Viden & Svar"], ["Videnscenter", "/app/knowledge"]]} />
          <div className="flex items-center gap-space-md flex-wrap"><h1 className="font-display text-headline-lg text-primary tracking-tight">Videnscenter &amp; assistentstyring</h1><span className="inline-flex items-center gap-space-xs px-space-md py-0.5 rounded-full bg-surface-container-high text-on-surface text-label-sm"><span className="w-2 h-2 rounded-full bg-primary" />{ws.name}</span></div>
        </div>
        <div className="flex items-center gap-space-md shrink-0">
          <div className="bg-surface-container-lowest px-space-md py-space-sm rounded-xl flex items-center gap-space-md shadow-sm">
            <div className="flex flex-col items-end"><span className="text-label-sm text-on-surface-variant uppercase">Aktiv viden</span><span className="text-label-md text-primary font-bold">{active.items.length} godkendte emner · revision {active.knowledge_revision}</span></div>
            <div className="w-8 h-8 rounded-lg bg-surface-container-low flex items-center justify-center text-primary"><Icon name="verified" /></div>
          </div>
        </div>
      </div>

      {queue.length > 0 && (
        <div className="bg-tertiary-fixed p-space-md rounded-xl flex flex-col md:flex-row items-start md:items-center justify-between gap-space-md shadow-sm">
          <div className="flex items-center gap-space-md"><div className="w-10 h-10 rounded-xl bg-tertiary text-on-tertiary flex items-center justify-center shrink-0"><Icon name="pending_actions" size={22} /></div><div><div className="flex items-center gap-space-sm"><span className="text-label-lg text-on-tertiary-fixed font-bold">Viden afventer godkendelse (K05)</span><span className="px-space-xs py-0.5 rounded-md bg-tertiary text-on-tertiary text-[10px] uppercase font-bold tracking-wider">{queue.length} til gennemgang</span></div><p className="text-body-sm text-on-tertiary-fixed mt-0.5">Kladder bliver først aktiv viden, når en ejer eller administrator har godkendt dem.</p></div></div>
          <Link href="/app/knowledge?tab=k05" className="px-space-md py-space-xs rounded-lg bg-surface-container-lowest text-primary text-label-md hover:bg-surface-container-low shadow-sm shrink-0">Gennemgå nu</Link>
        </div>
      )}

      <div className="overflow-x-auto pb-space-xs">
        <nav className="flex items-center gap-space-xs min-w-max p-1 bg-surface-container-low rounded-xl" aria-label="Vidensfaner">
          {TABS.map(([key, label, icon]) => (
            <Link key={key} href={`/app/knowledge?tab=${key}`} className={`flex items-center gap-space-sm px-space-md py-space-sm rounded-lg text-label-md transition-all ${tab === key ? "bg-primary-container text-on-primary shadow-sm" : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-high"}`}><Icon name={icon} size={18} />{label}{key === "k05" && queue.length > 0 && <span className="ml-1 rounded-full bg-tertiary text-on-tertiary px-1.5 text-label-sm">{queue.length}</span>}</Link>
          ))}
        </nav>
      </div>

      {tab === "k01" && (
        <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div><SectionLabel>K01–K02</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Kilder, URL-crawler og dokumentudtræk</h3></div>
          <Alert kind="info" icon="construction">Kildeimport (hjemmeside, PDF, dokumenter) med udtræk, provenance og konfliktdetektion er ikke implementeret endnu (milepæl B). Der vises derfor ingen kilder eller fiktive udtræk. Den manuelle vej under Ydelseskatalog er fuldt understøttet, og al viden kræver godkendelse.</Alert>
        </div>
      )}
      {(tab === "k03" || tab === "k04") && (
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-space-lg items-start">
          <div className="lg:col-span-8 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
            <div><SectionLabel>{tab === "k03" ? "K03" : "K04"}</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">{tab === "k03" ? "Ydelser, dækning, åbningstider og faste svar" : "Daterede tilbud med betingelser"}</h3><p className="text-body-sm text-on-surface-variant">{tab === "k03" ? "Kun godkendte versioner bruges af assistenten. En ny kladde ændrer aldrig den aktive version, før den er godkendt." : "Tilbud gælder ved mindst tærsklen (fx ≥ 40 m²) og inden for datoerne, slutdato inklusive. Kun den godkendte version evalueres."}</p></div>
            <KnowledgeList wsId={ws.id} items={visible} canDraft={canDraft} canApprove={canApprove} />
          </div>
          <div className="lg:col-span-4 rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg lg:sticky lg:top-20">
            <div><SectionLabel>Nyt emne</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Tilføj manuelt</h3></div>
            {canDraft ? <NewItemForm wsId={ws.id} defaultKind={tab === "k04" ? "offer" : "service"} /> : <p className="text-body-sm text-on-surface-variant">Din rolle (læser) kan ikke oprette viden.</p>}
          </div>
        </div>
      )}
      {tab === "k05" && (
        <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm space-y-space-lg">
          <div><SectionLabel>K05</SectionLabel><h3 className="font-display text-headline-sm text-primary font-bold mt-1">Gennemgangskø</h3><p className="text-body-sm text-on-surface-variant">{canApprove ? "Godkend eller afvis hver version. Godkendelse erstatter den tidligere aktive version og forælder vidensafhængige tjek." : "Kun ejere og administratorer kan godkende. Du kan se køen."}</p></div>
          {queue.length === 0 ? <p className="text-body-sm text-on-surface-variant">Ingen versioner afventer gennemgang.</p> : <ReviewQueue wsId={ws.id} queue={queue} canApprove={canApprove} />}
        </div>
      )}
    </div>
  );
}
