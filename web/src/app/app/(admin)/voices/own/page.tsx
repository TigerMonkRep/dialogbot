import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { OwnVoice, type Manuscript, type Project } from "./client";

/** V02: record your own voice from a Dialogbot manuscript (consent → sentence-by-sentence recording → review). */
export default async function OwnVoicePage() {
  const ws = await requireWorkspace();
  if (ws.role !== "owner" && ws.role !== "admin") {
    return <p className="bg-surface-container-lowest rounded-xl p-space-lg shadow-sm font-body-md text-body-md text-on-surface-variant">Egen stemme kan oprettes af administratorer og ejere.</p>;
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
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="text-secondary font-label-sm text-label-sm font-bold uppercase tracking-wider">Stemmer</span>
        <h1 className="font-headline-md text-headline-md text-primary font-bold">Indtal jeres egen stemme</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Læs et kort manuskript op direkte i browseren. Stemmen bruges kun i jeres eget arbejdsrum, og indtaleren kan altid trække samtykket tilbage.</p>
      </div>
      <OwnVoice wsId={ws.id} projects={items} defaults={defaults} manuscript={manuscript} />
    </section>
  );
}
