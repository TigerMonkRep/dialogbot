"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Input, Select, useSubmit } from "@/components/ui";

export function DataRequestForm() {
  const router = useRouter();
  const [f, setF] = useState({ subject: "phone", value: "", kind: "access" });
  const [confirm, setConfirm] = useState(false);
  const [result, setResult] = useState<unknown>(null);
  const send = useSubmit(async () => {
    const r = await api<{ result: unknown }>("/operator/salg/data-requests", { method: "POST", body: JSON.stringify({ ...f, confirm }) });
    setResult(r.result); setConfirm(false); router.refresh();
  });
  const download = () => {
    const blob = new Blob([JSON.stringify(result, null, 2)], { type: "application/json" });
    const a = document.createElement("a"); a.href = URL.createObjectURL(blob); a.download = `indsigt-${f.value.replace(/\W+/g, "")}.json`; a.click();
  };
  return (
    <form className="rounded-2xl border-2 border-ink bg-paper p-space-md flex flex-col gap-2" onSubmit={(e) => { e.preventDefault(); send.run(); }}>
      <div className="grid sm:grid-cols-3 gap-2">
        <Field label="Type"><Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })}><option value="access">Indsigt</option><option value="erasure">Sletning</option><option value="objection">Indsigelse (spær)</option></Select></Field>
        <Field label="Gælder"><Select value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })}><option value="phone">Telefonnummer</option><option value="email">E-mail</option><option value="cvr">CVR-nummer</option></Select></Field>
        <Field label="Værdi" error={fieldError(send.error, "value")}><Input value={f.value} onChange={(e) => setF({ ...f, value: e.target.value })} /></Field>
      </div>
      {f.kind === "erasure" && <label className="flex items-start gap-2 text-[13px]"><input type="checkbox" className="mt-1 accent-primary" checked={confirm} onChange={(e) => setConfirm(e.target.checked)} /><span>Jeg har bekræftet, at anmodningen kommer fra den registrerede. Sletningen kan ikke fortrydes.</span></label>}
      <ErrorBox error={send.error} />
      <div><Button type="submit" variant={f.kind === "erasure" ? "danger" : "secondary"} disabled={!f.value.trim() || send.pending || (f.kind === "erasure" && !confirm)}>{send.pending ? "Behandler…" : "Udfør"}</Button></div>
      {result != null && <Alert kind="info"><p className="font-semibold">Resultat</p><pre className="text-[12px] whitespace-pre-wrap max-h-64 overflow-auto">{JSON.stringify(result, null, 2)}</pre>{f.kind === "access" && <Button variant="secondary" onClick={download}>Hent som JSON</Button>}</Alert>}
    </form>
  );
}
