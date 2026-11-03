import Link from "next/link";
import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Icon } from "@/components/ui";
import { getT } from "@/i18n/server";
import type { T } from "@/i18n/translate";
import { WebchatForm, type WebchatSettings } from "./client";

type Capability = { key: string; status: "available" | "simulated" | "not_implemented" };

/** W01: web widget settings, embed code and readiness. Only owners/admins change them; staff can read. */
export default async function WebchatPage() {
  const ws = await requireWorkspace();
  const t = await getT("settings");
  if (ws.role === "reader") {
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("webchat.readersBlocked")}</p>;
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
            <span className="eyebrow">{t("webchat.eyebrow")}</span>
            <h2 className="font-display text-headline-sm text-ink font-bold">{t("webchat.title")}</h2>
            <p className="text-body-sm text-ink-soft max-w-2xl">{t("webchat.introBefore")} <Link href="/app/inbox" className="text-ink underline">{t("webchat.inbox")}</Link>{t("webchat.introAfter")}</p>
          </div>
          <StatusPill s={s} t={t} />
        </div>
        {status === "simulated" && <p className="p-2 rounded-lg bg-accent-soft text-accent-deep text-body-sm">{t("webchat.simulated")}</p>}
        {!s.available && s.unavailable_reasons.length > 0 && (
          <ul className="flex flex-col gap-1 p-3 rounded-lg bg-panel">
            {s.unavailable_reasons.map((r) => <li key={r} className="flex items-start gap-1 text-body-sm text-ink"><Icon name="radio_button_unchecked" size={18} className="text-ink mt-0.5" />{reason(t, r)}</li>)}
          </ul>
        )}
      </div>
      <WebchatForm wsId={ws.id} initial={s} canManage={ws.role === "owner" || ws.role === "admin"} />
    </section>
  );
}

function reason(t: T, r: string): React.ReactNode {
  if (r === "no_approved_knowledge") return <>{t("webchat.reason.noKnowledgeBefore")} <Link href="/app/knowledge" className="text-ink underline">{t("webchat.reason.noKnowledgeLink")}</Link>{t("webchat.reason.noKnowledgeAfter")}</>;
  return ["disabled", "no_allowed_origins", "ai_not_configured"].includes(r) ? t(`webchat.reason.${r}`) : r;
}

function StatusPill({ s, t }: { s: WebchatSettings; t: T }) {
  const [label, cls] = s.available ? [t("webchat.pill.active"), "bg-success-soft text-success"]
    : s.enabled ? [t("webchat.pill.missing"), "bg-accent-soft text-accent-deep"] : [t("webchat.pill.off"), "bg-line text-ink-soft"];
  return <span className={`px-3 py-1 rounded-full text-label-sm font-semibold ${cls}`}>{label}</span>;
}
