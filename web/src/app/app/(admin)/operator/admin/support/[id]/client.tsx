"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, useSubmit } from "@/components/ui";
import { CATEGORY, PRIORITY, STATUS } from "../labels";

const field = "min-h-[44px] w-full px-3 rounded-xl bg-paper border-2 border-ink text-[14px]";
const primary = "min-h-[44px] px-4 rounded-xl bg-ink text-paper font-semibold disabled:opacity-50";
const outline = "min-h-[44px] px-4 rounded-xl border-2 border-ink font-semibold disabled:opacity-50";

/** Status, priority, category and assignee («Frigiv til fælleskøen» = nobody). */
export function Triage({ id, status, priority, category, assigned, operators }: { id: string; status: string; priority: string; category: string; assigned: string; operators: { id: string; name: string }[] }) {
  const router = useRouter();
  const [v, setV] = useState({ status, priority, category, assigned });
  const save = useSubmit(async () => {
    const body: Record<string, unknown> = { status: v.status, priority: v.priority, category: v.category };
    if (v.assigned) body.assigned_to = v.assigned; else body.unassign = true;
    await api(`/operator/support/tickets/${id}`, { method: "PATCH", body: JSON.stringify(body) });
    router.refresh();
  });
  const row = (label: string, key: keyof typeof v, opts: [string, string][]) => (
    <label className="flex flex-col gap-1 text-[13px] font-semibold">{label}
      <select className={field} value={v[key]} onChange={(e) => setV({ ...v, [key]: e.target.value })}>{opts.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select>
    </label>
  );
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); save.run(); }}>
      {row("Tildelt operatør", "assigned", [["", "– Frigiv til fælleskøen –"], ...operators.map((o) => [o.id, o.name] as [string, string])])}
      {row("Status", "status", Object.entries(STATUS))}
      {row("Prioritet", "priority", Object.entries(PRIORITY))}
      {row("Kategori", "category", Object.entries(CATEGORY))}
      <ErrorBox error={save.error} />
      <button type="submit" className={primary} disabled={save.pending}>Gem behandling</button>
    </form>
  );
}

/** One composer, two separate streams: «Kundesynligt svar» (shown in the customer's ticket and mailed to them) or
 *  «Intern note» (operators only, never shown to the customer). */
export function Composer({ id, workspace }: { id: string; workspace: string }) {
  const router = useRouter();
  const [visibility, setVisibility] = useState<"public" | "internal">("public");
  const [body, setBody] = useState("");
  const send = useSubmit(async (close: boolean) => {
    await api(`/operator/support/tickets/${id}/messages`, { method: "POST", body: JSON.stringify({ body, visibility, ...(close ? { status: "resolved" } : {}) }) });
    setBody("");
    router.refresh();
  });
  const pub = visibility === "public";
  return (
    <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); send.run(false); }}>
      <fieldset className="flex flex-wrap gap-2">
        <legend className="sr-only">Hvem kan se beskeden</legend>
        {([["public", "Kundesynligt svar"], ["internal", "Intern note (fortrolig)"]] as const).map(([k, l]) => (
          <label key={k} className={`inline-flex items-center gap-2 min-h-[44px] px-3 rounded-xl border-2 border-ink cursor-pointer text-[14px] font-semibold ${visibility === k ? (k === "internal" ? "bg-highlight" : "bg-accent-soft") : "bg-paper"}`}>
            <input type="radio" name="visibility" value={k} checked={visibility === k} onChange={() => setVisibility(k)} />{l}
          </label>
        ))}
      </fieldset>
      <p className="text-[13px] text-muted">{pub ? `Vises i kundens sag og sendes som e-mail til den, der oprettede sagen hos ${workspace}. Status bliver «Afventer kunde».` : "Ses kun af Dialogbot-operatører. Vises aldrig i kundens sag, aktivitetslog eller e-mails."}</p>
      <label className="flex flex-col gap-1 text-[13px] font-semibold">{pub ? `Svar til ${workspace}` : "Intern note"}
        <textarea name="body" required maxLength={5000} rows={5} value={body} onChange={(e) => setBody(e.target.value)} className={`${field} py-2`} />
      </label>
      <ErrorBox error={send.error} />
      <div className="flex flex-wrap gap-2">
        <button type="submit" className={primary} disabled={send.pending || !body.trim()}>{pub ? "Send svar til kunde" : "Gem intern note"}</button>
        {pub && <button type="button" className={outline} disabled={send.pending || !body.trim()} onClick={() => send.run(true)}>Send og markér som løst</button>}
      </div>
    </form>
  );
}
