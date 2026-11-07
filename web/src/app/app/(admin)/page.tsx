import Link from "next/link";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { setupStatus } from "@/lib/setup.server";
import { Icon } from "@/components/ui";
import { PowerToggle, type TelephonyCode } from "./client";
import { InstallBanner } from "@/components/install-step";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";

type Activity = { id: string; kind: string; title: string; body: string; href: string; at: string };
type Overview = { kpis: Record<string, number>; activity: Activity[] };
type Telephony = { status: { code: TelephonyCode; label: string; next_step: string }; business_number: string | null; destination: { e164: string } | null };
type Row = { id: string; channel: string; outcome: "booked" | "to_you" | "done"; name: string; origin: string | null; summary: string; question: string; started_at: string };
type Appt = { id: string; title: string; label: string; starts_at: string; contact_name: string };
/** Outcome → pill class; the label is `app.outcome.<outcome>`. */
const TAG: Record<Row["outcome"], string> = { booked: "bg-success-soft text-success", to_you: "bg-highlight text-ink", done: "bg-accent-soft text-accent-deep" };

/** What each "to you" item is and what the one button does: `app.overview.todo.<kind>.tag|cta`. */
const TODO = new Set(["lead", "conversation", "task", "knowledge", "import"]);

const hhmm = (lang: string, iso: string | null) => iso ? new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit" }) : "–";
const dayLabel = (lang: string, iso: string | null) => {
  if (!iso) return "";
  const d = new Date(iso), now = new Date();
  return d.toDateString() === now.toDateString() ? "" : d.toLocaleDateString(lang, { day: "numeric", month: "short" });
};

/** "I dag": status + today's numbers, the list of things that need you, the latest calls, and the one place to change things from. */
export default async function OverviewPage({ searchParams }: { searchParams: Promise<{ taendt?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  const { taendt } = await searchParams;
  // The three setup steps come first. «Jeg gør resten senere» (cookie) lets people look around before they are done.
  const st = await setupStatus(ws.id, ws.role);
  if (!taendt && !st.done && !(await cookies()).get("db_setup_later")) redirect(`/opsaetning/${st.next}`);
  const staff = ws.role !== "reader";
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [ov, tel, calls, appts, goals] = await Promise.all([
    backend<Overview>(`/workspaces/${ws.id}/overview`),
    staff ? backend<Telephony>(`/workspaces/${ws.id}/telephony`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ items: Row[] }>(`/workspaces/${ws.id}/conversations/feed?limit=5`).catch(() => null) : Promise.resolve(null),
    staff ? backend<{ items: Appt[]; timezone: string }>(`/workspaces/${ws.id}/bookings?days=30`).catch(() => null) : Promise.resolve(null),
    backend<{ callback: boolean }>(`/workspaces/${ws.id}/goals`).catch(() => null),
  ]);
  const nextAppts = appts?.items.filter((a) => new Date(a.starts_at) >= new Date()).slice(0, 3) ?? [];
  const k = ov.kpis;
  const code: TelephonyCode = tel?.status.code ?? "not_started";
  const on = code === "active";
  const todo = ov.activity.filter((a) => TODO.has(a.kind) && (a.kind !== "task" || a.title.startsWith("Overskredet")));

  return (
    <div className="flex flex-wrap gap-6 items-start">
      {/* LEFT: the three things you can SEE */}
      <section className="flex-[999_1_560px] min-w-0 flex flex-col gap-5">
        {taendt && st.done && (
          <div role="status" className="stamp-in flex items-center gap-3 px-5 py-4 rounded-2xl border-2 border-ink bg-highlight shadow-block-sm">
            <Icon name="power_settings_new" size={26} />
            <span className="font-display font-extrabold text-[20px] text-ink">{t("overview.turnedOn")}</span>
            <span className="text-[14px] text-ink-soft">{t("overview.turnedOnSub")}</span>
          </div>
        )}
        {!st.done && (
          <Link href={`/opsaetning/${st.next}`} className="flex flex-wrap items-center gap-3 px-5 py-4 rounded-2xl border-2 border-dashed border-ink bg-paper hover:bg-panel">
            <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-[11px] font-semibold uppercase tracking-[0.08em]">{t("overview.notDone")}</span>
            <span className="flex-1 min-w-[200px] text-[15px] font-semibold text-ink">{t("overview.setupNext", { n: st.next })} {st.next === 1 ? t("overview.step1") : st.next === 2 ? t("overview.step2") : t("overview.step3")}</span>
            <span className="inline-flex items-center gap-1 text-[14px] font-semibold text-ink">{t("overview.continue")}<Icon name="arrow_forward" size={18} /></span>
          </Link>
        )}

        {/* First open after the login (once-dismissible): the app on the home screen. Hidden in the installed app. */}
        <InstallBanner audience="erhverv" />

        {/* 1. Status */}
        <div className="flex flex-wrap items-center gap-4 md:gap-6 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[24px] text-ink" aria-hidden>1</span>
          <div className="flex flex-col gap-0.5 flex-[1_1_200px]">
            <h1 className="font-display font-extrabold text-[24px] leading-tight tracking-[-0.4px] text-ink">{on ? t("overview.isOn") : code === "paused" ? t("overview.isOff") : t("overview.isNotOn")}</h1>
            <span className="text-[14px] text-muted">{t(`overview.statusLine.${code}`)}{tel?.business_number ? ` · ${tel.business_number}` : ""}</span>
            {!on && code !== "paused" && staff && <Link href="/app/indstillinger/telefoni" className="text-[14px] font-semibold text-ink underline underline-offset-2 w-fit mt-1">{t("overview.setUpPhone")}</Link>}
          </div>
          {staff && <PowerToggle wsId={ws.id} code={code} canManage={canManage} />}
        </div>

        {/* today's numbers */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
          <Tile n={k.calls_24h ?? 0} label={t("overview.tiles.calls")} sub={t("overview.tiles.callsSub")} href="/app/opkald" />
          <Tile n={k.new_leads_24h ?? 0} label={t("overview.tiles.leads")} sub={t("overview.tiles.leadsSub", { n: k.open_leads ?? 0 })} href="/app/opkald/henvendelser" />
          <Tile n={todo.length} label={t("overview.tiles.toYou")} sub={t("overview.tiles.toYouSub")} href="#til-dig" />
        </div>

        {/* 2. To you */}
        <div id="til-dig" className="flex flex-col gap-3.5 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex items-center gap-3.5">
            <span className="inline-flex w-12 h-12 rounded-xl bg-highlight items-center justify-center font-display font-extrabold text-[24px] text-ink" aria-hidden>2</span>
            <div className="flex flex-col">
              <h2 className="font-display font-extrabold text-[22px] leading-tight tracking-[-0.3px] text-ink">{t("overview.toYou")}</h2>
              <span className="text-[14px] text-muted">{t("overview.toYouSub")}</span>
            </div>
          </div>
          {todo.length === 0 ? (
            <p className="px-4 py-3.5 rounded-[14px] border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">{t("overview.nothingWaiting")}</p>
          ) : (
            <ul className="flex flex-col gap-2.5">
              {todo.map((a) => {
                const tag = t(`overview.todo.${a.kind}.tag`), cta = t(`overview.todo.${a.kind}.cta`);
                return (
                  <li key={a.id} className="flex flex-wrap items-center gap-2.5 md:gap-3.5 px-4 py-3.5 rounded-[14px] border-2 border-ink bg-paper">
                    <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-ink text-[11px] font-semibold uppercase tracking-[0.08em]">{tag}</span>
                    <div className="flex-[1_1_240px] flex flex-col gap-0.5 min-w-0">
                      <span className="text-[15px] font-semibold text-ink">{a.title}</span>
                      {a.body && <span className="text-[13px] text-ink-soft truncate">{a.body}</span>}
                    </div>
                    <Link href={a.href} aria-label={`${cta}: ${a.title}`} className="inline-flex items-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep">{cta}</Link>
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
              <h2 className="font-display font-extrabold text-[22px] leading-tight tracking-[-0.3px] text-ink">{t("overview.latestCalls")}</h2>
              <span className="text-[14px] text-muted">{t("overview.latestCallsSub")}</span>
            </div>
          </div>
          {!calls || calls.items.length === 0 ? (
            <p className="px-4 py-3.5 rounded-[14px] border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">{calls ? t("overview.noCalls") : t("overview.callsStaffOnly")}</p>
          ) : (
            <ul className="flex flex-col border-t-[1.5px] border-ink">
              {calls.items.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-2 md:gap-4 py-3 border-b-[1.5px] border-ink text-[14px]">
                  <span className="font-display font-bold min-w-[48px] text-ink">{hhmm(lang, c.started_at)}<span className="block text-[11px] font-body font-medium text-muted">{dayLabel(lang, c.started_at)}</span></span>
                  <span className="flex-[1_1_220px] min-w-0 text-ink"><b>{c.channel === "webchat" ? `Webchat${c.name !== "Webchat" ? ` · ${c.name}` : ""}` : c.name}</b>{c.summary || c.question ? ` · ${c.summary || c.question}` : ""}</span>
                  <span className={`inline-flex px-2.5 py-1 rounded-full text-[12px] font-semibold ${TAG[c.outcome]}`}>{t(`outcome.${c.outcome}`)}</span>
                  <Link href={`/app/opkald/${c.id}`} className="font-semibold text-ink underline underline-offset-2">{t("overview.read")}</Link>
                </li>
              ))}
            </ul>
          )}
          <Link href="/app/opkald" className="self-start text-[14px] font-semibold text-ink underline underline-offset-2">{t("overview.allCalls")}</Link>
        </div>

        {/* Aftaler (and Kampagner when outbound calls are chosen) */}
        {staff && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div className="flex flex-col gap-2.5 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
              <h2 className="font-display font-extrabold text-[20px] text-ink">{t("overview.appointments")}</h2>
              {nextAppts.length === 0 ? <p className="text-[14px] text-ink-soft">{t("overview.noAppointments")}</p> : (
                <ul className="flex flex-col">{nextAppts.map((a) => <li key={a.id} className="py-2 border-t-[1.5px] border-line text-[14px] text-ink"><b>{a.label}</b> · {a.contact_name || a.title}</li>)}</ul>
              )}
              <Link href="/app/aftaler" className="self-start text-[14px] font-semibold text-ink underline underline-offset-2">{t("overview.weekAppointments")}</Link>
            </div>
            {goals?.callback && (
              <div className="flex flex-col gap-2.5 px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
                <h2 className="font-display font-extrabold text-[20px] text-ink">{t("overview.campaigns")}</h2>
                <p className="text-[14px] text-ink-soft">{t("overview.campaignsSub")}</p>
                <Link href="/app/kampagner" className="self-start text-[14px] font-semibold text-ink underline underline-offset-2">{t("overview.openCampaigns")}</Link>
              </div>
            )}
          </div>
        )}

        {/* Everything else that happened, for completeness */}
        {ov.activity.length > 0 && (
          <details className="rounded-2xl bg-paper border-[1.5px] border-ink px-6 py-4">
            <summary className="cursor-pointer text-[14px] font-semibold text-ink">{t("overview.allActivity")}</summary>
            <ul className="mt-3 flex flex-col">
              {ov.activity.map((a) => (
                <li key={a.id}><Link href={a.href} className="flex items-start gap-3 py-2.5 border-t-[1.5px] border-line hover:bg-panel -mx-2 px-2 rounded-lg">
                  <span className="flex-1 min-w-0 text-[14px] text-ink"><span className="block font-semibold">{a.title}</span>{a.body && <span className="block text-[13px] text-ink-soft truncate">{a.body}</span>}</span>
                  <span className="text-[12px] text-muted shrink-0">{new Date(a.at).toLocaleString(lang, { dateStyle: "short", timeStyle: "short" })}</span>
                </Link></li>
              ))}
            </ul>
          </details>
        )}
      </section>
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
