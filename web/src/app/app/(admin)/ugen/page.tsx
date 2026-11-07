import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { ReportSettingsForm } from "./client";
import { getLocale, getRaw, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import type { T } from "@/i18n/translate";
import { currencyOr, formatPrice } from "@/lib/markets";

type Week = {
  start: string; end: string; timezone: string; answered: number; phone: number; to_you: number; bookings: number; bookings_prev_week: number;
  response_seconds: number | null; days: { date: string; answered: number; to_you: number }[]; campaign_calls: number; campaign_net_minor?: number; currency?: string;
};
type Topic = { topic: string; count: number; booked: number; could_answer: boolean; to_you: number };

const iso = (d: Date) => d.toISOString().slice(0, 10);
const at = (s: string) => new Date(`${s}T12:00:00Z`);
const addDays = (s: string, n: number) => { const d = at(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
const monday = (s: string) => { const d = at(s); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return iso(d); };
/** ISO week number (Monday-based; the week with the year's first Thursday is week 1). */
const isoWeek = (s: string) => {
  const d = at(s); d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
  const first = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  return 1 + Math.round(((d.getTime() - first.getTime()) / 86400000 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
};
const short = (lang: string, s: string) => at(s).toLocaleDateString(lang, { day: "numeric", month: "short", timeZone: "UTC" }).replace(".", "").toUpperCase();
const secs = (n: number | null) => (n === null ? "–" : n < 1 ? "<1 s" : n < 60 ? `${Math.round(n)} s` : `${Math.round(n / 60)} min`);
const kr = (t: T, lang: string, minor: number, currency?: string) => t("common.kr", { amount: formatPrice(minor, currencyOr(currency), lang) });

/** «Ugen»: what Dialogbot did last week, in four numbers, a bar per day and the questions customers asked. */
export default async function UgenPage({ searchParams }: { searchParams: Promise<{ uge?: string; date?: string }> }) {
  const ws = await requireWorkspace();
  const tr = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  const WD = (await getRaw())<string[]>("app.time.weekdaysShort");
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">{tr("week.staffOnly")}</p>;
  const isAdmin = ws.role === "owner" || ws.role === "admin";
  const { uge, date } = await searchParams;
  const wanted = [uge, date].find((v) => v && /^\d{4}-\d{2}-\d{2}$/.test(v));   // /app/reports?date=… from old e-mails lands in the right week
  const q = wanted ? `?start=${monday(wanted)}` : "";
  const [w, t, settings] = await Promise.all([
    backend<Week>(`/workspaces/${ws.id}/reports/week${q}`),
    backend<{ items: Topic[] }>(`/workspaces/${ws.id}/reports/topics${q}`),
    backend<{ email_enabled: boolean; send_hour_local: number; timezone: string }>(`/workspaces/${ws.id}/reports/settings`),
  ]);
  const thisWeek = monday(iso(new Date()));
  const isNow = w.start >= thisWeek;
  const max = Math.max(1, ...w.days.map((d) => d.answered + d.to_you));
  const delta = w.bookings - w.bookings_prev_week;
  const hour = String(settings.send_hour_local).padStart(2, "0");
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="flex flex-col gap-1.5">
            <span className="eyebrow">{tr("week.weekN", { n: isoWeek(w.start) })} · {short(lang, w.start)} – {short(lang, w.end)}</span>
            <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{tr("week.title")}</h1>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label={tr("week.chooseWeek")}>
            <Link href={`/app/ugen?uge=${addDays(w.start, -7)}`} className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">‹ {tr("week.weekN", { n: isoWeek(addDays(w.start, -7)) })}</Link>
            <Link href="/app/ugen" aria-current={isNow ? "page" : undefined} className={`inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${isNow ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>{tr("week.thisWeek")}</Link>
            {isNow ? <span className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-line text-[14px] font-semibold text-muted" aria-disabled>{tr("week.weekN", { n: isoWeek(addDays(w.start, 7)) })} ›</span>
              : <Link href={`/app/ugen?uge=${addDays(w.start, 7)}`} className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">{tr("week.weekN", { n: isoWeek(addDays(w.start, 7)) })} ›</Link>}
          </nav>
        </div>

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3.5">
          <Num n={String(w.answered)} label={tr("week.num.answered")} sub={tr("week.num.answeredSub", { phone: w.phone, chat: w.answered - w.phone })} />
          <Num n={String(w.bookings)} label={tr("week.num.bookings")} sub={w.bookings_prev_week || w.bookings ? tr("week.num.vsLastWeek", { d: `${delta >= 0 ? "+" : "−"}${Math.abs(delta)}` }) : tr("week.num.noneYet")} />
          <Num n={String(w.to_you)} label={tr("week.num.toYou")} sub={w.to_you ? tr("week.num.waiting") : tr("week.num.allDone")} />
          <Num n={secs(w.response_seconds)} label={tr("week.num.response")} sub={w.response_seconds === null ? tr("week.num.noChat") : tr("week.num.allDay")} />
        </div>

        <div className="flex flex-col gap-4 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>1</span>
            <div>
              <h2 className="font-display font-extrabold text-[20px] text-ink">{tr("week.perDay")}</h2>
              <p className="flex gap-3 text-[13px] text-muted"><span className="inline-flex items-center gap-1.5"><i className="w-3 h-3 rounded-sm bg-accent" />{tr("week.answered")}</span><span className="inline-flex items-center gap-1.5"><i className="w-3 h-3 rounded-sm bg-highlight border border-ink" />{tr("week.messageToYou")}</span></p>
            </div>
          </div>
          <ol className="grid grid-cols-7 gap-2 md:gap-4 items-end h-[210px]" aria-label={tr("week.perDay")}>
            {w.days.map((d, i) => {
              const total = d.answered + d.to_you;
              return (
                <li key={d.date} className="flex flex-col items-center justify-end h-full gap-1" aria-label={tr("week.dayAria", { day: WD[i], answered: d.answered, toYou: d.to_you })}>
                  <span className="text-[13px] text-ink-soft">{total}</span>
                  <div className="w-full max-w-[48px] flex flex-col justify-end h-[150px]">
                    {d.to_you > 0 && <div className="w-full bg-highlight border-b-2 border-paper" style={{ height: `${(d.to_you / max) * 100}%` }} />}
                    {d.answered > 0 && <div className="w-full bg-accent" style={{ height: `${(d.answered / max) * 100}%` }} />}
                    {total === 0 && <div className="w-full h-0.5 bg-line" />}
                  </div>
                  <span className="text-[13px] font-semibold text-ink">{WD[i]}</span>
                </li>
              );
            })}
          </ol>
        </div>

        <div className="flex flex-col gap-3 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>2</span>
            <div><h2 className="font-display font-extrabold text-[20px] text-ink">{tr("week.topics.title")}</h2><p className="text-[13px] text-muted">{tr("week.topics.sub")}</p></div>
          </div>
          {t.items.length === 0 ? <p className="px-4 py-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">{tr("week.topics.empty")}</p> : (
            <div className="overflow-x-auto">
              <table className="table-stack w-full text-left text-[15px] sm:text-[14px]">
                <thead><tr className="border-b-2 border-ink text-[12px] uppercase tracking-[0.08em] text-muted"><th className="py-2 pr-3 font-semibold">{tr("week.topics.topic")}</th><th className="py-2 pr-3 font-semibold">{tr("week.topics.times")}</th><th className="py-2 font-semibold">{tr("week.topics.couldAnswer")}</th><th /></tr></thead>
                <tbody>
                  {t.items.map((x) => (
                    <tr key={x.topic} className="border-b-[1.5px] border-line align-middle">
                      <td className="py-3 pr-3 text-ink font-semibold sm:font-normal">{x.topic}</td>
                      <td data-label={tr("week.topics.times")} className="py-3 pr-3 text-ink-soft">{x.count}</td>
                      <td className="py-3 pr-3">
                        {x.could_answer
                          ? <span className="inline-flex px-2.5 py-1 rounded-full bg-success-soft text-success text-[12px] font-semibold">{tr("week.topics.yes")}{x.booked ? ` · ${tr("week.topics.booked", { n: x.booked })}` : ""}</span>
                          : <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-ink text-[12px] font-semibold">{x.to_you === x.count ? tr("week.topics.no") : tr("week.topics.partly", { n: x.to_you, total: x.count })} · {tr("week.topics.tookMessage")}</span>}
                      </td>
                      <td className="stack-inline py-3 text-right whitespace-nowrap max-sm:!pt-2">{!x.could_answer && <Link href={`/app/viden?emne=${encodeURIComponent(x.topic)}#spoergsmaal`} className="font-semibold text-accent hover:underline">{tr("week.topics.addAnswer")} →</Link>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[12px] text-muted">{tr("week.topics.note")}</p>
        </div>
      </section>

      <aside className="flex-[1_1_300px] min-w-0 max-w-[420px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 px-5 py-5 rounded-2xl bg-paper border-2 border-ink shadow-block">
          <div className="flex items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>3</span>
            <h2 className="font-display font-extrabold text-[22px] text-ink">{tr("week.report.title")}</h2>
          </div>
          <p className="text-[15px] leading-relaxed text-ink-soft">{settings.email_enabled
            ? <>{tr("week.report.on.before")} <b className="text-ink">{hour}</b> ({settings.timezone}) {tr("week.report.on.after")}</>
            : <>{tr("week.report.off.before")} <b className="text-ink">{tr("week.report.off.bold")}</b>{tr("week.report.off.after")}</>}</p>
          {isAdmin && <ReportSettingsForm wsId={ws.id} initial={settings} />}
          <p className="text-[13px] text-muted">{tr("week.report.ask")}</p>
        </div>
        {(isAdmin || ws.role === "staff") && (
          <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
            <span className="eyebrow">{tr("week.cost.title")}</span>
            <p className="font-display font-extrabold text-[30px] leading-none text-ink">{w.campaign_net_minor !== undefined ? tr("week.cost.extra", { amount: kr(tr, lang, w.campaign_net_minor, w.currency) }) : tr("week.cost.calls", { n: w.campaign_calls })}</p>
            <p className="text-[14px] text-ink-soft">{tr("week.cost.note", { n: w.campaign_calls })}</p>
            {isAdmin && <Link href="/app/konto/fakturering" className="text-[14px] font-semibold text-accent hover:underline">{tr("week.cost.billing")} →</Link>}
          </div>
        )}
      </aside>
    </div>
  );
}

function Num({ n, label, sub }: { n: string; label: string; sub: string }) {
  return (
    <div className="flex flex-col gap-0.5 px-5 py-4 rounded-2xl bg-paper border-2 border-ink">
      <span className="font-display font-extrabold text-[40px] leading-none text-ink">{n}</span>
      <span className="text-[15px] font-semibold text-ink">{label}</span>
      <span className="text-[13px] text-muted">{sub}</span>
    </div>
  );
}
