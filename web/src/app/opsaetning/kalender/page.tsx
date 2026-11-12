import { redirect } from "next/navigation";
import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { nextStep, stepHref, stepNumber } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";
import { StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getRaw, getT } from "@/i18n/server";
import { Step2, type BookingSettings, type Connector } from "./step2";

/** Kalender – only when «Booke aftaler» was chosen under Virksomhed: where the appointments land. */
export default async function KalenderStep({ searchParams }: { searchParams: Promise<{ connected?: string; error?: string; connector?: string }> }) {
  const ws = await requireWorkspace();
  const q = await searchParams;
  const [st, booking, cat] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<BookingSettings>(`/workspaces/${ws.id}/bookings/settings`).catch(() => null),
    backend<{ items: Connector[] }>(`/workspaces/${ws.id}/integrations`).catch(() => ({ items: [] as Connector[] })),
  ]);
  if (!st.goals.booking || !booking) redirect(stepHref("betaling"));
  const t = await getT("setup.step2Page");
  const raw = await getRaw();
  const LABEL: Record<string, string> = { google_calendar: t("connector.google_calendar"), microsoft_calendar: t("connector.microsoft_calendar") };
  const notice = q.connected ? { kind: "ok" as const, text: t("connected", { name: LABEL[q.connected] ?? q.connected }) }
    : q.error ? { kind: "error" as const, text: t("error", { name: LABEL[q.connector ?? ""] ?? t("theCalendar"), error: q.error }) } : null;
  const connected = cat.items.some((c) => ["google_calendar", "microsoft_calendar"].includes(c.key) && c.status === "connected");
  const steps = st.steps.map((x) => (x.key === "kalender" ? { ...x, state: connected ? "done" as const : "todo" as const } : x));
  const n = stepNumber("kalender", st.goals);
  const next = nextStep("kalender", st.goals);
  const ts = await getT("setup.shell");
  return (
    <SetupShell step="kalender" steps={steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: ws.role !== "reader" }}>
      <StepHead n={n} eyebrow={t("eyebrow", { n, total: steps.length })} title={t("title")} need={raw<[string, string, string?][]>("setup.step2Page.need")} needTitle={raw<string>("setup.need.title")} />
      <Step2 wsId={ws.id} canManage={ws.role === "owner" || ws.role === "admin"} connectors={cat.items} booking={booking} goals={st.goals} notice={notice} nextHref={stepHref(next)} nextLabel={ts("next", { n: stepNumber(next, st.goals), label: ts(`labels.${next}`) })} />
    </SetupShell>
  );
}
