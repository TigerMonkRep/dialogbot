"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";

async function select(id: string) {
  await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: id }) });
}
const INTENT: Record<string, string> = { reception: "Reception", campaigns: "Kampagner", both: "Reception + kampagner" };
const ROLE: Record<string, string> = { owner: "Ejer", admin: "Administrator", staff: "Medarbejder", reader: "Læser" };
const initials = (name: string) => name.split(/\s+/).map((s) => s[0]).join("").slice(0, 2).toUpperCase();

type Ws = { id: string; name: string; role: string; product_intent: string; knowledge_revision: number };

/** A06 workspace cards (Stitch mosaic): the active workspace is highlighted, others can be switched to. */
export function WorkspaceCards({ workspaces, currentId }: { workspaces: Ws[]; currentId: string | null }) {
  const router = useRouter();
  if (workspaces.length === 0) return <p className="font-body-sm text-body-sm text-on-surface-variant">Du er ikke medlem af noget arbejdsrum endnu. Opret det første, eller acceptér en invitation fra en kollega.</p>;
  const active = workspaces.find((w) => w.id === currentId) ?? workspaces[0];
  const ordered = [active, ...workspaces.filter((w) => w.id !== active.id)];
  return (
    <ul className="grid grid-cols-1 md:grid-cols-3 gap-space-md">
      {ordered.map((w) => {
        const isActive = w.id === active.id;
        const ready = w.knowledge_revision > 0;
        return (
          <li key={w.id} className={`relative p-space-lg rounded-xl flex flex-col justify-between transition-all ${isActive ? "bg-surface-container-low shadow-sm" : "bg-surface hover:bg-surface-container"}`}>
            {isActive && (
              <span className="absolute -top-2.5 right-4 px-2.5 py-0.5 rounded-full bg-primary text-secondary-fixed font-label-sm text-label-sm font-bold uppercase tracking-wider flex items-center gap-1 shadow-sm">
                <span className="w-1.5 h-1.5 rounded-full bg-secondary-fixed animate-pulse" />Aktivt valg
              </span>
            )}
            <div>
              <div className="flex items-center gap-3 mb-2">
                <div className={`w-10 h-10 rounded-lg flex items-center justify-center font-headline-sm text-headline-sm font-bold flex-shrink-0 ${isActive ? "bg-primary-container text-secondary-fixed" : "bg-surface-container-highest text-on-surface-variant"}`}>{initials(w.name)}</div>
                <div className="min-w-0">
                  <p className={`font-headline-sm text-headline-sm truncate ${isActive ? "text-primary font-bold" : "text-on-surface font-semibold"}`}>{w.name}</p>
                  <p className="font-label-sm text-label-sm text-on-surface-variant">{ROLE[w.role] ?? w.role} • {INTENT[w.product_intent] ?? w.product_intent}</p>
                </div>
              </div>
              <p className="font-body-sm text-body-sm text-on-surface-variant mt-2">{ready ? `${w.knowledge_revision} godkendte vidensrevisioner.` : "Ingen godkendt viden endnu."}</p>
            </div>
            <div className="mt-4 pt-3 flex items-center justify-between">
              <span className={`font-label-sm text-label-sm flex items-center gap-1 ${ready ? "text-primary font-semibold" : "text-on-surface-variant"}`}>
                <Icon name={ready ? "check_circle" : "pause_circle"} size={16} className={ready ? "text-secondary" : ""} />{ready ? "Viden klar" : "Afventer onboarding"}
              </span>
              {!isActive && <button onClick={async () => { await select(w.id); router.refresh(); }} className="font-label-sm text-label-sm text-primary hover:underline font-semibold">Skift hertil</button>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function WorkspaceForm({ defaultIntent, verified }: { defaultIntent: string; verified: boolean }) {
  const router = useRouter();
  const [name, setName] = useState("");
  const [intent, setIntent] = useState(defaultIntent);
  const { run, pending, error } = useSubmit(async () => {
    const ws = await api<{ id: string }>("/workspaces", { method: "POST", body: JSON.stringify({ name, product_intent: intent }) });
    await select(ws.id); router.push("/onboarding/business"); router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      {!verified && <Alert kind="warn">Bekræft din e-mail først. <Link className="underline" href="/verify-email">Gå til bekræftelse</Link></Alert>}
      <ErrorBox error={error} />
      <Field label="Virksomhedens officielle navn" hint="Dette navn bruges af assistenten over for kunderne."><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fx Fjord Gulvservice ApS" /></Field>
      <Field label="Produktintention"><Select value={intent} onChange={(e) => setIntent(e.target.value)}><option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Reception + kampagner</option></Select></Field>
      <Button type="submit" icon="add_circle" disabled={pending || !verified} className="w-full">{pending ? "Opretter…" : "Opret og fortsæt"}</Button>
    </form>
  );
}
