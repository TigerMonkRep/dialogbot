import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { AutoRefresh, CreateLeadButton, ReplyBox, ResolveButton } from "./client";
import { getLocale, getT } from "@/i18n/server";
import { HTML_LANG } from "@/i18n/config";
import type { T } from "@/i18n/translate";

type Item = {
  id: string; channel: string; outcome: "booked" | "to_you" | "done"; name: string; origin: string | null; summary: string; question: string;
  started_at: string; duration_seconds: number | null; phone: string | null; lead_id: string | null; awaiting_staff: boolean; mode: string;
};
type Feed = { counts: { all: number; to_you: number; booked: number; done: number; webchat: number }; items: Item[]; total: number };
type Msg = { id: string; role: string; text: string; created_at: string };
type Run = { id: string; label: string; status: "ok" | "failed" | "refused"; error: string | null; simulated: boolean };
type Detail = { id: string; messages: Msg[]; actions?: Run[] };

const TZ = "Europe/Copenhagen";
/** Filter key → count key; labels are `app.calls.filters.<key>`. */
const FILTERS: [string, keyof Feed["counts"]][] = [["all", "all"], ["to_you", "to_you"], ["booked", "booked"], ["done", "done"], ["webchat", "webchat"]];
const PERIODS = [1, 7, 30, 90];
const TAG: Record<Item["outcome"], string> = { booked: "bg-success-soft text-success", to_you: "bg-highlight text-ink", done: "bg-accent-soft text-accent-deep" };

const hhmm = (lang: string, iso: string) => new Date(iso).toLocaleTimeString(lang, { hour: "2-digit", minute: "2-digit", timeZone: TZ });
const dayKey = (iso: string) => new Date(iso).toLocaleDateString("sv-SE", { timeZone: TZ });
const dayName = (t: T, lang: string, iso: string) => {
  const key = dayKey(iso), today = dayKey(new Date().toISOString()), yest = dayKey(new Date(Date.now() - 86400000).toISOString());
  const wd = new Date(iso).toLocaleDateString(lang, { weekday: "long", timeZone: TZ });
  const lead = key === today ? t("time.today") : key === yest ? t("time.yesterday") : new Date(iso).toLocaleDateString(lang, { day: "numeric", month: "long", timeZone: TZ });
  return `${lead} · ${wd}`;
};
/** A phone call is named after the caller; a webchat after the person who left their name, else the website it came from. */
const who = (i: Item) => i.channel !== "webchat" ? i.name : i.name !== "Webchat" ? `${i.name} · Webchat` : `Webchat${i.origin ? ` · ${i.origin.replace(/^https?:\/\//, "")}` : ""}`;
const dur = (t: T, s: number | null) => (s ? t("time.minSec", { m: Math.floor(s / 60), s: s % 60 }) : "");

/** «Opkald og beskeder»: phone and webchat in one list, newest first, with the conversation on the right (a sheet on a phone). */
export async function OpkaldView({ selected, f = "all", q = "", days = 30 }: { selected?: string; f?: string; q?: string; days?: number }) {
  const ws = await requireWorkspace();
  const t = await getT("app");
  const lang = HTML_LANG[await getLocale()];
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">{t("calls.staffOnly")}</p>;
  const feed = await backend<Feed>(`/workspaces/${ws.id}/conversations/feed?f=${encodeURIComponent(f)}&q=${encodeURIComponent(q)}&days=${days}`);
  const activeId = selected ?? feed.items[0]?.id;
  const [item, detail] = activeId ? await Promise.all([
    feed.items.find((i) => i.id === activeId) ? Promise.resolve(feed.items.find((i) => i.id === activeId)!) : backend<Item>(`/workspaces/${ws.id}/conversations/${encodeURIComponent(activeId)}/summary`),
    backend<Detail>(`/workspaces/${ws.id}/conversations/${encodeURIComponent(activeId)}`),
  ]) : [null, null];
  const href = (id?: string, over: Record<string, string | number | undefined> = {}) => {
    const p = new URLSearchParams();
    const v = { f, q, days: String(days), ...over };
    if (v.f && v.f !== "all") p.set("f", String(v.f));
    if (v.q) p.set("q", String(v.q));
    if (Number(v.days) !== 30) p.set("days", String(v.days));
    const s = p.toString();
    return `/app/opkald${id ? `/${id}` : ""}${s ? `?${s}` : ""}`;
  };
  const groups: [string, Item[]][] = [];
  for (const i of feed.items) {
    const k = dayKey(i.started_at);
    const last = groups[groups.length - 1];
    if (last && dayKey(last[1][0].started_at) === k) last[1].push(i); else groups.push([dayName(t, lang, i.started_at), [i]]);
  }
  const canReply = ws.role !== "reader";
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className={`${selected ? "hidden lg:flex" : "flex"} flex-[999_1_400px] min-w-0 flex-col gap-4`} aria-label={t("calls.title")}>
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">{t("calls.eyebrow")}</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("calls.title")}</h1>
        </div>
        <nav className="flex flex-wrap items-center gap-2" aria-label={t("calls.filtersAria")}>
          {FILTERS.map(([k, c]) => {
            const on = f === k;
            return (
              <Link key={k} href={href(undefined, { f: k })} aria-current={on ? "true" : undefined}
                className={`inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${on ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>
                {t(`calls.filters.${k}`)} · <span className={k === "to_you" && !on && feed.counts.to_you ? "text-accent" : ""}>{feed.counts[c]}</span>
              </Link>
            );
          })}
          <details className="relative">
            <summary className="list-none [&::-webkit-details-marker]:hidden cursor-pointer inline-flex items-center min-h-[44px] px-3 text-[14px] font-semibold text-ink">{days === 1 ? t("time.today") : t("calls.lastDays", { n: days })} ▾</summary>
            <ul className="absolute z-10 mt-1 w-48 rounded-xl border-2 border-ink bg-paper p-1">
              {PERIODS.map((d) => <li key={d}><Link href={href(undefined, { days: d })} className="block rounded-lg px-3 py-2.5 text-[14px] text-ink hover:bg-panel">{d === 1 ? t("time.today") : t("calls.lastDays", { n: d })}</Link></li>)}
            </ul>
          </details>
        </nav>
        <form action="/app/opkald" method="get" role="search" className="flex">
          {f !== "all" && <input type="hidden" name="f" value={f} />}
          {days !== 30 && <input type="hidden" name="days" value={days} />}
          <label htmlFor="opkald-q" className="sr-only">{t("calls.search")}</label>
          <input id="opkald-q" name="q" defaultValue={q} placeholder={t("calls.search")} className="w-full min-h-[46px] px-4 rounded-xl bg-paper border-2 border-ink text-[15px] text-ink placeholder:text-muted focus:outline-none focus:ring-[3px] focus:ring-accent focus:ring-offset-2" />
        </form>
        <div className="rounded-2xl border-2 border-ink bg-paper p-3 md:p-4 flex flex-col gap-4">
          {feed.items.length === 0 ? (
            <p className="px-3 py-6 text-[15px] text-ink-soft">{q || f !== "all" ? t("calls.noMatch") : t("calls.empty")}</p>
          ) : groups.map(([label, rows]) => (
            <div key={label} className="flex flex-col gap-2">
              <h2 className="eyebrow px-1">{label}</h2>
              <ul className="flex flex-col gap-2">
                {rows.map((i) => {
                  const on = i.id === activeId;
                  const tag = t(`outcome.${i.outcome}`), cls = TAG[i.outcome];
                  return (
                    <li key={i.id}>
                      <Link href={href(i.id)} aria-current={on ? "true" : undefined}
                        className={`flex items-center gap-3 min-h-[56px] px-3.5 py-2.5 rounded-xl border-[1.5px] ${on ? "border-ink bg-accent-soft" : "border-line hover:bg-panel"}`}>
                        <span className="font-display font-bold text-[15px] text-ink w-[46px] shrink-0">{hhmm(lang, i.started_at)}</span>
                        <span className="flex-1 min-w-0 text-[15px] text-ink truncate">
                          <b>{who(i)}</b>
                          {(i.summary || i.question) && <span className="text-ink-soft"> · {i.channel === "webchat" ? `«${i.summary || i.question}»` : i.summary || i.question}</span>}
                        </span>
                        <span className={`shrink-0 inline-flex px-2.5 py-1 rounded-full text-[12px] font-semibold ${cls}`}>{tag}</span>
                      </Link>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
          {feed.total > feed.items.length && <p className="px-1 text-[13px] text-muted">{t("calls.showing", { n: feed.items.length, total: feed.total })}</p>}
        </div>
      </section>

      {item && detail && (
        <aside aria-label={t("calls.conversation")} className={`${selected ? "flex" : "hidden lg:flex"} flex-[1_1_340px] min-w-0 max-w-[480px] lg:sticky lg:top-[88px] flex-col gap-4 rounded-2xl border-2 border-ink bg-paper shadow-block p-5`}>
          <Link href={href()} className="lg:hidden inline-flex items-center gap-1 min-h-[44px] text-[14px] font-semibold text-accent"><Icon name="arrow_back" size={18} />{t("calls.back")}</Link>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <div className="min-w-0">
              <span className="eyebrow">{dayName(t, lang, item.started_at).split(" · ")[0]} {hhmm(lang, item.started_at)}{item.duration_seconds ? ` · ${dur(t, item.duration_seconds)}` : ""} · {item.channel === "phone" ? t("calls.phone") : "Webchat"}</span>
              <h2 className="font-display font-extrabold text-[22px] leading-tight text-ink break-words">{who(item)}</h2>
            </div>
            <span className={`inline-flex px-2.5 py-1 rounded-full text-[12px] font-semibold ${TAG[item.outcome]}`}>{t(`outcome.${item.outcome}`)}</span>
          </div>

          <ol className="flex flex-col gap-2.5" aria-label={t("calls.transcript")}>
            {detail.messages.length === 0 && <li className="text-[14px] text-ink-soft">{t("calls.noTranscript")}</li>}
            {detail.messages.map((m) => m.role === "visitor" ? (
              <li key={m.id} className="self-end max-w-[85%] rounded-2xl rounded-tr-sm bg-ink text-paper px-4 py-2.5 text-[15px] whitespace-pre-wrap">{m.text}</li>
            ) : (
              <li key={m.id} className="flex items-end gap-2 max-w-[92%]">
                <span className={`inline-flex w-7 h-7 shrink-0 rounded-full items-center justify-center text-[12px] font-extrabold text-white ${m.role === "staff" ? "bg-ink" : "bg-accent"}`} title={m.role === "staff" ? t("calls.staff") : "Dialogbot"}>{m.role === "staff" ? t("calls.staffInitial") : "D"}</span>
                <span className="rounded-2xl rounded-bl-sm border-2 border-ink px-4 py-2.5 text-[15px] text-ink whitespace-pre-wrap">{m.text}</span>
              </li>
            ))}
          </ol>

          {(detail.actions?.length ?? 0) > 0 && (
            <div className="rounded-xl border-[1.5px] border-ink p-3.5 flex flex-col gap-1.5">
              <span className="eyebrow">{t("calls.actions")}</span>
              <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[14px] text-ink">
                {detail.actions!.map((r) => <li key={r.id} title={r.error ?? undefined}><span aria-hidden>{r.status === "ok" ? "✓" : "✗"}</span> <span className="sr-only">{t(`calls.run.${r.status}`)}: </span>{r.label}{r.simulated ? ` (${t("calls.simulated")})` : ""}</li>)}
              </ul>
            </div>
          )}

          <div className="flex flex-wrap gap-2.5">
            {item.phone && <a href={`tel:${item.phone}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl bg-accent text-white text-[15px] font-semibold hover:bg-accent-deep">{t("calls.callBack")}</a>}
            {canReply && <Link href={`/app/aftaler?navn=${encodeURIComponent(item.name)}${item.phone ? `&telefon=${encodeURIComponent(item.phone)}` : ""}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink text-[15px] font-semibold text-ink hover:bg-panel">{t("calls.makeAppointment")}</Link>}
            {canReply && <ResolveButton wsId={ws.id} conversationId={item.id} disabled={item.outcome !== "to_you"} />}
            {item.lead_id
              ? <Link href={`/app/opkald/henvendelser/${item.lead_id}`} className="inline-flex items-center justify-center min-h-[44px] px-4 rounded-xl border-2 border-ink text-[15px] font-semibold text-ink hover:bg-panel">{t("calls.openLead")}</Link>
              : canReply && <CreateLeadButton wsId={ws.id} conversationId={item.id} need={item.question} />}
          </div>
          {item.channel === "webchat" && canReply && (
            <>
              {item.mode === "staff" && <p className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("calls.takenOver")}</p>}
              <ReplyBox wsId={ws.id} conversationId={item.id} mode={item.mode} />
              <AutoRefresh />
            </>
          )}
          <p className="text-[13px] text-muted">{t("calls.wrongAnswer")}</p>
        </aside>
      )}
    </div>
  );
}
