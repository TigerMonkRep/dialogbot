"use client";
import { useState } from "react";
import { api } from "@/lib/client";
import { Button, ErrorBox, Icon, inputCls, useSubmit } from "@/components/ui";

type Preview = {
  reply: string; refused: boolean; truncated: boolean; stop_reason: string; model: string; prompt_version: string; knowledge_revision: number;
  usage: { input_tokens: number; output_tokens: number; cache_creation_input_tokens: number; cache_read_input_tokens: number; est_cost_usd_micros: number | null };
};
type Turn = { q: string; a: Preview };

export const usd = (micros: number | null) => (micros == null ? "ukendt pris" : `≈ $${(micros / 1_000_000).toFixed(4)}`);

/** R06: internal one-question test against the assistant. Answers come only from approved knowledge; nothing reaches a customer. */
export function AssistantPreview({ wsId, simulated }: { wsId: string; simulated: boolean }) {
  const [message, setMessage] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const ask = useSubmit(async () => {
    const q = message.trim();
    const a = await api<Preview>(`/workspaces/${wsId}/assistant/preview`, { method: "POST", body: JSON.stringify({ message: q }) });
    setTurns((t) => [{ q, a }, ...t]);
    setMessage("");
  });
  return (
    <div className="flex flex-col gap-space-md">
      <div className="p-space-md rounded-xl bg-surface-container-low flex items-start gap-space-sm">
        <Icon name="science" size={22} className="text-secondary flex-shrink-0" />
        <p className="font-body-sm text-body-sm text-on-surface-variant">
          Intern test: svarene sendes ikke til kunder, og ingen kundekanal er koblet på endnu. Assistenten bruger kun den godkendte viden – kladder er aldrig med.
          {simulated && <strong className="block text-on-surface">Testmiljø: svarene kommer fra en simuleret model, ikke en rigtig AI.</strong>}
        </p>
      </div>
      <form className="flex flex-col gap-space-sm" onSubmit={(e) => { e.preventDefault(); if (message.trim()) ask.run(); }}>
        <label htmlFor="assistant-q" className="font-label-md text-label-md text-on-surface font-semibold">Spørgsmål fra en kunde</label>
        <textarea id="assistant-q" rows={3} maxLength={2000} className={`${inputCls} resize-y`} placeholder="Fx: Hvad koster afslibning af 50 m²?" value={message} onChange={(e) => setMessage(e.target.value)} />
        <ErrorBox error={ask.error} />
        <div><Button type="submit" icon="send" disabled={ask.pending || !message.trim()}>{ask.pending ? "Assistenten svarer…" : "Spørg assistenten"}</Button></div>
      </form>
      <ol className="flex flex-col gap-space-md" aria-label="Testsvar">
        {turns.map(({ q, a }, i) => (
          <li key={turns.length - i} className="rounded-xl bg-surface-container-lowest shadow-sm p-space-md flex flex-col gap-space-sm">
            <p className="font-label-md text-label-md text-on-surface-variant">Spørgsmål</p>
            <p className="font-body-md text-body-md text-on-surface whitespace-pre-wrap">{q}</p>
            <p className="font-label-md text-label-md text-on-surface-variant flex items-center gap-space-xs">Svar
              {a.refused && <span className="px-2 py-0.5 rounded-full bg-error-container text-on-error-container font-label-sm text-label-sm">Afvist af modellen</span>}
              {a.truncated && <span className="px-2 py-0.5 rounded-full bg-tertiary-fixed text-on-tertiary-fixed font-label-sm text-label-sm">Afkortet</span>}
            </p>
            <p className="font-body-md text-body-md text-primary whitespace-pre-wrap">{a.reply}</p>
            <p className="font-mono text-label-sm text-on-surface-variant">
              {a.model} · {a.prompt_version} · viden rev. {a.knowledge_revision} · {a.usage.input_tokens + a.usage.cache_creation_input_tokens + a.usage.cache_read_input_tokens} ind / {a.usage.output_tokens} ud tokens · {usd(a.usage.est_cost_usd_micros)}
            </p>
          </li>
        ))}
      </ol>
    </div>
  );
}
