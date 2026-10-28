import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { BookingSettingsForm, TypesEditor, type Settings } from "./booking-forms";

/** Booking in Alle indstillinger: online booking on/off, the rules, the calendar address and the booking types. */
export default async function BookingSheet() {
  const ws = await requireWorkspace();
  if (ws.role === "owner" || ws.role === "admin") {
    const s = await backend<Settings>(`/workspaces/${ws.id}/bookings/settings`);
    return <div className="flex flex-col gap-4"><TypesEditor wsId={ws.id} types={s.types} /><BookingSettingsForm wsId={ws.id} s={s} /></div>;
  }
  return <p className="rounded-2xl border-2 border-ink bg-paper p-6 text-[15px] text-ink-soft">Kun ejere og administratorer kan ændre bookingindstillinger.</p>;
}
