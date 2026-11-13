import type { Metadata } from "next";
import { getT } from "@/i18n/server";
import { API_BASE_URL } from "@/lib/config";
import { BookingManager, type BookingView } from "./manage";

export async function generateMetadata(): Promise<Metadata> {
  const t = await getT("widget");
  return { title: t("customer.booking.metaTitle"), robots: { index: false, follow: false } };
}

/** W13: the business's customer sees the appointment they booked in the chat and moves or cancels it – after an SMS
 *  code to the booking's own number when it has one, and only until the business's lead time before the start. */
export default async function BookingManagePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const r = await fetch(`${API_BASE_URL}/api/v1/public/booking/manage/${encodeURIComponent(token)}`, { cache: "no-store" });
  const state = r.ok ? "ok" : r.status === 410 ? "expired" : r.status === 404 ? "invalid" : "error";
  const view: BookingView | null = r.ok ? await r.json() : null;
  return <BookingManager token={token} state={state} initial={view} />;
}
