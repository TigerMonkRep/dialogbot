import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { getT } from "@/i18n/server";
import { setupStatus } from "@/lib/setup.server";
import { Sheet } from "./sheet";
import { SettingsTiles, type Chapter, type Row } from "./tiles";
import BookingSheet from "./_sheets/booking";
import ActivityPage from "../settings/activity/page";
import IntegrationsPage from "../settings/integrationer/page";
import TelephonyPage from "../settings/telephony/page";
import WebchatPage from "../settings/webchat/page";
import ReceptionPage from "../reception/page";
import VoicesPage from "../voices/page";

const SHEETS = ["telefoni", "hilsen", "stemmer", "webchat", "booking", "integrationer", "log"];

type Tel = { status: { code: string; label: string; next_step: string }; business_number: string | null };
type Web = { enabled: boolean; available: boolean; allowed_origins: string[] };
type Book = { enabled: boolean; lead_time_hours: number; horizon_days: number; buffer_minutes: number; types: { active: boolean }[]; busy_ics_url: string | null; has_opening_hours: boolean };
type Goals = { product_intent: string; callback: boolean; booking: boolean; inbound_phone: boolean; webchat: boolean };
type Cat = { items: { key: string; label: string; status: string; account_label: string; simulated?: boolean }[] };
type Voices = { settings: { standard_voice: string | null; standard_default: string; default_profile_id: string | null } };

/** «Alle indstillinger»: everything Dialogbot knows and does, as eight chapters of tiles. Simple values go through the assistant; forms open as sheets. */
export default async function IndstillingerPage({ searchParams }: { searchParams: Promise<{ ark?: string; page?: string }> }) {
  const ws = await requireWorkspace();
  const t = await getT("settings");
  const sp = await searchParams;
  const staff = ws.role !== "reader";
  const settle = async <T,>(p: Promise<T>) => p.catch(() => null);
  const [st, tel, web, book, goals, know, cat, members, script, voices, acc] = await Promise.all([
    staff ? settle(setupStatus(ws.id, ws.role)) : null,
    staff ? settle(backend<Tel>(`/workspaces/${ws.id}/telephony`)) : null,
    staff ? settle(backend<Web>(`/workspaces/${ws.id}/webchat`)) : null,
    staff ? settle(backend<Book>(`/workspaces/${ws.id}/bookings/settings`)) : null,
    settle(backend<Goals>(`/workspaces/${ws.id}/goals`)),
    settle(backend<{ items: unknown[]; knowledge_revision: number }>(`/workspaces/${ws.id}/assistant/knowledge`)),
    staff ? settle(backend<Cat>(`/workspaces/${ws.id}/integrations`)) : null,
    settle(backend<unknown[]>(`/workspaces/${ws.id}/members`)),
    staff ? settle(backend<{ greeting: string }>(`/workspaces/${ws.id}/reception/script`)) : null,
    staff ? settle(backend<Voices>(`/workspaces/${ws.id}/voices`)) : null,
    settle(backend<{ configured: boolean; test_mode?: boolean }>(`/workspaces/${ws.id}/billing/account`)),
  ]);
  // «Klar» means it works now: a simulated connection says so, and the two tiles below follow the real state
  const sim = (c: { label: string; account_label?: string; simulated?: boolean }, text: string) => (c.simulated ? `${text} (${t("overview.simulated")})` : text);
  const hooks = cat?.items.filter((i) => ["webhook", "zapier", "make"].includes(i.key) && i.status === "connected") ?? [];
  const calendar = cat?.items.find((i) => i.key.includes("calendar") && i.status === "connected");
  const connected = cat?.items.filter((i) => i.status === "connected") ?? [];
  const row = (r: Row) => r;
  // «Ringe kunder op» in trin 1 = product_intent campaigns/both – not the reception's «ring tilbage» (F-E2B-11-O03).
  const outbound = Boolean(goals && goals.product_intent !== "reception");
  const chapters: Chapter[] = [
    { n: 1, title: t("overview.phone.title"), sub: t("overview.phone.sub"), rows: [
      row({ label: t("overview.phone.number"), value: tel ? `${tel.status.label}${tel.business_number ? ` · ${tel.business_number}` : ""}` : "–", status: tel?.status.code === "active" ? "ready" : tel && tel.status.code !== "not_started" ? "soon" : "off", ark: "telefoni" }),
      row({ label: t("overview.phone.greeting"), value: script?.greeting ? `«${script.greeting.slice(0, 80)}${script.greeting.length > 80 ? "…" : ""}»` : t("overview.phone.greetingDefault"), status: script?.greeting ? "ready" : "soon", ark: "hilsen" }),
      row({ label: t("overview.phone.voice"), value: voices ? (voices.settings.default_profile_id ? t("overview.phone.voiceChosen") : t("overview.phone.voiceStandard", { name: voices.settings.standard_voice ?? voices.settings.standard_default })) : "–", status: voices ? "ready" : "off", ark: "stemmer" }),
    ] },
    { n: 2, title: t("overview.knowledge.title"), sub: t("overview.knowledge.sub"), rows: [
      row({ label: t("overview.knowledge.known"), value: know ? t("overview.knowledge.knownValue", { n: know.items.length, rev: know.knowledge_revision }) : "–", status: know && know.items.length > 0 ? "ready" : "off", href: "/app/viden" }),
      row({ label: t("overview.knowledge.about"), value: t("overview.knowledge.aboutValue"), status: "ready", href: "/opsaetning/1" }),
    ] },
    { n: 3, title: t("overview.channels.title"), sub: t("overview.channels.sub"), rows: [
      row({ label: t("overview.channels.webchat"), value: web ? (web.available ? t("overview.channels.activeOn", { n: web.allowed_origins.length }) : web.enabled ? t("overview.channels.onMissing") : t("overview.channels.off")) : "–", status: web?.available ? "ready" : web?.enabled ? "soon" : "off", ark: "webchat" }),
    ] },
    { n: 4, title: t("overview.booking.title"), sub: t("overview.booking.sub"), rows: [
      row({ label: t("overview.booking.online"), value: book ? t("overview.booking.onlineValue", { state: book.enabled ? t("overview.booking.on") : t("overview.booking.off"), n: book.types.filter((x) => x.active).length }) : "–", status: book?.enabled ? "ready" : "off", ark: "booking" }),
      row({ label: t("overview.booking.buffer"), value: book ? t("overview.booking.bufferValue", { n: book.buffer_minutes }) : "–", status: book ? "ready" : "off", say: t("overview.booking.bufferSay") }),
      row({ label: t("overview.booking.window"), value: book ? t("overview.booking.windowValue", { lead: book.lead_time_hours, horizon: book.horizon_days }) : "–", status: book ? "ready" : "off", say: t("overview.booking.windowSay") }),
      row({ label: t("overview.booking.appointments"), value: t("overview.booking.appointmentsValue"), status: "ready", href: "/app/aftaler" }),
    ] },
    { n: 5, title: t("overview.campaigns.title"), sub: t("overview.campaigns.sub"), rows: [
      row({ label: t("overview.campaigns.outbound"), value: outbound ? t("overview.campaigns.chosen") : t("overview.campaigns.notChosen"), status: outbound ? "ready" : "off", href: "/app/kampagner" }),
    ] },
    { n: 6, title: t("overview.systems.title"), sub: t("overview.systems.sub"), rows: [
      row({ label: t("overview.systems.calendar"), value: calendar ? sim(calendar, calendar.account_label || calendar.label) : book?.busy_ics_url ? t("overview.systems.ical") : t("overview.systems.notConnected"), status: calendar || book?.busy_ics_url ? "ready" : "off", ark: "integrationer" }),
      row({ label: t("overview.systems.connected"), value: connected.length ? connected.map((c) => sim(c, c.label)).join(", ") : t("overview.systems.none"), status: connected.length ? "ready" : "off", ark: "integrationer" }),
    ] },
    { n: 7, title: t("overview.team.title"), sub: t("overview.team.sub"), rows: [
      row({ label: t("overview.team.team"), value: members ? t("overview.team.teamValue", { n: members.length }) : "–", status: "ready", href: "/app/konto" }),
      row({ label: t("overview.team.billing"), value: t("overview.team.billingValue"), status: acc?.configured ? "ready" : "off", href: "/app/konto" }),
    ] },
    { n: 8, title: t("overview.tech.title"), sub: t("overview.tech.sub"), rows: [
      row({ label: t("overview.tech.embed"), value: t("overview.tech.embedValue"), status: web?.enabled ? "ready" : "off", ark: "webchat", tech: true }),
      row({ label: t("overview.tech.webhooks"), value: t("overview.tech.webhooksValue"), status: hooks.length ? (hooks.some((h) => h.simulated) ? "soon" : "ready") : "off", ark: "integrationer", tech: true }),
      row({ label: t("overview.tech.log"), value: t("overview.tech.logValue"), status: "ready", ark: "log", tech: true }),
    ] },
  ];
  const ark = sp.ark && SHEETS.includes(sp.ark) ? sp.ark : null;
  const pageParam = Promise.resolve({ page: sp.page });
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Link href="/app" className="text-[14px] font-semibold text-accent hover:underline w-fit">{t("overview.back")}</Link>
        <span className="eyebrow">{t("overview.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("overview.title")}</h1>
        <p className="text-[15px] leading-relaxed text-ink-soft max-w-[640px]">{t("overview.intro")}</p>
      </div>
      {/* Set up by hand here or in the guide – both count; the way back to the guide while it is not finished. */}
      {st && !st.done && (
        <Link href={`/opsaetning/${st.next}`} className="flex flex-wrap items-center gap-3 px-5 py-4 rounded-2xl border-2 border-dashed border-ink bg-paper hover:bg-panel">
          <span className="flex-1 min-w-[200px] text-[15px] font-semibold text-ink">{t("overview.guide", { n: st.next })}</span>
          <span className="text-[14px] font-semibold text-ink underline underline-offset-2">{t("overview.guideCta")}</span>
        </Link>
      )}
      <SettingsTiles chapters={chapters} canChange={staff} />
      {ark && (
        <Sheet title={t(`overview.sheets.${ark}`)} closeLabel={t("sheet.close")}>
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
