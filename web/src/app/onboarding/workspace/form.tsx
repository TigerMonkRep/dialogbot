"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Select, useSubmit } from "@/components/ui";

async function select(id: string) {
  await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: id }) });
}
const INTENT: Record<string, string> = { reception: "Reception", campaigns: "Kampagner", both: "Reception + Kampagner" };

export function WorkspaceList({ workspaces }: { workspaces: { id: string; name: string; role: string; product_intent: string; knowledge_revision: number }[] }) {
  const router = useRouter();
  if (workspaces.length === 0) return <p className="text-body-sm text-on-surface-variant">Du er ikke medlem af noget arbejdsrum endnu. Opret det første til højre, eller acceptér en invitation fra en kollega.</p>;
  return (
    <ul className="space-y-space-sm">
      {workspaces.map((w, i) => (
        <li key={w.id} className={`flex items-center gap-space-md p-space-md rounded-xl ${i === 0 ? "bg-surface-container-low ring-1 ring-primary/30" : "bg-surface-container-low/60"}`}>
          <span className="w-10 h-10 rounded-lg bg-primary text-secondary-fixed font-display font-bold flex items-center justify-center">{w.name.split(" ").map((s) => s[0]).join("").slice(0, 2).toUpperCase()}</span>
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-space-xs flex-wrap"><span className="text-label-lg font-bold text-on-surface truncate">{w.name}</span>{i === 0 && <span className="text-label-sm text-secondary font-semibold uppercase">Aktivt valg</span>}</div>
            <p className="text-body-sm text-on-surface-variant">{INTENT[w.product_intent]} · rolle: {w.role} · {w.knowledge_revision > 0 ? `${w.knowledge_revision} vidensrevisioner` : "ingen godkendt viden endnu"}</p>
            <p className="text-label-sm text-on-surface-variant flex items-center gap-1 mt-0.5"><Icon name={w.knowledge_revision > 0 ? "check_circle" : "pause_circle"} size={14} className={w.knowledge_revision > 0 ? "text-secondary" : ""} />{w.knowledge_revision > 0 ? "Viden klar" : "Afventer onboarding"}</p>
          </div>
          <Button variant={i === 0 ? "primary" : "tonal"} onClick={async () => { await select(w.id); router.push("/onboarding/business"); router.refresh(); }}>{i === 0 ? "Fortsæt" : "Skift hertil"}</Button>
        </li>
      ))}
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
      <Field label="Virksomhedens officielle navn" hint="Dette navn udtales af assistenten ved indgående samtaler."><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} placeholder="Fx Fjord Gulvservice ApS" /></Field>
      <Field label="Produktintention"><Select value={intent} onChange={(e) => setIntent(e.target.value)}><option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Reception + Kampagner</option></Select></Field>
      <Button type="submit" icon="add_circle" disabled={pending || !verified} className="w-full">{pending ? "Opretter…" : "Opret og fortsæt"}</Button>
    </form>
  );
}
