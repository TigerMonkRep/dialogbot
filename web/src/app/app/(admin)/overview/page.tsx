import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { ChangePanel, PowerToggle, type TelephonyCode } from "./client";

type Activity = { id: string; kind: string; title: string; body: string; href: string; at: string };
type Overview = { kpis: Record<string, number>; activity: Activity[] };
type Plan = { progress: { required_total: number; required_complete: number }; next_action: { title: string } | null };
type Telephony = { status: { code: TelephonyCode; label: string; next_step: string }; business_number: string | null; destination: { e164: string } | null };
type Call = { id: string; from_number: string | null; started_at: string | null; duration_seconds: number | null; ended_reason: string | null; summary: string | null; conversation_id: string | null };
type Me = { display_name: string };

/** What each "to you" item is and what the one button does. */
const TODO: Record<string, { tag: string; cta: string }> = {
  lead: { tag: "Ny henvendelse", cta: "Åbn" },
  conversation: { tag: "Venter på dig", cta: "Svar" },
  task: { tag: "Opgave", cta: "Åbn" },
  knowledge: { tag: "Godkend", cta: "Gennemgå" },
  import: { tag: "Forslag", cta: "Se forslag" },
};

const STATUS_LINE: Record<TelephonyCode, string> = {
  active: "Tager telefonen, når I ikke selv gør.",
  paused: "Sat på pause – opkald går til jer som før.",
  not_started: "Telefonen er ikke sat op endnu.",
  awaiting_info: "Mangler oplysninger, før telefonen kan kobles på.",
  provisioning: "Forbindelsen gøres klar.",
  ready_for_test: "Klar til prøveopkald.",
  test_failed: "Prøveopkaldet fejlede – prøv igen.",
};

const hhmm = (iso: string | null) => iso ? new Date(iso).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" }) : "–";
const dayLabel = (iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  return d.toDateString() === now.toDateString() ? "" : d.toLocaleDateString("da-DK", { day: "numeric", month: "short" });
};

/** "I dag": status + today's numbers, the list of things that need you, the latest calls, and the one place to change things from. */
export default async function OverviewPage() {
  const ws = await requireWorkspace();
  const staff = ws.role !== "reader";
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [ov, plan, tel, calls, me] = await Promise.all([
    backend<Overview>(`/workspaces/${ws.id}/overview`),
    backend<Plan>(`/workspaces/${ws.id}/setup/plan`).catch(() => null),
    staff ? backend<Telephony>(`/workspaces/${ws.id}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ items: Call[] }>(`/workspaces/${ws.id}/telephony/calls?limit=5`).catch(() => null) : Promise.resolve(null),
    backend<Me>("/auth/me").catch(() => null),
  ]);
  const k = ov.kpis;
  const code: TelephonyCode = tel?.status.code ?? "not_started";
  const on = code === "active";
  const todo = ov.activity.filter((a) => a.kind in TODO && (a.kind !== "task" || a.title.startsWith("Overskredet")));
  const pct = plan ? Math.round((100 * plan.progress.required_complete) / Math.max(1, plan.progress.required_total)) : null;
  const firstName = (me?.display_name ?? "").split(" ")[0] || "du";
  const summary = `${k.calls_24h ?? 0} opkald og ${k.new_leads_24h ?? 0} nye henvendelser det seneste døgn, ${todo.length === 0 ? "intet" : todo.length} venter på dig.`;

  return (
    <div className="flex flex-wrap gap-6 items-start">
      {/* LEFT: the three things you can SEE */}
      <section className="flex-[999_1_560px] min-w-0 flex flex-col gap-5">
        {plan && pct !== null && pct < 100 && (
          <Link href="/app/setup" className="flex flex-wrap items-center gap-3 px-5 py-4 rounded-2xl border-2 border-dashed border-ink bg-paper hover:bg-panel">
            <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-[11px] font-semibold uppercase tracking-[0.08em]">Ikke færdig</span>
            <span className="flex-1 min-w-[200px] text-[15px] font-semibold text-ink">Opsætningen er {pct} % færdig{plan.next_action ? ` · Næste: ${plan.next_action.title}` : ""}</span>
            <span className="inline-flex items-center gap-1 text-[14px] font-semibold text-ink">Fortsæt<Icon name="arrow_forward" size={18} /></span>
          </Link>
        )}

        {/* 1. Status */}
        <div className="flex flex-wrap items-center gap-4 md:gap-6 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[24px] text-ink" aria-hidden>1</span>
          <div className="flex flex-col gap-0.5 flex-[1_1_200px]">
            <h1 className="font-display font-extrabold text-[24px] leading-tight tracking-[-0.4px] text-ink">Dialogbot er {on ? "tændt" : code === "paused" ? "slukket" : "ikke tændt"}</h1>
            <span className="text-[14px] text-muted">{STATUS_LINE[code]}{tel?.business_number ? ` · ${tel.business_number}` : ""}</span>
            {!on && code !== "paused" && staff && <Link href="/app/settings/telephony" className="text-[14px] font-semibold text-ink underline underline-offset-2 w-fit mt-1">Sæt telefonen op</Link>}
          </div>
          {staff && <PowerToggle wsId={ws.id} code={code} canManage={canManage} />}
        </div>

        {/* today's numbers */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          <Tile n={k.calls_24h ?? 0} label="opkald" sub="seneste 24 timer" href="/app/inbox" />
          <Tile n={k.new_leads_24h ?? 0} label="nye henvendelser" sub={`${k.open_leads ?? 0} åbne i alt`} href="/app/leads" />
          <Tile n={todo.length} label="til dig" sub="venter på dit svar" href="#til-dig" />
        </div>

        {/* 2. To you */}
        <div id="til-dig" className="flex flex-col gap-3.5 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex items-center gap-3.5">
            <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[24px] text-ink" aria-hidden>2</span>
            <div className="flex flex-col">
              <h2 className="font-display font-extrabold text-[22px] leading-tight tracking-[-0.3px] text-ink">Til dig</h2>
              <span className="text-[14px] text-muted">Det eneste, du skal gøre i dag.</span>
            </div>
          </div>
          {todo.length === 0 ? (
            <p className="px-4 py-3.5 rounded-[14px] border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">Intet venter på dig lige nu.</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {todo.map((a) => {
                const t = TODO[a.kind];
                return (
                  <li key={a.id} className="flex flex-wrap items-center gap-2.5 md:gap-3.5 px-4 py-3.5 rounded-[14px] border-2 border-ink bg-paper">
                    <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.08em]">{t.tag}</span>
                    <div className="flex-[1_1_240px] flex flex-col gap-0.5 min-w-0">
                      <span className="text-[15px] font-semibold text-ink">{a.title}</span>
                      {a.body && <span className="text-[13px] text-ink-soft truncate">{a.body}</span>}
                    </div>
                    <Link href={a.href} className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep">{t.cta}</Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* 3. Latest calls */}
        <div className="flex flex-col gap-3.5 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex items-center gap-3.5">
            <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[24px] text-ink" aria-hidden>3</span>
            <div className="flex flex-col">
              <h2 className="font-display font-extrabold text-[22px] leading-tight tracking-[-0.3px] text-ink">Seneste opkald</h2>
              <span className="text-[14px] text-muted">Klik på et for at læse, hvad der blev sagt.</span>
            </div>
          </div>
          {!calls || calls.items.length === 0 ? (
            <p className="px-4 py-3.5 rounded-[14px] border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">{calls ? "Ingen opkald endnu." : "Opkald kan ses af medarbejdere, administratorer og ejere."}</p>
          ) : (
            <ul className="flex flex-col border-t-[1.5px] border-ink">
              {calls.items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2 md:gap-4 py-3 border-b-[1.5px] border-ink text-[14px]">
                  <span className="font-display font-bold min-w-[48px] text-ink">{hhmm(c.started_at)}<span className="block text-[11px] font-body font-medium text-muted">{dayLabel(c.started_at)}</span></span>
                  <span className="flex-[1_1_220px] min-w-0 text-ink"><b>{c.from_number || "Skjult nummer"}</b>{c.summary ? ` · ${c.summary}` : ""}</span>
                  <span className={`inline-flex px-2.5 py-1 rounded-full text-[12px] font-semibold ${c.conversation_id ? "bg-panel border-[1.5px] border-ink text-ink" : "bg-highlight text-ink"}`}>{c.conversation_id ? "Besvaret af Dialogbot" : "Ingen samtale"}</span>
                  {c.conversation_id ? <Link href={`/app/inbox/${c.conversation_id}`} className="font-semibold text-ink underline underline-offset-2">Læs</Link> : <span className="text-muted">{c.duration_seconds ? `${Math.round(c.duration_seconds / 60)} min` : ""}</span>}
                </li>
              ))}
            </ul>
          )}
          <Link href="/app/inbox" className="self-start text-[14px] font-semibold text-ink underline underline-offset-2">Se alle opkald</Link>
        </div>

        {/* Everything else that happened, for completeness */}
        {ov.activity.length > 0 && (
          <details className="rounded-2xl bg-paper border-[1.5px] border-ink px-6 py-4">
            <summary className="cursor-pointer text-[14px] font-semibold text-ink">Al aktivitet de seneste 14 dage</summary>
            <ul className="mt-3 flex flex-col">
              {ov.activity.map((a) => (
                <li key={a.id}><Link href={a.href} className="flex items-start gap-3 py-2.5 border-t-[1.5px] border-line hover:bg-panel -mx-2 px-2 rounded-lg">
                  <span className="flex-1 min-w-0 text-[14px] text-ink"><span className="block font-semibold">{a.title}</span>{a.body && <span className="block text-[13px] text-ink-soft truncate">{a.body}</span>}</span>
                  <span className="text-[12px] text-muted shrink-0">{new Date(a.at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" })}</span>
                </Link></li>
              ))}
            </ul>
          </details>
        )}
      </section>

      {/* RIGHT: the ONE thing you change with */}
      <div className="flex-[1_1_340px] min-w-0 max-w-[440px] w-full xl:sticky xl:top-[88px]">
        <ChangePanel firstName={firstName} summary={summary} />
      </div>
    </div>
  );
}

function Tile({ n, label, sub, href }: { n: number; label: string; sub: string; href: string }) {
  return (
    <Link href={href} className="flex flex-col gap-1 px-5 py-4 rounded-2xl bg-paper border-2 border-ink hover:bg-panel">
      <span className="font-display font-extrabold text-[40px] leading-none text-ink tabular-nums">{n}</span>
      <span className="text-[14px] font-semibold text-ink">{label}</span>
      <span className="text-[12px] text-muted">{sub}</span>
    </Link>
  );
}
