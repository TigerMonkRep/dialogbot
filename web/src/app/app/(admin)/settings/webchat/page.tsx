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
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">Webchat-indstillingerne kan ses af medarbejdere, administratorer og ejere.</p>;
  }
  const [s, caps] = await Promise.all([
    backend<WebchatSettings>(`/workspaces/${ws.id}/webchat`),
    backend<{ items: Capability[] }>("/integrations/capabilities"),
  ]);
  const status = caps.items.find((c) => c.key === "webchat")?.status ?? "not_implemented";
  return (
    <section className="flex flex-col gap-4">
      <div className="bg-paper rounded-2xl p-3 md:p-4 border-2 border-ink flex flex-col gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <span className="eyebrow">Indstillinger</span>
            <h2 className="font-display text-headline-sm text-ink font-bold">Webchat på jeres hjemmeside</h2>
            <p className="text-body-sm text-ink-soft max-w-2xl">Assistenten svarer kun ud fra godkendt viden og vises kun på de domæner, I angiver. Samtalerne lander i <Link href="/app/inbox" className="text-ink underline">indbakken</Link>.</p>
          </div>
          <StatusPill s={s} />
        </div>
        {status === "simulated" && <p className="p-2 rounded-lg bg-accent-soft text-accent-deep text-body-sm">Testmiljø: svarene kommer fra en simuleret model, ikke en rigtig AI.</p>}
        {!s.available && s.unavailable_reasons.length > 0 && (
          <ul className="flex flex-col gap-1 p-3 rounded-lg bg-panel">
            {s.unavailable_reasons.map((r) => <li key={r} className="flex items-start gap-1 text-body-sm text-ink"><Icon name="radio_button_unchecked" size={18} className="text-ink mt-0.5" />{REASON[r] ?? r}</li>)}
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
  no_approved_knowledge: <>Der er ingen godkendt viden endnu – godkend mindst ét emne i <Link href="/app/knowledge" className="text-ink underline">videnscentret</Link>.</>,
};

function StatusPill({ s }: { s: WebchatSettings }) {
  const [label, cls] = s.available ? ["Aktiv på jeres domæner", "bg-success-soft text-success"]
    : s.enabled ? ["Slået til – mangler noget", "bg-accent-soft text-accent-deep"] : ["Slået fra", "bg-line text-ink-soft"];
  return <span className={`px-3 py-1 rounded-full text-label-sm font-semibold ${cls}`}>{label}</span>;
}
