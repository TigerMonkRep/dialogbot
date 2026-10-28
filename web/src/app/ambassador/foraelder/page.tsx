"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { StepNumber } from "@/components/lego";
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
  if (!p) return <p className="m-0 text-[17px] text-ink-soft">Henter aftalen…</p>;
  const first = p.ambassador_name.split(" ")[0];
  if (ok || p.confirmed) return <Alert kind="ok">Tak! Aftalen er godkendt. {first} kan nu få sin bonus udbetalt.</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex flex-col gap-4">
      <p className="m-0 text-[17px] leading-normal text-ink">{p.ambassador_name} vil gerne være ambassadør for Dialogbot. Det betyder, at {first} anbefaler Dialogbot til virksomheder og får en bonus, når de bliver betalende kunder:</p>
      <ul className="m-0 p-0 list-none text-[15px] leading-normal text-ink flex flex-col gap-2">
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{kr(p.terms.bonus_minor)} når en kunde har betalt sin første faktura</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{pct(p.terms.rate_bp)} af det kunden betaler i {p.terms.months} måneder</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />Udbetales til {first}s bankkonto. Det er B-indkomst, som vi indberetter til Skattestyrelsen – der trækkes ikke skat.</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />Aftalen kan stoppes når som helst – skriv til os.</li>
      </ul>
      <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4"><p className="m-0 eyebrow mb-1.5">Reglerne {first} har sagt ja til</p><p className="m-0 text-[15px] leading-normal text-ink-soft">{p.rules_text}</p></div>
      <ErrorBox error={error} />
      <Field label="Dit navn"><Input required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
      <label className="flex items-start gap-2.5 min-h-[44px] text-[15px] leading-normal text-ink"><input type="checkbox" checked={check} onChange={(e) => setCheck(e.target.checked)} className="mt-0.5 w-5 h-5 accent-accent flex-shrink-0" />Jeg er forælder/værge for {p.ambassador_name} og godkender, at {first} er ambassadør for Dialogbot på disse vilkår.</label>
      <Button type="submit" icon="verified" disabled={pending || !check || !name.trim()} className="w-full min-h-[52px] text-[17px] rounded-[14px]">{pending ? "Godkender…" : "Godkend aftalen"}</Button>
    </form>
  );
}

export default function ParentPage() {
  return (
    <div className="max-w-xl mx-auto rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5 shadow-block">
      <div className="flex items-center gap-3.5"><StepNumber value="1" /><div className="flex flex-col gap-1"><span className="eyebrow">Forælder eller værge</span><h1 className="m-0 font-display font-extrabold text-[clamp(24px,3vw,30px)] leading-[1.1] tracking-[-0.5px] text-ink">Godkend ambassadøraftale</h1></div></div>
      <Suspense><Consent /></Suspense>
    </div>
  );
}
