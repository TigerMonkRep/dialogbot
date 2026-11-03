import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { ScriptEditor, type Script } from "./client";
import { getT } from "@/i18n/server";

type Overview = {
  channels: { phone: { configured: boolean; numbers: { e164: string; active: boolean; voice: boolean }[] }; webchat: { enabled: boolean; origins: number } };
  script_configured: boolean;
  last_7_days: { conversations: number; calls: number; leads: number };
};

/** Reception: channel status, the last 7 days and the manuscript the assistant follows in chat and on the phone. */
export default async function ReceptionPage() {
  const ws = await requireWorkspace();
  const t = await getT("app");
  if (ws.role === "reader") return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("reception.staffOnly")}</p>;
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
    <div className="bg-paper rounded-2xl p-3 border-2 border-ink flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-1 text-label-lg text-ink font-bold"><Icon name={icon} size={20} />{title}</span>
        <span className={`px-2 py-0.5 rounded-full text-label-sm font-semibold ${ok ?"bg-success-soft text-success":"bg-line text-ink-soft"}`}>{ok ? t("reception.active") : t("reception.inactive")}</span>
      </div>
      <p className="text-body-sm text-ink-soft">{text}</p>
      <Link href={href} className="text-label-md text-ink underline self-start">{cta}</Link>
    </div>
  );
  return (
    <section className="flex flex-col gap-4">
      <div>
        <span className="eyebrow">{t("reception.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("reception.title")}</h1>
        <p className="text-body-sm text-ink-soft max-w-2xl">{t("reception.intro")}</p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <Channel icon="call" title={t("calls.phone")} ok={phone.configured && activeNumbers.length > 0}
          text={!phone.configured ? t("reception.phone.notConfigured") : activeNumbers.length ? `${activeNumbers.map((n) => n.e164).join(", ")}${activeNumbers.some((n) => !n.voice) ? ` – ${t("reception.phone.noVoice")}` : ""}` : t("reception.phone.noNumber")}
          href="/app/settings/telephony" cta={t("reception.phone.settings")} />
        <Channel icon="chat" title="Webchat" ok={ov.channels.webchat.enabled} text={ov.channels.webchat.enabled ? t("reception.webchat.activeOn", { n: ov.channels.webchat.origins }) : t("reception.webchat.off")} href="/app/settings/webchat" cta={t("reception.webchat.settings")} />
        <div className="bg-paper rounded-2xl p-3 border-2 border-ink grid grid-cols-3 gap-2 text-center">
          {([[t("reception.stats.conversations"), ov.last_7_days.conversations, "/app/inbox"], [t("nav.calls"), ov.last_7_days.calls, "/app/settings/telephony"], [t("leads.back"), ov.last_7_days.leads, "/app/leads"]] as const).map(([l, v, h]) => (
            <Link key={l} href={h} className="rounded-lg p-1 hover:bg-panel"><p className="font-display text-headline-md text-ink font-bold">{v}</p><p className="text-label-sm text-ink-soft">{l}</p></Link>
          ))}
          <p className="col-span-3 text-label-sm text-ink-soft">{t("calls.lastDays", { n: 7 })}</p>
        </div>
      </div>
      <ScriptEditor wsId={ws.id} script={script} canManage={canManage} aiReady={aiReady} />
      <div className="bg-paper rounded-2xl p-3 border-2 border-ink flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <p className="text-body-sm text-ink-soft">{t("reception.try")}</p>
        <Link href="/app/knowledge?tab=r06" className="px-4 py-2 rounded-xl bg-ink text-paper text-label-lg inline-flex items-center gap-1 self-start"><Icon name="play_circle" size={18} />{t("reception.test")}</Link>
      </div>
    </section>
  );
}
