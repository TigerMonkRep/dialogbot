"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "@/components/ui";
import { api, type ApiError } from "@/lib/client";

export type Connector = { key: string; label: string; availability: "ready" | "coming" | "via_zapier"; status: "not_connected" | "connected" | "error" | "not_implemented"; simulated: boolean; account_label: string; last_ok_at: string | null; error: string | null };
export type BookingSettings = { version: number; enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number; busy_ics_url: string | null; types: { id: string; name: string; duration_minutes: number; active: boolean }[] };

const ago = (iso: string | null) => {
  if (!iso) return "";
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000));
  return min < 1 ? "lige nu" : min < 60 ? `${min} min siden` : min < 1440 ? `${Math.round(min / 60)} t siden` : `${Math.round(min / 1440)} d siden`;
};
const cardCls = "rounded-2xl border-2 border-ink bg-paper p-5 flex flex-col gap-3 min-h-[170px]";

/** Trin 2 – Kalender & systemer. Optional: the owner can connect a calendar, or skip and let Dialogbot take a message. */
export function Step2({ wsId, canManage, connectors, booking, goals, notice }: { wsId: string; canManage: boolean; connectors: Connector[]; booking: BookingSettings; goals: { version: number; product_intent: string; guidance_mode: string; conversation_goals: string[]; inbound_phone: boolean; webchat: boolean; callback: boolean }; notice: { kind: "ok" | "error"; text: string } | null }) {
  const router = useRouter();
  useEffect(() => { document.cookie = "db_setup_return=; path=/; max-age=0"; }, []); // the return from the provider is handled
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const google = connectors.find((c) => c.key === "google_calendar");
  const ms = connectors.find((c) => c.key === "microsoft_calendar");
  const connected = connectors.some((c) => ["google_calendar", "microsoft_calendar"].includes(c.key) && c.status === "connected");

  const connect = async (c: Connector) => {
    setBusy(c.key); setError(null);
    try {
      // The provider sends the browser back to the integrations page; this cookie turns that return into «tilbage til trin 2».
      document.cookie = "db_setup_return=1; path=/; max-age=900; samesite=lax";
      const r = await api<{ status: string; authorize_url?: string }>(`/workspaces/${wsId}/integrations/${c.key}/connect`, { method: "POST", headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ config: {}, secrets: {} }) });
      if (r.status === "authorize" && r.authorize_url) { window.location.href = r.authorize_url; return; }
      router.refresh();
    } catch (e) { setError((e as ApiError).message ?? "Kunne ikke forbinde. Prøv igen."); }
    setBusy(null);
  };

  /** Sensible defaults the first time: one 45-minute appointment type, 15 minutes between appointments, from tomorrow. */
  const applyDefaults = async () => {
    if (booking.types.length > 0) return;
    await api(`/workspaces/${wsId}/bookings/types`, { method: "POST", body: JSON.stringify({ name: "Aftale", duration_minutes: 45, active: true }) });
    await api(`/workspaces/${wsId}/bookings/settings`, { method: "PUT", body: JSON.stringify({ enabled: true, lead_time_hours: 24, horizon_days: booking.horizon_days || 30, buffer_minutes: 15, busy_ics_url: booking.busy_ics_url, expected_version: booking.version }) });
  };
  const next = async () => {
    setBusy("next"); setError(null);
    try { await applyDefaults(); router.push("/opsaetning/3"); }
    catch (e) { setError((e as ApiError).message ?? "Kunne ikke gemme. Prøv igen."); setBusy(null); }
  };
  const skip = async () => {
    setBusy("skip"); setError(null);
    try {
      await api(`/workspaces/${wsId}/goals`, { method: "PUT", body: JSON.stringify({ product_intent: goals.product_intent, guidance_mode: goals.guidance_mode, conversation_goals: goals.conversation_goals, inbound_phone: goals.inbound_phone, webchat: goals.webchat, callback: goals.callback, booking: false, expected_version: goals.version }) });
      router.push("/opsaetning/3");
    } catch (e) { setError((e as ApiError).message ?? "Kunne ikke gemme. Prøv igen."); setBusy(null); }
  };

  const status = (c: Connector | undefined) => {
    if (!c || c.availability !== "ready" || c.status === "not_implemented") return <span className="text-[14px] text-muted">På vej – ikke tilgængelig endnu.</span>;
    if (c.status === "connected") return <span className="text-[14px] text-success font-semibold">Forbundet{c.account_label ? ` som ${c.account_label}` : ""}{c.last_ok_at ? ` · synk ${ago(c.last_ok_at)}` : ""}{c.simulated ? " (simuleret)" : ""}</span>;
    if (c.status === "error") return <span className="text-[14px] text-danger font-semibold">{c.error ?? "Forbindelsen fejlede"}</span>;
    return <span className="text-[14px] text-muted">Ikke forbundet</span>;
  };
  const card = (c: Connector | undefined, title: string) => {
    const usable = Boolean(c && c.availability === "ready" && c.status !== "not_implemented");
    return (
      <li className={cardCls}>
        <span className="w-10 h-10 rounded-[10px] bg-accent text-white inline-flex items-center justify-center"><Icon name="calendar_month" size={22} /></span>
        <h2 className="font-display font-extrabold text-[20px] text-ink">{title}</h2>
        {status(c)}
        {usable && c!.status !== "connected" && canManage && (
          <button type="button" onClick={() => connect(c!)} disabled={busy !== null} className="mt-auto self-start min-h-[44px] px-5 rounded-xl bg-accent text-white font-semibold hover:bg-accent-deep disabled:opacity-60">{busy === c!.key ? "Åbner …" : c!.status === "error" ? "Forbind igen" : "Forbind"}</button>
        )}
      </li>
    );
  };

  return (
    <div className="flex flex-col gap-6">
      {notice && <p role={notice.kind === "error" ? "alert" : "status"} className={`rounded-xl px-4 py-3 text-[14px] ${notice.kind === "ok" ? "bg-success-soft text-success" : "bg-danger-soft text-danger"}`}>{notice.text}</p>}
      <ul className="grid md:grid-cols-3 gap-4">
        {card(google, "Google Kalender")}
        {card(ms, "Microsoft 365 / Outlook")}
        <li className={cardCls}>
          <span className="w-10 h-10 rounded-[10px] bg-ink text-paper inline-flex items-center justify-center"><Icon name="add" size={22} /></span>
          <h2 className="font-display font-extrabold text-[20px] text-ink">Et andet system</h2>
          <p className="text-[14px] text-ink-soft">CRM, bookingsystem, fagsystem – fortæl os hvilket, så ser vi på det. Det er ikke forbundet, før det virker.</p>
          <Link href="/kontakt" className="mt-auto self-start inline-flex items-center min-h-[44px] px-5 rounded-xl border-2 border-ink bg-paper font-semibold hover:bg-panel">Skriv til os</Link>
        </li>
      </ul>
      {!canManage && <p className="text-[14px] text-muted">Kun ejere og administratorer kan forbinde systemer.</p>}

      <section className="rounded-2xl border-2 border-ink bg-paper p-5 flex flex-col gap-3">
        <h2 className="font-display font-extrabold text-[20px] text-ink">Det skriver Dialogbot i kalenderen</h2>
        <ul className="text-[15px] text-ink flex flex-col gap-1.5">
          <li><b className="font-display">1×</b> aftale med kundens navn, nummer og ærinde</li>
          <li><b className="font-display">1×</b> bekræftelse til jer med aftalens tidspunkt</li>
          <li><b className="font-display">0×</b> ændringer i jeres eksisterende aftaler – dem rører den aldrig</li>
        </ul>
        <p className="text-[14px] text-muted">Tiderne følger jeres åbningstider fra trin 1. Som start: aftaler på 45 minutter, 15 minutters pause og tidligst i morgen. Det kan ændres under Aftaler.</p>
      </section>

      {error && <p role="alert" className="text-[14px] text-danger">{error}</p>}
      <div className="fixed sm:static inset-x-0 bottom-0 z-20 bg-paper sm:bg-transparent border-t-2 sm:border-0 border-ink px-4 py-3 sm:p-0 pb-safe flex flex-col sm:flex-row sm:items-center gap-3">
        <button type="button" onClick={next} disabled={busy !== null} className={`inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-xl font-semibold text-[16px] disabled:opacity-60 ${connected ? "bg-accent text-white hover:bg-accent-deep" : "bg-paper text-accent border-2 border-accent hover:bg-panel"}`}>
          Videre til trin 3: test &amp; tænd<Icon name="arrow_forward" size={18} />
        </button>
        <button type="button" onClick={skip} disabled={busy !== null} className="min-h-[44px] px-2 text-[15px] font-semibold text-ink underline underline-offset-2">Spring over – jeg bruger ingen kalender</button>
      </div>
    </div>
  );
}
