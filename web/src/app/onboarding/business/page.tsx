import Link from "next/link";
import { backend, currentWorkspaceId } from "@/lib/api.server";
import { requireWorkspace, type Workspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { FlowBar, INTENT_LABEL } from "@/components/onboarding";
import { Bag } from "@/components/lego";
import { WorkspaceCards } from "../workspace/form";
import { ApproveButton, BusinessForm, Categories, SelfManagedButton } from "./form";

type Version = { id: string; status: string; title: string; content: Record<string, unknown>; source_type?: string };
type Item = { id: string; kind: string; approved_version: Version | null; open_draft: Version | null };

const DAY: Record<string, string> = { mon: "man", tue: "tir", wed: "ons", thu: "tor", fri: "fre", sat: "lør", sun: "søn" };
function daysLabel(days: string[]) {
  const order = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
  const idx = days.map((d) => order.indexOf(d)).sort((a, b) => a - b);
  const contiguous = idx.every((v, i) => i === 0 || v === idx[i - 1] + 1);
  return contiguous && idx.length > 2 ? `${DAY[order[idx[0]]]}–${DAY[order[idx[idx.length - 1]]]}` : idx.map((i) => DAY[order[i]]).join(", ");
}
const kr = (minor: unknown) => typeof minor === "number" ? `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0 })},- kr.` : null;
const UNIT: Record<string, string> = { m2: "pr. m²", hour: "pr. time", item: "pr. stk.", job: "pr. opgave" };

/** A06 + O01 + O02 — Stitch "a06_o01_o02_virksomhed_arbejdsrum_viden" (desktop and mobil). */
export default async function BusinessPage() {
  const ws = await requireWorkspace();
  const [profile, cats, suggested, workspaces, me, items, goals, currentId, caps, latestImport] = await Promise.all([
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/profile`),
    backend<{ id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean }[]>(`/workspaces/${ws.id}/categories`),
    backend<{ items: { slug: string; label: string }[] }>(`/workspaces/${ws.id}/categories/suggested`),
    backend<Workspace[]>("/workspaces"),
    backend<{ signup_intent: string | null }>("/auth/me"),
    backend<{ items: Item[] }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/goals`),
    currentWorkspaceId(),
    backend<{ items: { key: string; status: string }[] }>("/integrations/capabilities"),
    backend<{ import: unknown }>(`/workspaces/${ws.id}/knowledge/imports/latest`),
  ]);
  const capOn = (k: string) => caps.items.some((c) => c.key === k && c.status !== "not_implemented");
  const canEdit = ws.role !== "reader";
  const canApprove = ws.role === "owner" || ws.role === "admin";
  const byKind = (k: string) => items.items.filter((i) => i.kind === k);
  const hours = byKind("opening_hours")[0];
  const services = byKind("service");
  const coverage = byKind("coverage_area")[0];
  const zones = ((coverage?.approved_version ?? coverage?.open_draft)?.content.zones as string[] | undefined) ?? [];
  const approvedCount = items.items.filter((i) => i.approved_version).length;
  const pendingCount = items.items.filter((i) => i.open_draft).length;
  const roleLabel = { owner: "Ejer", admin: "Administrator", staff: "Medarbejder", reader: "Læser" }[ws.role] ?? ws.role;

  return (
    <div className="space-y-space-xl pb-space-md">
      <FlowBar step={1} intent={me.signup_intent} />

      {/* A06 — mobil: compact card for the active workspace */}
      <div className="md:hidden bg-surface-container-lowest rounded-2xl p-space-md border-2 border-ink flex flex-col gap-space-sm relative overflow-hidden">
        <div className="flex items-start justify-between gap-space-sm">
          <div className="flex items-center gap-space-sm min-w-0">
            <div className="w-10 h-10 rounded-[10px] bg-accent text-white flex items-center justify-center flex-shrink-0"><Icon name="domain" size={22} /></div>
            <div className="min-w-0">
              <p className="font-headline-sm text-headline-sm text-primary font-bold truncate">{ws.name}</p>
              <p className="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1"><Icon name="verified_user" size={14} className="text-secondary" />Rolle: {roleLabel}</p>
            </div>
          </div>
          <Link href="/onboarding/workspace" aria-label="Skift eller opret arbejdsrum" className="w-11 h-11 rounded-xl border-2 border-ink bg-white hover:bg-panel flex items-center justify-center text-ink flex-shrink-0"><Icon name="swap_horiz" size={20} /></Link>
        </div>
        {me.signup_intent && <span className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-full border-[1.5px] border-ink bg-panel text-ink font-label-sm text-label-sm font-semibold"><Icon name="bookmark_added" size={16} className="text-accent" />Beholdt hensigt: {INTENT_LABEL[me.signup_intent] ?? me.signup_intent}</span>}
      </div>

      {/* A06 workspace overview */}
      <div className="hidden md:block bg-surface-container-lowest p-space-xl rounded-2xl border-2 border-ink space-y-space-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between md:pb-space-md gap-4">
          <div>
            <div className="flex items-center gap-space-sm">
              <span className="px-2.5 py-0.5 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.12em]">Arbejdsrum</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Arbejdsrumsoversigt</span>
            </div>
            <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink mt-0.5">Vælg eller opret arbejdsrum</h1>
          </div>
          <div className="flex items-center gap-space-md flex-wrap">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-xl border-[1.5px] border-ink bg-panel text-ink"><Icon name="verified_user" size={18} className="text-accent" /><span className="font-label-md text-label-md font-semibold">Rolle: {roleLabel}</span></div>
            <Link href="/onboarding/workspace" className="min-h-[44px] px-4 rounded-xl border-2 border-ink bg-white hover:bg-panel text-ink font-label-md text-label-md font-semibold flex items-center gap-1.5 transition-colors no-underline"><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link>
          </div>
        </div>
        <WorkspaceCards workspaces={workspaces} currentId={currentId ?? ws.id} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-xl">
        {/* O01 */}
        <div className="xl:col-span-5 flex flex-col gap-space-xl">
          <div className="bg-surface-container-lowest p-space-md md:p-space-xl rounded-2xl border-2 border-ink space-y-space-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-space-sm">
                <Bag n={1} size={36} />
                <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Virksomhedsopsætning</h2>
              </div>
              <span className="eyebrow flex items-center gap-1"><Icon name="tune" size={14} />Basale parametre</span>
            </div>
            <BusinessForm wsId={ws.id} profile={profile} canEdit={canEdit} aiReady={capOn("knowledge.source_import")} cvrReady={capOn("cvr.lookup")} autoFetch={!latestImport.import && !profile.manual_setup && Boolean(profile.website_url) && !String(profile.description ?? "").trim()} />
            <div className="space-y-space-md pt-2">
              <div className="flex items-center justify-between">
                <span className="block font-label-md text-label-md text-on-surface font-semibold">Branchekategorier &amp; servicescope</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">{cats.length} valgt</span>
              </div>
              <Categories wsId={ws.id} categories={cats} suggested={suggested.items} canEdit={canEdit} />
            </div>
            <div className="p-space-md rounded-xl border-[1.5px] border-ink bg-panel space-y-2">
              <span className="font-label-md text-label-md text-ink font-bold flex items-center gap-1"><Icon name="location_on" size={16} className="text-accent" />Lokation og dækningsområde</span>
              {zones.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">{zones.map((z, i) => <span key={z} className="px-2.5 py-1 rounded-lg bg-white border-[1.5px] border-ink text-primary font-label-sm text-label-sm font-semibold">Zone {i + 1}: {z}</span>)}</div>
              ) : <p className="font-body-sm text-body-sm text-on-surface-variant">Intet dækningsområde endnu.</p>}
              <Link href="/app/knowledge?tab=k03" className="text-[14px] text-accent font-semibold underline underline-offset-4 inline-flex items-center gap-1 min-h-[44px]">Redigér i Videnscenter<Icon name="arrow_forward" size={14} /></Link>
            </div>
          </div>
        </div>

        {/* O02 — knowledge the assistant may use (entered manually; no automatic extraction yet) */}
        <div className="xl:col-span-7 flex flex-col gap-space-xl">
          <div className="bg-surface-container-lowest p-space-md md:p-space-xl rounded-2xl border-2 border-ink space-y-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 gap-2">
              <div className="flex items-center gap-space-sm">
                <Bag n={2} size={36} />
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Fakta og redigerbar viden</h2>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">Valider hvad assistenten må gengive til kunder.</p>
                </div>
              </div>
              <span className="px-2.5 py-1 rounded-full border-[1.5px] border-ink bg-panel text-ink font-label-sm text-label-sm font-semibold self-start sm:self-auto">{approvedCount} godkendt • {pendingCount} kræver handling</span>
            </div>
            <div className="p-space-md rounded-xl border-[1.5px] border-ink bg-panel flex items-start gap-space-md">
              <Icon name="lock_reset" size={22} className="text-accent mt-0.5" />
              <div className="flex-1">
                <p className="font-label-md text-label-md text-primary font-bold">Kun godkendte versioner bruges</p>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">En ny kladde ændrer aldrig den aktive viden, før en ejer eller administrator har godkendt den. Forslag fra hjemmesiden lægges også som kladder her.</p>
              </div>
            </div>

            {/* Opening hours */}
            <div className="p-space-md rounded-xl border-[1.5px] border-ink bg-white space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><Icon name="schedule" size={18} className="text-accent" /><span className="font-label-md text-label-md text-primary font-bold">Åbningstider &amp; telefontider</span></div>
                <FactStatus item={hours} />
              </div>
              {hours ? (() => {
                const c = (hours.approved_version ?? hours.open_draft)!.content as { weekly?: { days: string[]; open: string; close: string }[]; closed_note?: string };
                return (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    {(c.weekly ?? []).map((w, i) => (
                      <div key={i} className="bg-panel p-2.5 rounded-lg">
                        <span className="font-label-sm text-label-sm text-on-surface-variant block capitalize">{daysLabel(w.days)}</span>
                        <span className="font-headline-sm text-headline-sm text-primary font-bold">{w.open} – {w.close}</span>
                      </div>
                    ))}
                    {c.closed_note && (
                      <div className="bg-panel p-2.5 rounded-lg">
                        <span className="font-label-sm text-label-sm text-on-surface-variant block">Øvrig tid</span>
                        <span className="font-headline-sm text-headline-sm text-on-surface-variant font-medium">{c.closed_note}</span>
                      </div>
                    )}
                  </div>
                );
              })() : <EmptyFact text="Ingen åbningstider endnu." />}
              {hours?.open_draft && canApprove && <div className="flex justify-end"><ApproveButton wsId={ws.id} versionId={hours.open_draft.id} label="Godkend åbningstider" /></div>}
            </div>

            {/* Services & prices */}
            <div className="p-space-md rounded-xl border-[1.5px] border-ink bg-panel space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Icon name="payments" size={20} className="text-accent" />
                  <div>
                    <span className="font-label-md text-label-md text-primary font-bold">Ydelser og vejledende priser</span>
                    {services.some((s) => s.open_draft) && <span className="font-label-sm text-label-sm text-on-error-container block font-bold">Ugodkendte ændringer – kræver godkendelse</span>}
                  </div>
                </div>
                <span className="font-label-sm text-label-sm text-muted bg-white border-[1.5px] border-ink px-2 py-0.5 rounded-lg self-start sm:self-auto">{services.some((s) => (s.open_draft ?? s.approved_version)?.source_type === "extraction") ? "Kilde: hjemmeside + manuel" : "Kilde: indtastet manuelt"}</span>
              </div>
              <div className="space-y-2">
                {services.length === 0 && <EmptyFact text="Ingen ydelser endnu – tilføj mindst én i Videnscenter." />}
                {services.map((s) => {
                  const v = s.open_draft ?? s.approved_version!;
                  const c = v.content as { description?: string; price_net_minor?: number; unit?: string };
                  return (
                    <div key={s.id} className="p-3 rounded-xl bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-[1.5px] border-ink">
                      <div className="min-w-0">
                        <p className="font-label-md text-label-md text-primary font-bold">{v.title}</p>
                        {c.description && <p className="font-body-sm text-body-sm text-on-surface-variant">{c.description}</p>}
                      </div>
                      <div className="flex items-center gap-3 self-end sm:self-auto">
                        {kr(c.price_net_minor) && <div className="text-right"><span className="font-headline-sm text-headline-sm text-primary font-bold">{kr(c.price_net_minor)}</span><span className="font-label-sm text-label-sm text-on-surface-variant block">{UNIT[c.unit ?? ""] ?? ""} ekskl. moms</span></div>}
                        {s.open_draft
                          ? canApprove ? <ApproveButton wsId={ws.id} versionId={s.open_draft.id} label="Godkend" /> : <span className="px-2.5 py-0.5 rounded-full bg-highlight text-ink text-[12px] font-semibold uppercase tracking-[0.06em]">Afventer godkendelse</span>
                          : <span className="px-2.5 py-0.5 rounded-full bg-success-soft text-success text-[12px] font-semibold uppercase tracking-[0.06em]">Godkendt</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-end pt-1">
                <Link href="/app/knowledge?tab=k03" className="text-accent underline underline-offset-4 text-[14px] font-semibold inline-flex items-center gap-1 min-h-[44px]"><Icon name="edit_note" size={14} />Rediger priser i Videnscenter</Link>
              </div>
            </div>

            {/* Escalation — needs telephony */}
            <div className="p-space-md rounded-xl border-[1.5px] border-dashed border-ink bg-white space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><Icon name="support_agent" size={18} className="text-muted" /><span className="font-label-md text-label-md text-primary font-bold">Eskalering ved akutte henvendelser</span></div>
                <span className="px-2.5 py-0.5 rounded-full border-[1.5px] border-dashed border-ink bg-white text-muted text-[12px] font-semibold uppercase tracking-[0.06em]">Ikke tilgængelig endnu</span>
              </div>
              <p className="p-2.5 rounded-lg bg-panel font-body-sm text-body-sm text-on-surface-variant">Viderestilling til vagttelefon kræver telefoni, som ikke er tilkoblet. Reglen kan oprettes, når telefoni-adapteren er bygget.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky action bar */}
      <div className="md:sticky md:bottom-4 z-40 w-full bg-white border-2 border-ink p-space-md rounded-2xl flex flex-col-reverse md:flex-row items-center justify-between gap-space-md">
        <div className="flex items-center gap-space-md w-full md:w-auto">
          {canEdit && <SelfManagedButton wsId={ws.id} goals={goals} />}
          <span className="hidden md:inline font-body-sm text-body-sm text-on-surface-variant">Dine indtastninger gemmes serverside uanset valg.</span>
        </div>
        <div className="flex flex-col-reverse md:flex-row items-stretch md:items-center gap-space-md w-full md:w-auto md:justify-end">
          <button form="business-form" type="submit" name="intent" value="save" disabled={!canEdit} className="min-h-[44px] px-4 rounded-xl border-2 border-ink bg-white hover:bg-panel text-ink font-label-md text-label-md font-semibold transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"><Icon name="save" size={18} />Gem</button>
          <button form="business-form" type="submit" name="intent" value="next" className="justify-center min-h-[52px] px-[22px] rounded-[14px] bg-accent hover:bg-accent-deep text-white text-[17px] font-semibold transition-colors flex items-center gap-2.5">
            <span>Gem og fortsæt til mål &amp; sprog</span><Icon name="arrow_forward" size={20} />
          </button>
        </div>
      </div>
    </div>
  );
}

function FactStatus({ item }: { item?: Item }) {
  if (!item) return <span className="px-2.5 py-0.5 rounded-full border-[1.5px] border-dashed border-ink bg-white text-muted text-[12px] font-semibold uppercase tracking-[0.06em]">Mangler</span>;
  return item.open_draft
    ? <span className="px-2.5 py-0.5 rounded-full bg-danger-soft text-on-error-container text-[12px] font-semibold uppercase tracking-[0.06em]">Ugodkendt ændring</span>
    : <span className="px-2.5 py-0.5 rounded-full bg-success-soft text-success text-[12px] font-semibold uppercase tracking-[0.06em] flex items-center gap-1"><Icon name="check_circle" size={12} />Godkendt</span>;
}

function EmptyFact({ text }: { text: string }) {
  return <p className="p-2.5 rounded-lg bg-panel font-body-sm text-body-sm text-on-surface-variant">{text}</p>;
}
