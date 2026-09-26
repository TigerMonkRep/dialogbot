"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";

export type SourceImport = {
  id: string; url: string; status: "running" | "done" | "failed"; pages: { url: string; title: string }[];
  created_items: { kind: string; title: string }[]; skipped: number; error: string | null; finished_at: string | null;
};

const KIND: Record<string, string> = { service: "Ydelse", fact: "Fakta", known_answer: "Fast svar" };

/** "Hent forslag fra hjemmesiden": the backend reads the site and creates drafts; we poll until done. */
export function WebsiteImport({ wsId, defaultUrl, initial, aiReady, compact = false }: {
  wsId: string; defaultUrl: string; initial: SourceImport | null; aiReady: boolean; compact?: boolean;
}) {
  const router = useRouter();
  const [url, setUrl] = useState(defaultUrl);
  const [imp, setImp] = useState<SourceImport | null>(initial);
  const running = imp?.status === "running";
  const start = useSubmit(async () => {
    setImp(await api<SourceImport>(`/workspaces/${wsId}/knowledge/import`, { method: "POST", body: JSON.stringify({ url }) }));
  });
  useEffect(() => {
    if (!running) return;
    const t = setInterval(async () => {
      const r = await api<{ import: SourceImport | null }>(`/workspaces/${wsId}/knowledge/imports/latest`).catch(() => null);
      if (r?.import && r.import.status !== "running") { setImp(r.import); router.refresh(); }
    }, 3000);
    return () => clearInterval(t);
  }, [running, wsId, router]);

  return (
    <div className="bg-surface-container-lowest rounded-xl p-space-md md:p-space-lg shadow-sm flex flex-col gap-space-sm">
      <div className="flex items-start gap-space-md">
        <div className="w-10 h-10 rounded-xl bg-secondary-container flex items-center justify-center text-on-secondary-container shrink-0"><Icon name="auto_awesome" size={22} /></div>
        <div>
          <h2 className="font-headline-sm text-headline-sm text-primary">Hent forslag fra hjemmesiden</h2>
          {!compact && <p className="font-body-sm text-body-sm text-on-surface-variant max-w-2xl">Vi læser jeres egne sider og foreslår ydelser, fakta og faste svar med færdig tekst. Forslagene lægges som kladder: I retter tekst og priser og godkender dem, før assistenten bruger dem. Priser gættes aldrig – står der en pris på siden, citeres den, så I kan bekræfte den ekskl. moms.</p>}
        </div>
      </div>
      {!aiReady ? <Alert kind="info">Kræver, at AI er slået til på serveren.</Alert> : (
        <form className="flex flex-col md:flex-row gap-space-sm" onSubmit={(e) => { e.preventDefault(); start.run(); }}>
          <label htmlFor="import-url" className="sr-only">Hjemmesidens adresse</label>
          <input id="import-url" className={inputCls} placeholder="https://www.jeres-firma.dk" value={url} onChange={(e) => setUrl(e.target.value)} disabled={running} />
          <Button type="submit" icon="travel_explore" disabled={start.pending || running || !url.trim()} className="shrink-0">{running ? "Læser hjemmesiden…" : "Hent forslag"}</Button>
        </form>
      )}
      {fieldError(start.error, "url") ? <p role="alert" className="text-label-md text-error">Angiv en gyldig adresse, fx https://www.jeres-firma.dk</p> : <ErrorBox error={start.error} />}
      {running && <p role="status" className="font-body-sm text-body-sm text-on-surface-variant flex items-center gap-space-xs"><Icon name="hourglass_top" size={18} />Læser sider og skriver forslag. Det tager typisk under et minut.</p>}
      {imp?.status === "failed" && <Alert kind="error">{imp.error ?? "Importen fejlede."}</Alert>}
      {imp?.status === "done" && (
        <div role="status" className="flex flex-col gap-space-xs p-space-sm rounded-lg bg-surface-container-low">
          <p className="font-label-lg text-label-lg text-primary">{imp.created_items.length === 0 ? "Ingen nye forslag" : `${imp.created_items.length} forslag oprettet som kladder`} · {imp.pages.length} sider læst{imp.skipped ? ` · ${imp.skipped} fandtes allerede` : ""}</p>
          {imp.created_items.length > 0 && (
            <ul className="flex flex-wrap gap-space-xs">{imp.created_items.map((i) => (
              <li key={`${i.kind}-${i.title}`} className="px-2 py-0.5 rounded-full bg-surface-container-high font-label-sm text-label-sm text-on-surface">{KIND[i.kind] ?? i.kind}: {i.title}</li>
            ))}</ul>
          )}
          {imp.created_items.length > 0 && <p className="font-body-sm text-body-sm text-on-surface-variant">Ret priser og tekst under <Link href="/app/knowledge?tab=k03" className="text-primary underline">Katalog</Link>, og godkend dem under <Link href="/app/knowledge?tab=k05" className="text-primary underline">Gennemgang</Link>.</p>}
        </div>
      )}
    </div>
  );
}
