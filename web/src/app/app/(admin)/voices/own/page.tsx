import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { getT } from "@/i18n/server";
import { OwnVoice, type Manuscript, type Project } from "./client";

/** V02: record your own voice from a Dialogbot manuscript (consent → sentence-by-sentence recording → review). */
export default async function OwnVoicePage() {
  const ws = await requireWorkspace();
  const t = await getT("settings");
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">{t("ownVoice.onlyAdmins")}</p>;
  }
  const [{ items }, defaults] = await Promise.all([
    backend<{ items: Project[] }>(`/workspaces/${ws.id}/own-voices`),
    backend<Manuscript>(`/workspaces/${ws.id}/own-voices/manuscripts/kort`),
  ]);
  const current = items.find((p) => p.status === "recording");
  let manuscript: Manuscript | null = null;
  if (current) {
    const q = new URLSearchParams(Object.entries(current.values).filter(([, v]) => v) as [string, string][]);
    manuscript = await backend<Manuscript>(`/workspaces/${ws.id}/own-voices/manuscripts/${current.manuscript}?${q}`);
  }
  return (
    <section className="flex flex-col gap-4">
      <div>
        <span className="eyebrow">{t("ownVoice.eyebrow")}</span>
        <h1 className="font-display font-extrabold text-[26px] sm:text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{t("ownVoice.title")}</h1>
        <p className="text-body-sm text-ink-soft max-w-2xl">{t("ownVoice.intro")}</p>
      </div>
      <OwnVoice wsId={ws.id} projects={items} defaults={defaults} manuscript={manuscript} />
    </section>
  );
}
