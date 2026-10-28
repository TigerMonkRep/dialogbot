import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { BookForCustomer, BookingCard, CalendarTools } from "./client";
import type { Booking, Settings } from "./types";

const iso = (d: Date) => d.toISOString().slice(0, 10);
const at = (s: string) => new Date(`${s}T12:00:00Z`);
const addDays = (s: string, n: number) => { const d = at(s); d.setUTCDate(d.getUTCDate() + n); return iso(d); };
const monday = (s: string) => { const d = at(s); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); return iso(d); };
const isoWeek = (s: string) => {
  const d = at(s); d.setUTCDate(d.getUTCDate() + 3 - ((d.getUTCDay() + 6) % 7));
  const first = new Date(Date.UTC(d.getUTCFullYear(), 0, 4));
  return 1 + Math.round(((d.getTime() - first.getTime()) / 86400000 - 3 + ((first.getUTCDay() + 6) % 7)) / 7);
};
const WD = ["Man", "Tir", "Ons", "Tor", "Fre", "Lør", "Søn"];
const DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"];
const DA_DAY = ["man", "tir", "ons", "tor", "fre", "lør", "søn"];

/** «Aftaler»: the week with the appointments Dialogbot booked, a form to book for a customer, calendar status and the booking rules. */
export default async function AftalerPage({ searchParams }: { searchParams: Promise<{ uge?: string; navn?: string; telefon?: string }> }) {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">Aftaler kan ses af medarbejdere, administratorer og ejere.</p>;
  const { uge, navn, telefon } = await searchParams;
  const today = new Date().toLocaleDateString("sv-SE", { timeZone: "Europe/Copenhagen" });
  const start = monday(uge && /^\d{4}-\d{2}-\d{2}$/.test(uge) ? uge : today);
  const [s, list] = await Promise.all([
    backend<Settings>(`/workspaces/${ws.id}/bookings/settings`),
    backend<{ items: Booking[]; timezone: string }>(`/workspaces/${ws.id}/bookings?start=${start}&end=${addDays(start, 6)}`),
  ]);
  const tz = list.timezone;
  const dayOf = (b: Booking) => new Date(b.starts_at).toLocaleDateString("sv-SE", { timeZone: tz });
  const byDay = new Map<string, Booking[]>();
  for (const b of list.items) byDay.set(dayOf(b), [...(byDay.get(dayOf(b)) ?? []), b]);
  const days = [0, 1, 2, 3, 4, 5, 6].map((i) => ({ i, date: addDays(start, i) })).filter((d) => d.i < 5 || s.open_weekdays.includes(d.i) || byDay.has(d.date));
  const canChange = ws.role !== "reader";
  const activeTypes = s.types.filter((t) => t.active);
  const isNow = start === monday(today);
  const hours = Object.entries(s.opening_hours).map(([d, rows]) => `${DA_DAY[DAYS.indexOf(d)]} ${rows.join(", ")}`).join(" · ");
  return (
    <div className="flex flex-wrap gap-6 items-start">
      <section className="flex-[999_1_460px] min-w-0 flex flex-col gap-5">
        <div className="flex flex-col gap-1.5">
          <span className="eyebrow">I dag → Aftaler</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Aftaler, Dialogbot har booket</h1>
          <p className="text-[15px] leading-relaxed text-ink-soft max-w-[620px]">Flyt eller aflys her. Optaget tid i jeres kalender blokeres, og hver booking bliver en henvendelse med en opgave.</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="eyebrow mr-2">Uge {isoWeek(start)}</span>
          <Link href={`/app/aftaler?uge=${addDays(start, -7)}`} aria-label="Forrige uge" className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] rounded-full border-[1.5px] border-ink text-ink hover:bg-panel">‹</Link>
          <Link href="/app/aftaler" aria-current={isNow ? "page" : undefined} className={`inline-flex items-center min-h-[44px] px-4 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${isNow ? "bg-ink text-paper" : "text-ink hover:bg-panel"}`}>Denne uge</Link>
          <Link href={`/app/aftaler?uge=${addDays(start, 7)}`} aria-label="Næste uge" className="inline-flex items-center justify-center min-w-[44px] min-h-[44px] rounded-full border-[1.5px] border-ink text-ink hover:bg-panel">›</Link>
        </div>
        {!s.has_opening_hours && <p className="rounded-xl border-[1.5px] border-dashed border-ink bg-paper px-4 py-3 text-[14px] text-ink">Der er ingen godkendte åbningstider, så der er ingen ledige tider. <Link href="/app/viden" className="font-semibold text-accent underline">Tilføj åbningstider under «Det ved den»</Link>.</p>}
        <ol className="grid grid-cols-1 md:grid-cols-5 gap-3" aria-label="Ugens aftaler">
          {days.map(({ i, date }) => {
            const rows = byDay.get(date) ?? [];
            const closed = !s.open_weekdays.includes(i) && rows.length === 0;
            const isToday = date === today;
            return (
              <li key={date} className="flex flex-col gap-2 min-w-0">
                <span className={`inline-flex self-start px-3 py-1.5 rounded-full text-[13px] font-semibold border-[1.5px] border-ink ${isToday ? "bg-highlight text-ink" : "bg-paper text-ink"}`}>{WD[i]} {at(date).getUTCDate()}.</span>
                {closed ? <p className="rounded-xl border-[1.5px] border-dashed border-ink px-3 py-3 text-[13px] text-muted">Lukket · Dialogbot booker ikke</p>
                  : rows.length === 0 ? <p className="rounded-xl border-[1.5px] border-dashed border-line px-3 py-3 text-[13px] text-muted">Ingen aftaler</p>
                  : <ul className="flex flex-col gap-2">{rows.map((b) => <BookingCard key={b.id} wsId={ws.id} b={b} tz={tz} canChange={canChange} />)}</ul>}
              </li>
            );
          })}
        </ol>
      </section>

      <aside className="flex-[1_1_320px] min-w-0 max-w-[440px] flex flex-col gap-5">
        <div className="flex flex-col gap-3 px-5 py-5 rounded-2xl bg-paper border-2 border-ink shadow-block">
          <h2 className="font-display font-extrabold text-[20px] text-ink">Book for en kunde</h2>
          {activeTypes.length === 0 ? (
            <p className="text-[14px] text-ink-soft">Der er ingen bookingtyper endnu. <Link href="/app/indstillinger?ark=booking" className="font-semibold text-accent underline">Opret en under Alle indstillinger → Booking</Link>.</p>
          ) : <BookForCustomer wsId={ws.id} types={activeTypes} initialName={navn ?? ""} initialPhone={telefon ?? ""} />}
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">Kalender</span>
          <p className="text-[15px] font-semibold text-ink">{s.busy_ics_url ? (s.busy_error ? "Kunne ikke læse kalenderen" : "Forbundet") : "Ikke forbundet"}</p>
          <p className="text-[14px] text-ink-soft">
            {s.busy_ics_url ? (s.busy_error ? s.busy_error : `Sidst læst ${s.busy_synced_at ? new Date(s.busy_synced_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short", timeZone: tz }) : "–"} · ${s.busy_blocks} optagne perioder. Dialogbot ser kun, hvornår I er optaget.`)
              : "Uden kalender kender Dialogbot kun åbningstiderne og de aftaler, den selv har booket."}
          </p>
          {canChange && <CalendarTools wsId={ws.id} feedUrl={s.feed_url} hasIcs={!!s.busy_ics_url} />}
          <Link href="/app/indstillinger?ark=integrationer" className="text-[14px] font-semibold text-accent hover:underline">Forbind eller skift kalender →</Link>
        </div>
        <div className="flex flex-col gap-2 px-5 py-5 rounded-2xl bg-paper border-2 border-ink">
          <span className="eyebrow">Sådan booker den</span>
          <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 text-[14px]">
            <dt className="text-muted">Online booking</dt><dd className="text-ink font-semibold">{s.enabled ? "Slået til" : "Slået fra"}</dd>
            <dt className="text-muted">Hvornår</dt><dd className="text-ink">{hours || "Ingen åbningstider"}</dd>
            <dt className="text-muted">Tidligst</dt><dd className="text-ink">{s.lead_time_hours === 0 ? "med det samme" : `${s.lead_time_hours} timer frem`} · højst {s.horizon_days} dage frem</dd>
            <dt className="text-muted">Pause</dt><dd className="text-ink">{s.buffer_minutes} min mellem aftaler</dd>
            <dt className="text-muted">Typer</dt><dd className="text-ink">{activeTypes.map((t) => `${t.name} ${t.duration_minutes} min`).join(" · ") || "Ingen"}</dd>
          </dl>
          <p className="text-[13px] text-muted">Sig det til assistenten – den viser reglen, før den gælder. Alle regler: <Link href="/app/indstillinger?ark=booking" className="font-semibold text-accent hover:underline">Alle indstillinger → Booking</Link>.</p>
        </div>
      </aside>
    </div>
  );
}
