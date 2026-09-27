import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { VoiceLibrary, type VoicesData } from "./client";

type Plan = { checks: { key: string; status: string; label: string; runnable: boolean }[] };
type Me = { is_platform_operator?: boolean };

/** V01: Danish voice library – choose, listen, test the greeting, assign per assistant/campaign. */
export default async function VoicesPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Stemmer kan ses af medarbejdere, administratorer og ejere.</p>;
  const [data, plan, script, me] = await Promise.all([
    backend<VoicesData>(`/workspaces/${ws.id}/voices`),
    backend<Plan>(`/workspaces/${ws.id}/setup/plan`).catch(() => ({ checks: [] }) as Plan),
    backend<{ greeting: string }>(`/workspaces/${ws.id}/reception/script`).catch(() => ({ greeting: "" })),
    backend<Me>(`/auth/me`).catch(() => ({}) as Me),
  ]);
  const check = (k: string) => plan.checks.find((c) => c.key === k)?.status ?? "untested";
  const canManage = ws.role === "owner" || ws.role === "admin";
  return (
    <section className="flex flex-col gap-space-lg">
      <div className="flex flex-wrap items-start justify-between gap-space-sm">
        <div>
          <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Stemmer</span>
          <h1 className="font-headline-md text-headline-md text-primary font-bold">Dansk stemme til jeres assistent</h1>
          <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Vælg den stemme, kunderne hører i telefonen. Webchatten bruger ikke tale. Kun stemmer, der har bestået Dialogbots kontroller, kan vælges.</p>
        </div>
        <div className="flex flex-wrap gap-space-md">
          {canManage && <Link href="/app/voices/own" className="flex items-center gap-1 font-label-lg text-label-lg text-primary underline"><Icon name="mic" size={18} />Indtal jeres egen stemme</Link>}
          {me.is_platform_operator && <Link href="/app/operator/voices" className="flex items-center gap-1 font-label-lg text-label-lg text-primary underline"><Icon name="admin_panel_settings" size={18} />Operatørvisning</Link>}
        </div>
      </div>
      <VoiceLibrary wsId={ws.id} data={data} canManage={canManage} greeting={script.greeting}
        steps={{ heard: check("voice.heard"), testCall: check("telephony.test_call") }} />
    </section>
  );
}
