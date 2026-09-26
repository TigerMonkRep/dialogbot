import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { NumberForm, NumberRow, type PhoneNumber } from "./client";

type Calls = { items: { id: string; from_number: string | null; to_number: string | null; started_at: string | null; duration_seconds: number | null; summary: string; conversation_id: string | null }[] };

/** S03: inbound telephony via Vapi. The customer buys/imports the number at Vapi; we only map it. */
export default async function TelephonyPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Telefoni kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [nums, calls] = await Promise.all([
    backend<{ items: PhoneNumber[]; webhook_url: string; configured: boolean }>(`/workspaces/${ws.id}/phone-numbers`),
    backend<Calls>(`/workspaces/${ws.id}/calls?limit=10`),
  ]);
  return (
    <section className="flex flex-col gap-space-lg">
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <div className="flex flex-wrap items-start justify-between gap-space-md">
          <div>
            <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Indstillinger</span>
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Telefoni</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Assistenten tager telefonen på jeres nummer via Vapi og svarer kun ud fra godkendt viden. Opkald lander i <Link href="/app/inbox" className="text-primary underline">indbakken</Link>, og kunder, der vil ringes op, bliver til <Link href="/app/leads" className="text-primary underline">henvendelser</Link>.</p>
          </div>
          <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm font-semibold ${nums.configured ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{nums.configured ? "Stemmeforbindelse konfigureret" : "Ikke konfigureret"}</span>
        </div>
        {!nums.configured && <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm">Serveren mangler <code>VAPI_SERVER_SECRET</code>, så opkald kan ikke modtages endnu. Ingen numre er købt eller forbundet af Dialogbot.</p>}
        <ol className="list-decimal pl-5 flex flex-col gap-1 font-body-sm text-body-sm text-on-surface">
          <li>Opret eller importér et nummer i Vapi (fra Vapi eller jeres Twilio-konto).</li>
          <li>Sæt nummerets <em>Server URL</em> i Vapi til <code className="px-1 rounded bg-surface-container-low break-all">{nums.webhook_url}</code> med en Bearer-legitimation (samme hemmelighed som <code>VAPI_SERVER_SECRET</code>), og lad assistenten være tom, så Dialogbot leverer den.</li>
          <li>Tilknyt nummeret herunder med Vapis nummer-id.</li>
          <li>Viderestil jeres eksisterende nummer til Vapi-nummeret hos teleselskabet, og ring et prøveopkald.</li>
        </ol>
      </div>
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <h3 className="font-headline-sm text-headline-sm text-primary">Numre</h3>
        {nums.items.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen numre tilknyttet.</p> : (
          <ul className="flex flex-col gap-space-sm">{nums.items.map((n) => <NumberRow key={n.id} wsId={ws.id} n={n} canManage={canManage} />)}</ul>
        )}
        {canManage ? <NumberForm wsId={ws.id} /> : <p className="font-body-sm text-body-sm text-on-surface-variant">Kun ejere og administratorer kan tilknytte numre.</p>}
      </div>
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
        <h3 className="font-headline-sm text-headline-sm text-primary">Seneste opkald</h3>
        {calls.items.length === 0 ? <p className="font-body-sm text-body-sm text-on-surface-variant">Ingen opkald endnu.</p> : (
          <ul className="flex flex-col gap-space-xs">{calls.items.map((c) => (
            <li key={c.id}>
              <Link href={c.conversation_id ? `/app/inbox/${c.conversation_id}` : "#"} className="flex flex-wrap items-center gap-space-sm p-space-sm rounded-lg hover:bg-surface-container-low">
                <Icon name="call" size={18} className="text-primary" />
                <span className="font-label-lg text-label-lg text-primary">{c.from_number ?? "Skjult nummer"}</span>
                <span className="font-body-sm text-body-sm text-on-surface-variant">{c.started_at ? new Date(c.started_at).toLocaleString("da-DK", { dateStyle: "short", timeStyle: "short" }) : ""}{c.duration_seconds != null ? ` · ${Math.floor(c.duration_seconds / 60)}:${String(c.duration_seconds % 60).padStart(2, "0")} min` : ""}</span>
                <span className="w-full font-body-sm text-body-sm text-on-surface truncate">{c.summary}</span>
              </Link>
            </li>
          ))}</ul>
        )}
      </div>
    </section>
  );
}
