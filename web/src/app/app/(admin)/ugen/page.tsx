import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { ReportSettingsForm } from "./client";

type Week = {
  start: string; end: string; timezone: string; answered: number; phone: number; to_you: number; bookings: number; bookings_prev_week: number;
  response_seconds: number | null; days: { date: string; answered: number; to_you: number }[]; campaign_calls: number; campaign_net_minor?: number;
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
const short = (s: string) => at(s).toLocaleDateString("da-DK", { day: "numeric", month: "short", timeZone: "UTC" }).replace(".", "").toUpperCase();
const WD = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];
const secs = (n: number | null) => (n === null ? "–" : n < 1 ? "<1 s" : n < 60 ? `${Math.round(n)} s` : `${Math.round(n / 60)} min`);
const kr = (minor: number) => `${(minor / 100).toLocaleString("da-DK", { minimumFractionDigits: minor % 100 ? 2 : 0, maximumFractionDigits: 2 })} kr.`;

/** «Ugen»: what Dialogbot did last week, in four numbers, a bar per day and the questions customers asked. */
export default async function UgenPage({ searchParams }: { searchParams: Promise<{ uge?: string; date?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">Ugen kan ses af medarbejdere, administratorer og ejere.</p>;
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
            <span className="eyebrow">Uge {isoWeek(w.start)} · {short(w.start)} – {short(w.end)}</span>
            <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Sådan gik ugen</h1>
          </div>
          <nav className="flex flex-wrap gap-2" aria-label="Vælg uge">
            <Link href={`/app/ugen?uge=${addDays(w.start, -7)}`} className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">‹ Uge {isoWeek(addDays(w.start, -7))}</Link>
            <Link href="/app/ugen" aria-current={isNow ? "page" : undefined} className={`inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${isNow ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>Denne uge</Link>
            {isNow ? <span className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-line text-[14px] font-semibold text-muted" aria-disabled>Uge {isoWeek(addDays(w.start, 7))} ›</span>
              : <Link href={`/app/ugen?uge=${addDays(w.start, 7)}`} className="inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold text-ink hover:bg-panel">Uge {isoWeek(addDays(w.start, 7))} ›</Link>}
          </nav>
        </div>

        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3.5">
          <Num n={String(w.answered)} label="opkald og beskeder besvaret" sub={`${w.phone} på telefon · ${w.answered - w.phone} i webchat`} />
          <Num n={String(w.bookings)} label="aftaler booket" sub={w.bookings_prev_week || w.bookings ? `${delta >= 0 ? "+" : "−"}${Math.abs(delta)} mod sidste uge` : "ingen endnu"} />
          <Num n={String(w.to_you)} label="beskeder til dig" sub={w.to_you ? "venter på dig" : "alle klaret"} />
          <Num n={secs(w.response_seconds)} label="før den svarer i chatten" sub={w.response_seconds === null ? "ingen chat i ugen" : "døgnet rundt"} />
        </div>

        <div className="flex flex-col gap-4 px-5 md:px-6 py-5 rounded-2xl bg-paper border-2 border-ink">
          <div className="flex flex-wrap items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>1</span>
            <div>
              <h2 className="font-display font-extrabold text-[20px] text-ink">Opkald pr. dag</h2>
              <p className="flex gap-3 text-[13px] text-muted"><span className="inline-flex items-center gap-1.5"><i className="w-3 h-3 rounded-sm bg-accent" />besvaret</span><span className="inline-flex items-center gap-1.5"><i className="w-3 h-3 rounded-sm bg-highlight border border-ink" />besked til dig</span></p>
            </div>
          </div>
          <ol className="grid grid-cols-7 gap-2 md:gap-4 items-end h-[210px]" aria-label="Opkald pr. dag">
            {w.days.map((d, i) => {
              const total = d.answered + d.to_you;
              return (
                <li key={d.date} className="flex flex-col items-center justify-end h-full gap-1" aria-label={`${WD[i]}: ${d.answered} besvaret, ${d.to_you} til dig`}>
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
            <div><h2 className="font-display font-extrabold text-[20px] text-ink">Det spurgte kunderne om</h2><p className="text-[13px] text-muted">Mangler der et svar, lægger du det ind under «Det ved den».</p></div>
          </div>
          {t.items.length === 0 ? <p className="px-4 py-3.5 rounded-xl border-[1.5px] border-dashed border-ink text-[14px] text-ink-soft">Ingen spørgsmål i denne uge.</p> : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[14px]">
                <thead><tr className="border-b-2 border-ink text-[12px] uppercase tracking-[0.08em] text-muted"><th className="py-2 pr-3 font-semibold">Emne</th><th className="py-2 pr-3 font-semibold">Gange</th><th className="py-2 font-semibold">Dialogbot kunne svare</th><th /></tr></thead>
                <tbody>
                  {t.items.map((x) => (
                    <tr key={x.topic} className="border-b-[1.5px] border-line align-middle">
                      <td className="py-3 pr-3 text-ink">{x.topic}</td>
                      <td className="py-3 pr-3 text-ink-soft">{x.count}</td>
                      <td className="py-3 pr-3">
                        {x.could_answer
                          ? <span className="inline-flex px-2.5 py-1 rounded-full bg-success-soft text-success text-[12px] font-semibold">Ja{x.booked ? ` · bookede ${x.booked}` : ""}</span>
                          : <span className="inline-flex px-2.5 py-1 rounded-full bg-highlight text-ink text-[12px] font-semibold">{x.to_you === x.count ? "Nej" : `Delvist (${x.to_you} af ${x.count})`} · tog besked</span>}
                      </td>
                      <td className="py-3 text-right whitespace-nowrap">{!x.could_answer && <Link href={`/app/viden?emne=${encodeURIComponent(x.topic)}#spoergsmaal`} className="font-semibold text-accent hover:underline">Tilføj svar →</Link>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="text-[12px] text-muted">Samlet automatisk ud fra det, kunderne skrev eller sagde først. Ligner to spørgsmål hinanden, lægges de sammen.</p>
        </div>
      </section>

      <aside className="flex-[1_1_300px] min-w-0 max-w-[420px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 px-5 py-5 rounded-2xl bg-paper border-2 border-ink shadow-block">
          <div className="flex items-center gap-3">
            <span className="inline-flex w-10 h-10 rounded-[10px] bg-highlight items-center justify-center font-display font-extrabold text-[20px] text-ink" aria-hidden>3</span>
            <h2 className="font-display font-extrabold text-[22px] text-ink">Dagsrapport</h2>
          </div>
          <p className="text-[15px] leading-relaxed text-ink-soft">{settings.email_enabled
            ? <>Hver dag kl. <b className="text-ink">{hour}</b> ({settings.timezone}) får ejere og administratorer gårsdagens opkald og aftaler som én mail.</>
            : <>Dagsrapporten på mail er <b className="text-ink">slået fra</b>. Tal for ugen finder du her.</>}</p>
          {isAdmin && <ReportSettingsForm wsId={ws.id} initial={settings} />}
          <p className="text-[13px] text-muted">Du kan også bede assistenten: «Send rapporten kl. 18».</p>
        </div>
        {(isAdmin || ws.role === "staff") && (
          <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
            <span className="eyebrow">Det kostede ugen</span>
            <p className="font-display font-extrabold text-[30px] leading-none text-ink">{w.campaign_net_minor !== undefined ? `${kr(w.campaign_net_minor)} ekstra` : `${w.campaign_calls} kampagneopkald`}</p>
            <p className="text-[14px] text-ink-soft">Indgående opkald er med i abonnementet. Kampagneopkald i ugen: {w.campaign_calls} (4 kr. pr. udgående opkald, ekskl. moms).</p>
            {isAdmin && <Link href="/app/konto/fakturering" className="text-[14px] font-semibold text-accent hover:underline">Se abonnement og fakturaer →</Link>}
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
