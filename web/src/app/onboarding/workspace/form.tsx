"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, useSubmit } from "@/components/ui";

async function select(id: string) {
  await fetch("/api/auth/workspace", { method: "POST", headers: { "content-type": "application/json", "x-requested-with": "dialogbot" }, body: JSON.stringify({ workspace_id: id }) });
}

export function WorkspaceList({ workspaces }: { workspaces: { id: string; name: string; role: string; product_intent: string }[] }) {
  const router = useRouter();
  return (
    <ul className="divide-y divide-line">
      {workspaces.map((w) => (
        <li key={w.id} className="flex items-center justify-between gap-3 py-3 text-sm">
          <span><strong>{w.name}</strong> <span className="text-muted">· {w.role} · {w.product_intent}</span></span>
          <Button variant="secondary" onClick={async () => { await select(w.id); router.push("/onboarding/business"); router.refresh(); }}>Fortsæt</Button>
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
    await select(ws.id);
    router.push("/onboarding/business"); router.refresh();
  });
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-4">
      {!verified && <Alert kind="info">Bekræft din e-mail først. <Link className="underline" href="/verify-email">Gå til bekræftelse</Link></Alert>}
      <ErrorBox error={error} />
      <Field label="Virksomhedens navn"><Input required minLength={2} value={name} onChange={(e) => setName(e.target.value)} /></Field>
      <Field label="Produktintention (fra tilmelding)">
        <select className="w-full rounded-xl border border-line bg-white px-3.5 py-2.5 text-sm" value={intent} onChange={(e) => setIntent(e.target.value)}>
          <option value="reception">Reception</option><option value="campaigns">Kampagner</option><option value="both">Begge dele</option>
        </select>
      </Field>
      <Button type="submit" disabled={pending || !verified}>Opret og fortsæt</Button>
    </form>
  );
}
