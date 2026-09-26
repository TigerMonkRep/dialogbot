import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { BookingSettingsForm, CancelBooking, ManualBooking, TypesEditor, type Settings } from "./client";

type Booking = { id: string; title: string; label: string; starts_at: string; source: string; contact_name: string; contact_phone: string | null; contact_email: string | null; note: string; lead_id: string | null };
const SOURCE: Record<string, string> = { webchat: "Webchat", phone: "Telefon", manual: "Manuelt" };

/** Bookings: upcoming appointments, manual booking, and (owner/admin) online booking + calendar settings. */
export default async function BookingsPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Bookinger kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [s, list] = await Promise.all([
    backend<Settings>(`/workspaces/${ws.id}/bookings/settings`),
    backend<{ items: Booking[]; timezone: string }>(`/workspaces/${ws.id}/bookings?days=60`),
  ]);
  const byDay = new Map<string, Booking[]>();
  for (const b of list.items) {
    const d = new Date(b.starts_at).toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long", timeZone: list.timezone });
    byDay.set(d, [...(byDay.get(d) ?? []), b]);
  }
  const activeTypes = s.types.filter((t) => t.active);
  return (
    <section className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div>
          <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Bookinger</span>
          <h1 className="font-headline-md text-headline-md text-primary font-bold">Aftaler</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Kunder kan booke i chatten og i telefonen ud fra jeres godkendte åbningstider. Optaget tid i jeres kalender blokeres, og hver booking bliver en henvendelse med en opgave.</p>
        </div>
        <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm font-semibold ${s.enabled ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{s.enabled ? "Online booking er slået til" : "Online booking er slået fra"}</span>
      </div>
      {!s.has_opening_hours && <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm">Der er ingen godkendte åbningstider, så der er ingen ledige tider. <Link href="/app/knowledge?tab=k03" className="underline">Godkend åbningstider i Viden</Link>.</p>}
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h2 className="font-headline-sm text-headline-sm text-primary">Kommende aftaler</h2>
        {list.items.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen aftaler de næste 60 dage.</p> : (
          [...byDay.entries()].map(([day, items]) => (
            <div key={day} className="flex flex-col gap-space-xs">
              <h3 className="font-label-lg text-label-lg text-on-surface-variant first-letter:uppercase">{day}</h3>
              <ul className="flex flex-col gap-space-xs">{items.map((b) => (
                <li key={b.id} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg bg-surface-container-low">
                  <Icon name="event" size={20} className="text-primary" />
                  <span className="font-label-lg text-label-lg text-primary">{new Date(b.starts_at).toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit", timeZone: list.timezone })}</span>
                  <span className="font-body-md text-body-md text-on-surface">{b.title}</span>
                  <span className="font-body-sm text-body-sm text-on-surface-variant">{[b.contact_phone, b.contact_email].filter(Boolean).join(" · ")}</span>
                  <span className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm">{SOURCE[b.source] ?? b.source}</span>
                  <span className="ml-auto flex items-center gap-space-sm">
                    {b.lead_id && <Link href={`/app/leads/${b.lead_id}`} className="font-label-md text-label-md text-primary underline">Henvendelse</Link>}
                    <CancelBooking wsId={ws.id} id={b.id} />
                  </span>
                </li>
              ))}</ul>
            </div>
          ))
        )}
      </div>
      {activeTypes.length > 0 && <ManualBooking wsId={ws.id} types={activeTypes} />}
      {canManage ? (
        <>
          <TypesEditor wsId={ws.id} types={s.types} />
          <BookingSettingsForm wsId={ws.id} s={s} />
        </>
      ) : <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejere og administratorer kan ændre bookingindstillinger.</p>}
    </section>
  );
}
