import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Sheet } from "./sheet";
import { SettingsTiles, type Chapter, type Row } from "./tiles";
import BookingSheet from "./_sheets/booking";
import ActivityPage from "../settings/activity/page";
import IntegrationsPage from "../settings/integrationer/page";
import TelephonyPage from "../settings/telephony/page";
import WebchatPage from "../settings/webchat/page";
import ReceptionPage from "../reception/page";
import VoicesPage from "../voices/page";

const SHEETS: Record<string, string> = { telefoni: "Telefon", hilsen: "Hilsen og manuskript", stemmer: "Stemme", webchat: "Webchat og domæner", booking: "Booking", integrationer: "Kalender og systemer", log: "Historik" };

type Tel = { status: { code: string; label: string; next_step: string }; business_number: string | null };
type Web = { enabled: boolean; available: boolean; allowed_origins: string[] };
type Book = { enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number; types: { active: boolean }[]; busy_ics_url: string | null; has_opening_hours: boolean };
type Goals = { callback: boolean; booking: boolean; inbound_phone: boolean; webchat: boolean };
type Cat = { items: { key: string; label: string; status: string; account_label: string }[] };
type Voices = { settings: { standard_voice: string | null; standard_default: string; default_profile_id: string | null } };

/** «Alle indstillinger»: everything Dialogbot knows and does, as eight chapters of tiles. Simple values go through the assistant; forms open as sheets. */
export default async function IndstillingerPage({ searchParams }: { searchParams: Promise<{ ark?: string; page?: string }> }) {
  const ws = await requireWorkspace();
  const sp = await searchParams;
  const staff = ws.role !== "reader";
  const settle = async <T,>(p: Promise<T>) => p.catch(() => null);
  const [tel, web, book, goals, know, cat, members, script, voices] = await Promise.all([
    staff ? settle(backend<Tel>(`/workspaces/${ws.id}/telephony`)) : null,
    staff ? settle(backend<Web>(`/workspaces/${ws.id}/webchat`)) : null,
    staff ? settle(backend<Book>(`/workspaces/${ws.id}/bookings/settings`)) : null,
    settle(backend<Goals>(`/workspaces/${ws.id}/goals`)),
    settle(backend<{ items: unknown[]; knowledge_revision: number }>(`/workspaces/${ws.id}/assistant/knowledge`)),
    staff ? settle(backend<Cat>(`/workspaces/${ws.id}/integrations`)) : null,
    settle(backend<unknown[]>(`/workspaces/${ws.id}/members`)),
    staff ? settle(backend<{ greeting: string }>(`/workspaces/${ws.id}/reception/script`)) : null,
    staff ? settle(backend<Voices>(`/workspaces/${ws.id}/voices`)) : null,
  ]);
  const calendar = cat?.items.find((i) => i.key.includes("calendar") && i.status === "connected");
  const connected = cat?.items.filter((i) => i.status === "connected") ?? [];
  const row = (r: Row) => r;
  const chapters: Chapter[] = [
    { n: 1, title: "Telefon", sub: "Nummer, hilsen og stemme", rows: [
      row({ label: "Nummer", value: tel ? `${tel.status.label}${tel.business_number ? ` · ${tel.business_number}` : ""}` : "–", status: tel?.status.code === "active" ? "ready" : tel && tel.status.code !== "not_started" ? "soon" : "off", ark: "telefoni" }),
      row({ label: "Hilsen", value: script?.greeting ? `«${script.greeting.slice(0, 80)}${script.greeting.length > 80 ? "…" : ""}»` : "Standardhilsen", status: script?.greeting ? "ready" : "soon", ark: "hilsen" }),
      row({ label: "Stemme", value: voices ? (voices.settings.default_profile_id ? "Valgt stemme" : `Standard: ${voices.settings.standard_voice ?? voices.settings.standard_default}`) : "–", status: voices ? "ready" : "off", ark: "stemmer" }),
    ] },
    { n: 2, title: "Viden", sub: "Hvad den ved, og hvad den ikke må", rows: [
      row({ label: "Det ved den", value: know ? `${know.items.length} godkendte emner · revision ${know.knowledge_revision}` : "–", status: know && know.items.length > 0 ? "ready" : "off", href: "/app/viden" }),
      row({ label: "Om virksomheden", value: "Navn, hvad I laver, adresse, sprog", status: "ready", href: "/opsaetning/1" }),
    ] },
    { n: 3, title: "Kanaler", sub: "Hvor kunderne kan række ud", rows: [
      row({ label: "Webchat", value: web ? (web.available ? `Aktiv på ${web.allowed_origins.length} domæne(r)` : web.enabled ? "Slået til – mangler noget" : "Slået fra") : "–", status: web?.available ? "ready" : web?.enabled ? "soon" : "off", ark: "webchat" }),
    ] },
    { n: 4, title: "Booking", sub: "Kalender og regler for aftaler", rows: [
      row({ label: "Online booking", value: book ? `${book.enabled ? "Slået til" : "Slået fra"} · ${book.types.filter((t) => t.active).length} typer` : "–", status: book?.enabled ? "ready" : "off", ark: "booking" }),
      row({ label: "Pause mellem aftaler", value: book ? `${book.buffer_minutes} min` : "–", status: book ? "ready" : "off", say: "Sæt pausen mellem aftaler til " }),
      row({ label: "Tidligst og højst", value: book ? `${book.lead_time_hours} timer frem · højst ${book.horizon_days} dage frem` : "–", status: book ? "ready" : "off", say: "Hvor langt frem må kunderne booke? Skriv fx «højst 30 dage frem»." }),
      row({ label: "Aftaler", value: "Ugens aftaler og book for en kunde", status: "ready", href: "/app/aftaler" }),
    ] },
    { n: 5, title: "Kampagner", sub: "Ring til jeres egne kunder", rows: [
      row({ label: "Udgående opkald", value: goals?.callback ? "Valgt – 4 kr. pr. opkald ekskl. moms" : "Ikke valgt", status: goals?.callback ? "ready" : "off", href: "/app/kampagner" }),
    ] },
    { n: 6, title: "Systemer", sub: "Kalender og jeres egne værktøjer", rows: [
      row({ label: "Kalender", value: calendar ? calendar.account_label || calendar.label : book?.busy_ics_url ? "iCal-adresse" : "Ikke forbundet", status: calendar || book?.busy_ics_url ? "ready" : "off", ark: "integrationer" }),
      row({ label: "Forbundne systemer", value: connected.length ? connected.map((c) => c.label).join(", ") : "Ingen endnu", status: connected.length ? "ready" : "off", ark: "integrationer" }),
    ] },
    { n: 7, title: "Team og konto", sub: "Hvem må hvad, abonnement og fakturaer", rows: [
      row({ label: "Team", value: members ? `${members.length} med adgang` : "–", status: "ready", href: "/app/konto" }),
      row({ label: "Abonnement og fakturaer", value: "Fra 2.495 kr./md. ekskl. moms", status: "ready", href: "/app/konto" }),
    ] },
    { n: 8, title: "Teknik", sub: "For dig, der vil se det hele", rows: [
      row({ label: "Webchat-kode og widgetnøgle", value: "Indlejringskode til hjemmesiden", status: web?.enabled ? "ready" : "off", ark: "webchat", tech: true }),
      row({ label: "Webhooks og Zapier", value: "Signerede webhooks til jeres systemer", status: "ready", ark: "integrationer", tech: true }),
      row({ label: "Log og eksport", value: "Alle ændringer, nyeste først", status: "ready", ark: "log", tech: true }),
    ] },
  ];
  const ark = sp.ark && sp.ark in SHEETS ? sp.ark : null;
  const pageParam = Promise.resolve({ page: sp.page });
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Link href="/app" className="text-[14px] font-semibold text-accent hover:underline w-fit">← Tilbage til I dag</Link>
        <span className="eyebrow">Bagerst i hæftet</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Alle indstillinger</h1>
        <p className="text-[15px] leading-relaxed text-ink-soft max-w-[640px]">Alt, Dialogbot ved og gør – ét sted, i almindeligt dansk. «Ændr» på en enkel værdi sender det til assistenten, som viser ændringen, før den gælder. Større formularer åbner som et ark.</p>
      </div>
      <SettingsTiles chapters={chapters} canChange={staff} />
      {ark && (
        <Sheet title={SHEETS[ark]}>
          {ark === "telefoni" && <TelephonyPage />}
          {ark === "hilsen" && <ReceptionPage />}
          {ark === "stemmer" && <VoicesPage />}
          {ark === "webchat" && <WebchatPage />}
          {ark === "booking" && <BookingSheet />}
          {ark === "integrationer" && <IntegrationsPage />}
          {ark === "log" && <ActivityPage searchParams={pageParam} />}
        </Sheet>
      )}
    </div>
  );
}
