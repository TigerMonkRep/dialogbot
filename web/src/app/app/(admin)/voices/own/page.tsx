import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { OwnVoice, type Manuscript, type Project } from "./client";

/** V02: record your own voice from a Dialogbot manuscript (consent → sentence-by-sentence recording → review). */
export default async function OwnVoicePage() {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-paper rounded-2xl p-4 border-2 border-ink text-body-md text-ink-soft">Egen stemme kan oprettes af administratorer og ejere.</p>;
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
        <span className="eyebrow">Stemmer</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Indtal jeres egen stemme</h1>
        <p className="text-body-sm text-ink-soft max-w-2xl">Læs et kort manuskript op direkte i browseren. Stemmen bruges kun i jeres eget arbejdsrum, og indtaleren kan altid trække samtykket tilbage.</p>
      </div>
      <OwnVoice wsId={ws.id} projects={items} defaults={defaults} manuscript={manuscript} />
    </section>
  );
}
