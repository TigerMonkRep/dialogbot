import { redirect } from "next/navigation";
import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Need } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { Step2, type BookingSettings, type Connector } from "./step2";

/** Trin 2 af 3 – Kalender & systemer. Only when «Booke aftaler» was chosen in trin 1. */
export default async function Trin2({ searchParams }: { searchParams: Promise<{ connected?: string; error?: string; connector?: string }> }) {
  const ws = await requireWorkspace();
  const q = await searchParams;
  const [st, booking, cat] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<BookingSettings>(`/workspaces/${ws.id}/bookings/settings`).catch(() => null),
    backend<{ items: Connector[] }>(`/workspaces/${ws.id}/integrations`).catch(() => ({ items: [] as Connector[] })),
  ]);
  if (!st.goals.booking || !booking) redirect("/opsaetning/3");
  const LABEL: Record<string, string> = { google_calendar: "Google Kalender", microsoft_calendar: "Microsoft 365-kalender" };
  const notice = q.connected ? { kind: "ok" as const, text: `${LABEL[q.connected] ?? q.connected} er forbundet.` }
    : q.error ? { kind: "error" as const, text: `${LABEL[q.connector ?? ""] ?? "Kalenderen"} blev ikke forbundet (${q.error}). Prøv igen, eller spring over.` } : null;
  const connected = cat.items.some((c) => ["google_calendar", "microsoft_calendar"].includes(c.key) && c.status === "connected");
  const steps = [...st.steps] as typeof st.steps;
  steps[1] = connected ? "done" : "todo";
  return (
    <SetupShell step={2} steps={steps} workspaceName={ws.name} wide later assistant={{ wsId: ws.id, canChange: ws.role !== "reader" }}>
      <div className="flex flex-col gap-3 mb-6">
        <div className="flex items-center gap-4">
          <span className="w-14 h-14 rounded-[14px] bg-highlight text-ink font-display font-extrabold text-[30px] inline-flex items-center justify-center" aria-hidden>2</span>
          <div>
            <span className="eyebrow">Trin 2 af 3</span>
            <h1 className="font-display font-extrabold text-[30px] md:text-[40px] leading-[1.05] tracking-[-1px] text-ink">Hvor skal aftalerne lande?</h1>
          </div>
        </div>
        <Need items={[["1×", "login til din kalender"], ["2", "minutter"]]} />
      </div>
      <Step2 wsId={ws.id} canManage={ws.role === "owner" || ws.role === "admin"} connectors={cat.items} booking={booking} goals={st.goals} notice={notice} />
    </SetupShell>
  );
}
