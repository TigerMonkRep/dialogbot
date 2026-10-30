"use client";
import { useRef, useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, useSubmit } from "@/components/ui";

type Rec = { status: string; duration_seconds: number | null; deleted_at: string | null; delete_reason: string | null } | null;
const STATUS: Record<string, string> = { PENDING: "afventer – hentes fra telefonudbyderen", NOT_RECORDED: "ikke optaget", FAILED: "kunne ikke hentes", DELETED: "slettet" };
const REASON: Record<string, string> = { retention: "efter fristen", objection: "kunden ville ikke optages", erasure: "efter anmodning om sletning" };

/** Plays the recording through a signed link (≤ 10 min) the backend hands out per play; each play is logged. */
export function Player({ ccId, rec }: { ccId: string; rec: Rec }) {
  const [url, setUrl] = useState<string | null>(null);
  const [rate, setRate] = useState(1);
  const audio = useRef<HTMLAudioElement>(null);
  const play = useSubmit(async () => { const r = await api<{ url: string }>(`/operator/salg/calls/${ccId}/audio`); setUrl(r.url); });
  const exp = useSubmit(async () => { const r = await api<{ url: string }>(`/operator/salg/calls/${ccId}/audio?export=true`); window.location.assign(r.url); });
  if (!rec || rec.status !== "AVAILABLE") {
    return <p>Lyd: {rec ? STATUS[rec.status] ?? rec.status : "ikke optaget"}{rec?.delete_reason ? ` (${REASON[rec.delete_reason] ?? rec.delete_reason})` : ""}</p>;
  }
  return (
    <div className="flex flex-col gap-2">
      {url ? <>
        <audio ref={audio} src={url} controls autoPlay className="w-full" onLoadedMetadata={() => { if (audio.current) audio.current.playbackRate = rate; }} />
        <label className="text-[13px]">Hastighed <select value={rate} onChange={(e) => { const r = Number(e.target.value); setRate(r); if (audio.current) audio.current.playbackRate = r; }} className="ml-1 rounded border border-ink px-1">{[0.75, 1, 1.25, 1.5, 2].map((r) => <option key={r} value={r}>{r}×</option>)}</select></label>
      </> : <div><Button variant="secondary" icon="play_arrow" disabled={play.pending} onClick={() => play.run()}>Afspil optagelse</Button></div>}
      <div><Button variant="secondary" icon="download" disabled={exp.pending} onClick={() => exp.run()}>Eksportér (kræver rettighed)</Button></div>
      <ErrorBox error={play.error ?? exp.error} />
      <p className="text-[12px] text-muted">Hver afspilning og eksport logges.</p>
    </div>
  );
}
