import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { WebchatForm, type WebchatSettings } from "./client";

type Capability = { key: string; status: "available" | "simulated" | "not_implemented" };

/** W01: web widget settings, embed code and readiness. Only owners/admins change them; staff can read. */
export default async function WebchatPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Webchat-indstillingerne kan ses af medarbejdere, administratorer og ejere.</p>;
  }
  const [s, caps] = await Promise.all([
    backend<WebchatSettings>(`/workspaces/${ws.id}/webchat`),
    backend<{ items: Capability[] }>("/integrations/capabilities"),
  ]);
  const status = caps.items.find((c) => c.key === "webchat")?.status ?? "not_implemented";
  return (
    <section className="flex flex-col gap-space-lg">
      <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-md">
        <div className="flex flex-wrap items-start justify-between gap-space-md">
          <div>
            <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">W01</span>
            <h2 className="font-headline-sm text-headline-sm text-primary font-bold">Webchat på jeres hjemmeside</h2>
            <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Assistenten svarer kun ud fra godkendt viden og vises kun på de domæner, I angiver. Samtalerne lander i <Link href="/app/inbox" className="text-primary underline">indbakken</Link>.</p>
          </div>
          <StatusPill s={s} />
        </div>
        {status === "simulated" && <p className="p-space-sm rounded-lg bg-tertiary-fixed text-on-tertiary-fixed font-body-sm text-body-sm">Testmiljø: svarene kommer fra en simuleret model, ikke en rigtig AI.</p>}
        {!s.available && s.unavailable_reasons.length > 0 && (
          <ul className="flex flex-col gap-space-xs p-space-md rounded-lg bg-surface-container-low">
            {s.unavailable_reasons.map((r) => <li key={r} className="flex items-start gap-space-xs font-body-sm text-body-sm text-on-surface"><Icon name="radio_button_unchecked" size={18} className="text-outline mt-0.5" />{REASON[r] ?? r}</li>)}
          </ul>
        )}
      </div>
      <WebchatForm wsId={ws.id} initial={s} canManage={ws.role === "owner" || ws.role === "admin"} />
    </section>
  );
}

const REASON: Record<string, React.ReactNode> = {
  disabled: "Widgetten er slået fra.",
  no_allowed_origins: "Angiv mindst ét domæne, hvor widgetten må vises.",
  ai_not_configured: "Ingen AI-udbyder er konfigureret i dette miljø.",
  no_approved_knowledge: <>Der er ingen godkendt viden endnu – godkend mindst ét emne i <Link href="/app/knowledge" className="text-primary underline">videnscentret</Link>.</>,
};

function StatusPill({ s }: { s: WebchatSettings }) {
  const [label, cls] = s.available ? ["Aktiv på jeres domæner", "bg-secondary-container text-on-secondary-container"]
    : s.enabled ? ["Slået til – mangler noget", "bg-tertiary-fixed text-on-tertiary-fixed"] : ["Slået fra", "bg-surface-container-high text-on-surface-variant"];
  return <span className={`px-3 py-1 rounded-full font-label-sm text-label-sm font-semibold ${cls}`}>{label}</span>;
}
