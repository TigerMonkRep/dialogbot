"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { kr, pct } from "../shared";

type Preview = { ambassador_name: string; parent_name: string | null; rules_text: string; terms: { bonus_minor: number; rate_bp: number; months: number }; confirmed: boolean };

/** A parent confirms that their child (under 18) may be a Dialogbot ambassador. Reached from the e-mail link. */
function Consent() {
  const token = useSearchParams().get("token") ?? "";
  const [p, setP] = useState<Preview | null>(null);
  const [loadErr, setLoadErr] = useState<ApiError | null>(null);
  const [ok, setOk] = useState(false);
  const [name, setName] = useState("");
  const [check, setCheck] = useState(false);
  useEffect(() => {
    if (!token) return;
    api<Preview>(`/public/ambassadors/parent-consent/${encodeURIComponent(token)}`).then((x) => { setP(x); setName(x.parent_name ?? ""); }).catch(setLoadErr);
  }, [token]);
  const { run, pending, error } = useSubmit(async () => {
    await api("/public/ambassadors/parent-consent", { method: "POST", body: JSON.stringify({ token, parent_name: name, confirm: check }) });
    setOk(true);
  });
  if (!token || loadErr) return <Alert kind="error">Linket er ugyldigt eller udløbet. Bed dit barn sende en ny mail fra sin ambassadørside.</Alert>;
  if (!p) return <p className="font-body-md text-body-md text-on-surface-variant">Henter aftalen…</p>;
  const first = p.ambassador_name.split(" ")[0];
  if (ok || p.confirmed) return <Alert kind="ok">Tak! Aftalen er godkendt. {first} kan nu få sin bonus udbetalt.</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-md">
      <p className="font-body-md text-body-md">{p.ambassador_name} vil gerne være ambassadør for Dialogbot. Det betyder, at {first} anbefaler Dialogbot til virksomheder og får en bonus, når de bliver betalende kunder:</p>
      <ul className="font-body-sm text-body-sm space-y-1">
        <li className="flex gap-1"><Icon name="check" size={18} className="text-secondary" />{kr(p.terms.bonus_minor)} når en kunde har betalt sin første faktura</li>
        <li className="flex gap-1"><Icon name="check" size={18} className="text-secondary" />{pct(p.terms.rate_bp)} af det kunden betaler i {p.terms.months} måneder</li>
        <li className="flex gap-1"><Icon name="check" size={18} className="text-secondary" />Udbetales til {first}s bankkonto. Det er B-indkomst, som vi indberetter til Skattestyrelsen – der trækkes ikke skat.</li>
        <li className="flex gap-1"><Icon name="check" size={18} className="text-secondary" />Aftalen kan stoppes når som helst – skriv til os.</li>
      </ul>
      <div className="rounded-lg bg-surface-container-low p-space-md"><p className="font-label-md text-label-md font-semibold mb-1">Reglerne {first} har sagt ja til</p><p className="font-body-sm text-body-sm text-on-surface-variant">{p.rules_text}</p></div>
      <ErrorBox error={error} />
      <Field label="Dit navn"><Input required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
      <label className="flex items-start gap-space-xs font-body-sm text-body-sm"><input type="checkbox" checked={check} onChange={(e) => setCheck(e.target.checked)} className="mt-1" />Jeg er forælder/værge for {p.ambassador_name} og godkender, at {first} er ambassadør for Dialogbot på disse vilkår.</label>
      <Button type="submit" icon="verified" disabled={pending || !check || !name.trim()} className="w-full h-12">{pending ? "Godkender…" : "Godkend aftalen"}</Button>
    </form>
  );
}

export default function ParentPage() {
  return (
    <div className="max-w-xl mx-auto rounded-xl bg-surface-container-lowest p-space-lg shadow-sm space-y-space-md">
      <div className="flex items-center gap-space-sm"><span className="w-11 h-11 rounded-full bg-primary-container text-secondary-fixed flex items-center justify-center"><Icon name="family_restroom" size={22} /></span><h1 className="font-headline-md text-headline-md text-primary font-bold">Godkend ambassadøraftale</h1></div>
      <Suspense><Consent /></Suspense>
    </div>
  );
}
