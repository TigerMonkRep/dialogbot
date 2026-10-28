"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { ErrorBox, Icon, useSubmit } from "@/components/ui";

export type TelephonyCode = "not_started" | "awaiting_info" | "provisioning" | "ready_for_test" | "test_failed" | "active" | "paused";

/** The big on/off switch. It only flips between "active" and "paused" (the two states the backend lets a
 *  customer toggle); every other state shows an honest label and sends the user to the telephony setup. */
export function PowerToggle({ wsId, code, canManage }: { wsId: string; code: TelephonyCode; canManage: boolean }) {
  const router = useRouter();
  const on = code === "active";
  const toggleable = canManage && (code === "active" || code === "paused");
  const { run, pending, error } = useSubmit(async () => {
    await api(`/workspaces/${wsId}/telephony/${on ? "pause" : "activate"}`, { method: "POST" });
    router.refresh();
  });
  return (
    <div className="flex flex-col items-end gap-2">
      <button type="button" role="switch" aria-checked={on} aria-label="Tænd eller sluk Dialogbot" disabled={!toggleable || pending} onClick={() => run()}
        title={toggleable ? undefined : code === "active" || code === "paused" ? "Kun ejere og administratorer kan tænde og slukke" : "Telefonen skal sættes op, før Dialogbot kan tændes"}
        className={`inline-flex items-center w-[84px] h-11 p-1 rounded-full transition-colors disabled:cursor-not-allowed ${on ? "bg-accent justify-end" : "bg-muted justify-start"} ${toggleable ? "" : "opacity-60"}`}>
        <span className="w-9 h-9 rounded-full bg-paper" />
      </button>
      <ErrorBox error={error} />
    </div>
  );
}

type Proposal = { area: string; title: string; body: string; href: string; cta: string };

const CHIPS: { label: string; p: Proposal }[] = [
  { label: "Ret åbningstider", p: { area: "Åbningstider", title: "Ret, hvornår Dialogbot siger I har åbent", body: "Åbningstiderne ligger under «Det ved den». Du retter dem der, og de gælder, når en ejer eller administrator har godkendt kladden.", href: "/app/knowledge?tab=k03", cta: "Åbn åbningstider" } },
  { label: "Tilføj en pris", p: { area: "Det I sælger", title: "Tilføj en ydelse med pris", body: "Du skriver navn, pris og en kort forklaring. Dialogbot nævner først prisen, når kladden er godkendt.", href: "/app/knowledge?tab=k03", cta: "Tilføj ydelse" } },
  { label: "Send SMS til kunder", p: { area: "Kampagne", title: "Lav en SMS-kampagne", body: "Du skriver teksten og vælger modtagere. Intet sendes, før du har godkendt listen og tidspunktet.", href: "/app/campaigns", cta: "Gå til kampagner" } },
  { label: "Koble et system på", p: { area: "Integration", title: "Forbind kalender eller fagsystem", body: "Under Integrationer ser du, hvad der kan kobles på nu, og hvad der er på vej. Intet markeres som klar, før det virker.", href: "/app/settings/integrationer", cta: "Åbn integrationer" } },
  { label: "Vis mig ugens tal", p: { area: "Rapporter", title: "Ugens opkald, henvendelser og bookinger", body: "Rapportsiden viser de rigtige tal fra jeres arbejdsrum – ingen estimater.", href: "/app/reports", cta: "Se rapporter" } },
];

/** Free text is matched to the nearest known change. There is no AI behind this box yet, so it never pretends to. */
function match(text: string): Proposal | null {
  const t = text.toLowerCase();
  if (/(åbn|lukket|luk |ferie|helligdag|tid)/.test(t)) return CHIPS[0].p;
  if (/(pris|koster|kr|ydelse|sælg)/.test(t)) return CHIPS[1].p;
  if (/(sms|kampagne|besked til|nyhedsbrev)/.test(t)) return CHIPS[2].p;
  if (/(system|kalender|integration|dinero|e-conomic|hubspot|outlook|google)/.test(t)) return CHIPS[3].p;
  if (/(tal|rapport|statistik|uge|måned)/.test(t)) return CHIPS[4].p;
  return null;
}

/** "Ændr noget": the one place to change things from. Each change is shown as a preview and approved before anything applies;
 *  today "Godkend" takes you to the page that makes the change. */
export function ChangePanel({ firstName, summary }: { firstName: string; summary: string }) {
  const router = useRouter();
  const [draft, setDraft] = useState("");
  const [log, setLog] = useState<{ from: "bot" | "user"; text: string }[]>([{ from: "bot", text: `Hej ${firstName}. ${summary} Vil du ændre noget?` }]);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const say = (from: "bot" | "user", text: string) => setLog((l) => [...l.slice(-5), { from, text }]);
  const propose = (label: string, p: Proposal) => { say("user", label); say("bot", "Sådan gør vi det – godkend, så åbner jeg det rigtige sted:"); setProposal(p); };
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const v = draft.trim(); if (!v) return;
    setDraft("");
    const p = match(v);
    if (p) propose(v, p);
    else { say("user", v); say("bot", "Det kan jeg ikke ændre herfra endnu. Vælg en af mulighederne nedenfor, eller find det under «Mere» øverst."); setProposal(null); }
  };
  return (
    <aside aria-label="Din assistent" className="bg-paper border-2 border-ink rounded-2xl shadow-block flex flex-col overflow-hidden">
      <div className="flex items-center gap-3 px-4 py-3.5 border-b-2 border-ink">
        <span className="inline-flex w-9 h-9 rounded-[10px] bg-accent items-center justify-center font-display font-extrabold text-white">D</span>
        <div className="flex flex-col">
          <span className="font-display font-bold text-[16px] text-ink">Ændr noget</span>
          <span className="text-[12px] text-muted">Sig det – du ser ændringen, før den gælder</span>
        </div>
      </div>
      <div className="flex flex-col gap-3 p-4 min-h-[220px]">
        {log.map((m, i) => (
          <div key={i} className={`flex ${m.from === "bot" ? "justify-start" : "justify-end"}`}>
            <p className={`m-0 px-3.5 py-2.5 text-[14px] leading-relaxed max-w-[320px] whitespace-pre-line border-2 border-ink ${m.from === "bot" ? "bg-paper text-ink rounded-[14px] rounded-bl-[4px]" : "bg-ink text-paper rounded-[14px] rounded-br-[4px]"}`}>{m.text}</p>
          </div>
        ))}
        {proposal && (
          <div className="flex flex-col gap-2.5 p-3.5 rounded-[14px] border-2 border-dashed border-ink bg-panel">
            <span className="eyebrow">Forhåndsvisning · {proposal.area}</span>
            <span className="font-display font-bold text-[16px] text-ink">{proposal.title}</span>
            <span className="text-[14px] leading-relaxed text-ink-soft">{proposal.body}</span>
            <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => router.push(proposal.href)} className="min-h-[44px] px-4 rounded-xl bg-accent text-white text-[14px] font-semibold hover:bg-accent-deep">{proposal.cta}</button>
              <button type="button" onClick={() => { setProposal(null); say("bot", "Okay, intet ændret."); }} className="min-h-[44px] px-3.5 rounded-xl bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel">Nej, lad være</button>
            </div>
          </div>
        )}
      </div>
      <div className="flex flex-col gap-2.5 px-4 pt-3.5 pb-4 border-t-2 border-ink bg-panel">
        <span className="eyebrow">Det, folk oftest beder om</span>
        <div className="flex flex-wrap gap-2">
          {CHIPS.map((c) => <button key={c.label} type="button" onClick={() => propose(c.label, c.p)} className="min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</button>)}
        </div>
        <form onSubmit={submit} className="flex gap-2">
          <label htmlFor="change-ask" className="sr-only">Skriv, hvad du vil ændre</label>
          <input id="change-ask" type="text" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Eller skriv det selv …" autoComplete="off" maxLength={300}
            className="flex-1 min-w-0 min-h-[46px] px-3.5 rounded-xl border-2 border-ink bg-paper text-[15px] text-ink placeholder:text-muted" />
          <button type="submit" aria-label="Send" className="w-[46px] h-[46px] rounded-xl bg-accent text-white inline-flex items-center justify-center hover:bg-accent-deep"><Icon name="arrow_forward" size={20} /></button>
        </form>
        <Link href="/app/settings/team" className="self-end text-[12px] text-muted hover:text-ink">Avanceret: alle indstillinger</Link>
      </div>
    </aside>
  );
}
