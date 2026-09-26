import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { ScriptEditor, type Script } from "./client";

type Overview = {
  channels: { phone: { configured: boolean; numbers: { e164: string; active: boolean; voice: boolean }[] }; webchat: { enabled: boolean; origins: number } };
  script_configured: boolean;
  last_7_days: { conversations: number; calls: number; leads: number };
};

/** Reception: channel status, the last 7 days and the manuscript the assistant follows in chat and on the phone. */
export default async function ReceptionPage() {
  const ws = await requireWorkspace();
  if (ws.role === "reader") return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Receptionen kan ses af medarbejdere, administratorer og ejere.</p>;
  const canManage = ws.role === "owner" || ws.role === "admin";
  const [ov, script, caps] = await Promise.all([
    backend<Overview>(`/workspaces/${ws.id}/reception/overview`),
    backend<Script>(`/workspaces/${ws.id}/reception/script`),
    backend<{ items: { key: string; status: string }[] }>("/integrations/capabilities"),
  ]);
  const aiReady = caps.items.some((c) => c.key === "ai.assistant_preview" && c.status !== "not_implemented");
  const phone = ov.channels.phone;
  const activeNumbers = phone.numbers.filter((n) => n.active);
  const Channel = ({ icon, title, ok, text, href, cta }: { icon: string; title: string; ok: boolean; text: string; href: string; cta: string }) => (
    <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col gap-space-sm">
      <div className="flex items-center justify-between gap-space-sm">
        <span className="flex items-center gap-space-xs font-label-lg text-label-lg text-primary font-bold"><Icon name={icon} size={20} />{title}</span>
        <span className={`px-2 py-0.5 rounded-full font-label-sm text-label-sm font-semibold ${ok ? "bg-secondary-container text-on-secondary-container" : "bg-surface-container-high text-on-surface-variant"}`}>{ok ? "Aktiv" : "Ikke aktiv"}</span>
      </div>
      <p className="font-body-sm text-body-sm text-on-surface-variant">{text}</p>
      <Link href={href} className="font-label-md text-label-md text-primary underline self-start">{cta}</Link>
    </div>
  );
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Reception</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Jeres digitale reception</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Assistenten svarer i telefonen og i chatten på jeres hjemmeside ud fra godkendt viden og manuskriptet herunder. Kunder, der vil kontaktes, bliver til henvendelser.</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
        <Channel icon="call" title="Telefon" ok={phone.configured && activeNumbers.length > 0}
          text={!phone.configured ? "Stemmeforbindelsen er ikke sat op på serveren." : activeNumbers.length ? `${activeNumbers.map((n) => n.e164).join(", ")}${activeNumbers.some((n) => !n.voice) ? " – mangler dansk stemme" : ""}` : "Intet aktivt nummer tilknyttet."}
          href="/app/settings/telephony" cta="Telefoni-indstillinger" />
        <Channel icon="chat" title="Webchat" ok={ov.channels.webchat.enabled} text={ov.channels.webchat.enabled ? `Aktiv på ${ov.channels.webchat.origins} domæne(r).` : "Widgetten er ikke slået til."} href="/app/settings/webchat" cta="Webchat-indstillinger" />
        <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm grid grid-cols-3 gap-space-sm text-center">
          {([["Samtaler", ov.last_7_days.conversations, "/app/inbox"], ["Opkald", ov.last_7_days.calls, "/app/settings/telephony"], ["Henvendelser", ov.last_7_days.leads, "/app/leads"]] as const).map(([l, v, h]) => (
            <Link key={l} href={h} className="rounded-lg p-space-xs hover:bg-surface-container-low"><p className="font-headline-md text-headline-md text-primary font-bold">{v}</p><p className="font-label-sm text-label-sm text-on-surface-variant">{l}</p></Link>
          ))}
          <p className="col-span-3 font-label-sm text-label-sm text-on-surface-variant">Seneste 7 dage</p>
        </div>
      </div>
      <ScriptEditor wsId={ws.id} script={script} canManage={canManage} aiReady={aiReady} />
      <div className="bg-surface-container-lowest rounded-xl p-space-md shadow-sm flex flex-col sm:flex-row sm:items-center justify-between gap-space-sm">
        <p className="font-body-sm text-body-sm text-on-surface-variant">Prøv assistenten med manuskriptet og jeres godkendte viden, før kunderne gør.</p>
        <Link href="/app/knowledge?tab=r06" className="px-4 py-2 rounded-xl bg-primary text-on-primary font-label-lg text-label-lg inline-flex items-center gap-space-xs self-start"><Icon name="play_circle" size={18} />Test assistenten</Link>
      </div>
    </section>
  );
}
