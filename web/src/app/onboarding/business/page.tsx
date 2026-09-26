import Link from "next/link";
import { backend, currentWorkspaceId } from "@/lib/api.server";
import { requireWorkspace, type Workspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { FlowBar, INTENT_LABEL } from "@/components/onboarding";
import { WorkspaceCards } from "../workspace/form";
import { ApproveButton, BusinessForm, Categories, SelfManagedButton } from "./form";

type Version = { id: string; status: string; title: string; content: Record<string, unknown> };
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
  const [profile, cats, suggested, workspaces, me, items, goals, currentId] = await Promise.all([
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/profile`),
    backend<{ id: string; label: string; slug: string; is_custom: boolean; is_primary: boolean }[]>(`/workspaces/${ws.id}/categories`),
    backend<{ items: { slug: string; label: string }[] }>(`/workspaces/${ws.id}/categories/suggested`),
    backend<Workspace[]>("/workspaces"),
    backend<{ signup_intent: string | null }>("/auth/me"),
    backend<{ items: Item[] }>(`/workspaces/${ws.id}/knowledge/items?limit=200`),
    backend<Record<string, unknown>>(`/workspaces/${ws.id}/goals`),
    currentWorkspaceId(),
  ]);
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
      <div className="md:hidden bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col gap-space-sm relative overflow-hidden">
        <div className="flex items-start justify-between gap-space-sm">
          <div className="flex items-center gap-space-sm min-w-0">
            <div className="w-10 h-10 rounded-lg bg-primary-container text-secondary-fixed flex items-center justify-center flex-shrink-0"><Icon name="domain" size={22} /></div>
            <div className="min-w-0">
              <p className="font-headline-sm text-headline-sm text-primary font-bold truncate">{ws.name}</p>
              <p className="font-label-sm text-label-sm text-on-surface-variant flex items-center gap-1"><Icon name="verified_user" size={14} className="text-secondary" />Rolle: {roleLabel}</p>
            </div>
          </div>
          <Link href="/onboarding/workspace" aria-label="Skift eller opret arbejdsrum" className="w-9 h-9 rounded-lg bg-surface-container flex items-center justify-center text-primary flex-shrink-0"><Icon name="swap_horiz" size={20} /></Link>
        </div>
        {me.signup_intent && <span className="self-start flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-semibold"><Icon name="bookmark_added" size={16} />Beholdt hensigt: {INTENT_LABEL[me.signup_intent] ?? me.signup_intent}</span>}
      </div>

      {/* A06 workspace overview */}
      <div className="hidden md:block bg-surface-container-lowest p-space-xl rounded-xl shadow-sm space-y-space-lg">
        <div className="flex flex-col md:flex-row md:items-center justify-between md:pb-space-md gap-4">
          <div>
            <div className="flex items-center gap-space-sm">
              <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold uppercase tracking-wider">Arbejdsrum</span>
              <span className="font-label-sm text-label-sm text-on-surface-variant">Arbejdsrumsoversigt</span>
            </div>
            <h1 className="font-headline-lg-mobile text-headline-lg-mobile md:font-headline-lg md:text-headline-lg text-primary tracking-tight mt-0.5">Vælg eller opret arbejdsrum</h1>
          </div>
          <div className="flex items-center gap-space-md flex-wrap">
            <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-surface-container text-primary"><Icon name="verified_user" size={18} /><span className="font-label-md text-label-md font-semibold">Rolle: {roleLabel}</span></div>
            <Link href="/onboarding/workspace" className="px-space-md py-1.5 rounded-lg bg-surface-container-low hover:bg-surface-container text-primary font-label-md text-label-md flex items-center gap-1.5 transition-colors"><Icon name="add_circle" size={18} />Nyt arbejdsrum</Link>
          </div>
        </div>
        <WorkspaceCards workspaces={workspaces} currentId={currentId ?? ws.id} />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-space-xl">
        {/* O01 */}
        <div className="xl:col-span-5 flex flex-col gap-space-xl">
          <div className="bg-surface-container-lowest p-space-md md:p-space-xl rounded-xl shadow-sm space-y-space-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-space-sm">
                <span className="w-7 h-6 rounded-md bg-primary-container text-on-primary flex items-center justify-center font-label-sm text-[10px] font-bold">1</span>
                <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Virksomhedsopsætning</h2>
              </div>
              <span className="font-label-sm text-label-sm text-secondary font-bold flex items-center gap-1"><Icon name="tune" size={14} />Basale parametre</span>
            </div>
            <BusinessForm wsId={ws.id} profile={profile} canEdit={canEdit} />
            <div className="space-y-space-md pt-2">
              <div className="flex items-center justify-between">
                <span className="block font-label-md text-label-md text-on-surface font-semibold">Branchekategorier &amp; servicescope</span>
                <span className="font-label-sm text-label-sm text-on-surface-variant">{cats.length} valgt</span>
              </div>
              <Categories wsId={ws.id} categories={cats} suggested={suggested.items} canEdit={canEdit} />
            </div>
            <div className="p-space-md rounded-xl bg-surface space-y-2">
              <span className="font-label-md text-label-md text-primary font-bold flex items-center gap-1"><Icon name="location_on" size={16} />Lokation og dækningsområde</span>
              {zones.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">{zones.map((z, i) => <span key={z} className="px-2.5 py-1 rounded bg-surface-container-lowest shadow-sm text-primary font-label-sm text-label-sm font-semibold">Zone {i + 1}: {z}</span>)}</div>
              ) : <p className="font-body-sm text-body-sm text-on-surface-variant">Intet dækningsområde endnu.</p>}
              <Link href="/app/knowledge?tab=k03" className="font-label-sm text-label-sm text-secondary font-semibold hover:underline flex items-center gap-1">Redigér i Videnscenter<Icon name="arrow_forward" size={14} /></Link>
            </div>
          </div>
        </div>

        {/* O02 — knowledge the assistant may use (entered manually; no automatic extraction yet) */}
        <div className="xl:col-span-7 flex flex-col gap-space-xl">
          <div className="bg-surface-container-lowest p-space-md md:p-space-xl rounded-xl shadow-sm space-y-space-lg">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-2 gap-2">
              <div className="flex items-center gap-space-sm">
                <span className="w-7 h-6 rounded-md bg-secondary text-on-secondary flex items-center justify-center font-label-sm text-[10px] font-bold flex-shrink-0">2</span>
                <div>
                  <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Fakta og redigerbar viden</h2>
                  <p className="font-body-sm text-body-sm text-on-surface-variant">Valider hvad assistenten må gengive til kunder.</p>
                </div>
              </div>
              <span className="px-2.5 py-1 rounded-full bg-surface-container text-on-surface-variant font-label-sm text-label-sm font-medium self-start sm:self-auto">{approvedCount} godkendt • {pendingCount} kræver handling</span>
            </div>
            <div className="p-space-md rounded-xl bg-surface-container-low flex items-start gap-space-md">
              <Icon name="lock_reset" size={22} className="text-secondary mt-0.5" />
              <div className="flex-1">
                <p className="font-label-md text-label-md text-primary font-bold">Kun godkendte versioner bruges</p>
                <p className="font-body-sm text-body-sm text-on-surface-variant mt-0.5">En ny kladde ændrer aldrig den aktive viden, før en ejer eller administrator har godkendt den. Automatisk udtræk fra hjemmeside og dokumenter er ikke bygget endnu, så alt her er indtastet manuelt.</p>
              </div>
            </div>

            {/* Opening hours */}
            <div className="p-space-md rounded-xl bg-surface space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><Icon name="schedule" size={18} className="text-primary" /><span className="font-label-md text-label-md text-primary font-bold">Åbningstider &amp; telefontider</span></div>
                <FactStatus item={hours} />
              </div>
              {hours ? (() => {
                const c = (hours.approved_version ?? hours.open_draft)!.content as { weekly?: { days: string[]; open: string; close: string }[]; closed_note?: string };
                return (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1">
                    {(c.weekly ?? []).map((w, i) => (
                      <div key={i} className="bg-surface-container-lowest p-2.5 rounded-lg">
                        <span className="font-label-sm text-label-sm text-on-surface-variant block capitalize">{daysLabel(w.days)}</span>
                        <span className="font-headline-sm text-headline-sm text-primary font-bold">{w.open} – {w.close}</span>
                      </div>
                    ))}
                    {c.closed_note && (
                      <div className="bg-surface-container-lowest p-2.5 rounded-lg">
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
            <div className="p-space-md rounded-xl bg-surface-container space-y-3">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <Icon name="payments" size={20} className="text-secondary" />
                  <div>
                    <span className="font-label-md text-label-md text-primary font-bold">Ydelser og vejledende priser</span>
                    {services.some((s) => s.open_draft) && <span className="font-label-sm text-label-sm text-on-error-container block font-bold">Ugodkendte ændringer – kræver godkendelse</span>}
                  </div>
                </div>
                <span className="font-label-sm text-label-sm text-on-surface-variant bg-surface-container-lowest px-2 py-0.5 rounded self-start sm:self-auto">Kilde: indtastet manuelt</span>
              </div>
              <div className="space-y-2">
                {services.length === 0 && <EmptyFact text="Ingen ydelser endnu – tilføj mindst én i Videnscenter." />}
                {services.map((s) => {
                  const v = s.open_draft ?? s.approved_version!;
                  const c = v.content as { description?: string; price_net_minor?: number; unit?: string };
                  return (
                    <div key={s.id} className="p-3 rounded-lg bg-surface-container-lowest flex flex-col sm:flex-row sm:items-center justify-between gap-2 shadow-sm">
                      <div className="min-w-0">
                        <p className="font-label-md text-label-md text-primary font-bold">{v.title}</p>
                        {c.description && <p className="font-body-sm text-body-sm text-on-surface-variant">{c.description}</p>}
                      </div>
                      <div className="flex items-center gap-3 self-end sm:self-auto">
                        {kr(c.price_net_minor) && <div className="text-right"><span className="font-headline-sm text-headline-sm text-primary font-bold">{kr(c.price_net_minor)}</span><span className="font-label-sm text-label-sm text-on-surface-variant block">{UNIT[c.unit ?? ""] ?? ""} ekskl. moms</span></div>}
                        {s.open_draft
                          ? canApprove ? <ApproveButton wsId={ws.id} versionId={s.open_draft.id} label="Godkend" /> : <span className="px-2 py-0.5 rounded bg-surface-container text-on-surface-variant font-label-sm text-label-sm">Afventer godkendelse</span>
                          : <span className="px-2 py-0.5 rounded bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold">Godkendt</span>}
                      </div>
                    </div>
                  );
                })}
              </div>
              <div className="flex justify-end pt-1">
                <Link href="/app/knowledge?tab=k03" className="text-primary hover:underline font-label-sm text-label-sm font-semibold flex items-center gap-1"><Icon name="edit_note" size={14} />Rediger priser i Videnscenter</Link>
              </div>
            </div>

            {/* Escalation — needs telephony */}
            <div className="p-space-md rounded-xl bg-surface space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2"><Icon name="support_agent" size={18} className="text-primary" /><span className="font-label-md text-label-md text-primary font-bold">Eskalering ved akutte henvendelser</span></div>
                <span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm font-bold">Ikke tilgængelig endnu</span>
              </div>
              <p className="p-2.5 rounded-lg bg-surface-container-lowest font-body-sm text-body-sm text-on-surface-variant">Viderestilling til vagttelefon kræver telefoni, som ikke er tilkoblet. Reglen kan oprettes, når telefoni-adapteren er bygget.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky action bar */}
      <div className="md:sticky md:bottom-4 z-40 w-full bg-surface-container-lowest/95 backdrop-blur-md p-space-md rounded-xl shadow-xl flex flex-col-reverse md:flex-row items-center justify-between gap-space-md">
        <div className="flex items-center gap-space-md w-full md:w-auto">
          {canEdit && <SelfManagedButton wsId={ws.id} goals={goals} />}
          <span className="hidden md:inline font-body-sm text-body-sm text-on-surface-variant">Dine indtastninger gemmes serverside uanset valg.</span>
        </div>
        <div className="flex flex-col-reverse md:flex-row items-stretch md:items-center gap-space-md w-full md:w-auto md:justify-end">
          <button form="business-form" type="submit" name="intent" value="save" disabled={!canEdit} className="px-space-md py-2.5 rounded-lg bg-surface-container-low hover:bg-surface-container text-primary font-label-md text-label-md font-semibold transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"><Icon name="save" size={18} />Gem</button>
          <button form="business-form" type="submit" name="intent" value="next" className="justify-center px-space-xl py-2.5 rounded-lg bg-primary-container hover:bg-primary text-on-primary font-label-md text-label-md font-bold transition-all shadow-md flex items-center gap-2">
            <span>Gem og fortsæt til mål &amp; sprog</span><Icon name="arrow_forward" size={18} className="text-secondary-fixed" />
          </button>
        </div>
      </div>
    </div>
  );
}

function FactStatus({ item }: { item?: Item }) {
  if (!item) return <span className="px-2 py-0.5 rounded-full bg-surface-container-highest text-on-surface-variant font-label-sm text-label-sm font-bold">Mangler</span>;
  return item.open_draft
    ? <span className="px-2 py-0.5 rounded-full bg-error-container text-on-error-container font-label-sm text-label-sm font-bold">Ugodkendt ændring</span>
    : <span className="px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold flex items-center gap-1"><Icon name="check_circle" size={12} />Godkendt</span>;
}

function EmptyFact({ text }: { text: string }) {
  return <p className="p-2.5 rounded-lg bg-surface-container-lowest font-body-sm text-body-sm text-on-surface-variant">{text}</p>;
}
