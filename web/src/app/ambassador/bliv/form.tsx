"use client";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { api, fieldError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, Textarea, useSubmit } from "@/components/ui";
import type { Program } from "../shared";

const age = (iso: string) => {
  if (!iso) return null;
  const b = new Date(iso), t = new Date();
  return t.getFullYear() - b.getFullYear() - (t.getMonth() < b.getMonth() || (t.getMonth() === b.getMonth() && t.getDate() < b.getDate()) ? 1 : 0);
};

export function ApplyForm({ program, defaultName }: { program: Program; defaultName: string }) {
  const router = useRouter();
  const [f, setF] = useState({
    kind: "private", full_name: defaultName, phone: "", birth_date: "", cpr: "", parent_name: "", parent_email: "",
    company_name: "", cvr: "", vat_registered: false, bank_reg: "", bank_account: "", headline: "", motivation: "",
  });
  const [quiz, setQuiz] = useState<Record<string, string>>({});
  const [wrong, setWrong] = useState<string[]>([]);
  const years = useMemo(() => age(f.birth_date), [f.birth_date]);
  const minor = f.kind === "private" && years !== null && years < 18;
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => setF({ ...f, [k]: e.target.value });
  const { run, pending, error } = useSubmit(async () => {
    setWrong([]);
    try {
      await api("/ambassador/apply", { method: "POST", body: JSON.stringify({
        ...f, birth_date: f.kind === "private" ? f.birth_date || null : null, cpr: f.cpr || null,
        parent_name: minor ? f.parent_name : null, parent_email: minor ? f.parent_email : null,
        cvr: f.kind === "company" ? f.cvr : null, company_name: f.kind === "company" ? f.company_name : null,
        bank_reg: f.bank_reg || null, bank_account: f.bank_account || null, rules_version: program.rules_version, quiz,
      }) });
    } catch (e) {
      const x = e as { code?: string; extra?: { wrong?: string[] }; wrong?: string[] };
      if (x.code === "rules_quiz_failed") setWrong(x.wrong ?? x.extra?.wrong ?? []);
      throw e;
    }
    router.push("/ambassador"); router.refresh();
  });
  const answered = program.quiz.every((q) => quiz[q.id]);
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="space-y-space-lg">
      <ErrorBox error={error} />
      <fieldset className="space-y-space-sm">
        <legend className="font-label-md text-label-md font-semibold mb-1">Jeg er</legend>
        <div className="grid grid-cols-2 gap-space-sm">
          {[["private", "Privatperson", "Uden CVR – bonus er B-indkomst"], ["company", "Virksomhed", "Med CVR – afregning via bilag"]].map(([v, l, h]) => (
            <label key={v} className={`rounded-lg p-space-sm cursor-pointer border ${f.kind === v ? "border-primary bg-surface-container-low" : "border-outline-variant"}`}>
              <input type="radio" name="kind" value={v} checked={f.kind === v} onChange={() => setF({ ...f, kind: v })} className="sr-only" />
              <span className="font-label-lg text-label-lg text-primary font-semibold block">{l}</span><span className="font-label-sm text-label-sm text-on-surface-variant">{h}</span>
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid sm:grid-cols-2 gap-space-md">
        <Field label="Fulde navn" error={fieldError(error, "full_name")}><Input required value={f.full_name} onChange={set("full_name")} autoComplete="name" /></Field>
        <Field label="Mobilnummer" hint="Så vi kan ringe, hvis der er spørgsmål."><Input value={f.phone} onChange={set("phone")} autoComplete="tel" inputMode="tel" /></Field>
      </div>
      {f.kind === "private" ? (
        <div className="grid sm:grid-cols-2 gap-space-md">
          <Field label="Fødselsdato" error={fieldError(error, "birth_date")}><Input type="date" required value={f.birth_date} onChange={set("birth_date")} /></Field>
          <Field label="CPR-nummer (kan vente)" hint="Skal bruges til at indberette B-indkomst. Gemmes krypteret." error={fieldError(error, "cpr")}><Input value={f.cpr} onChange={set("cpr")} inputMode="numeric" placeholder="DDMMÅÅ-XXXX" autoComplete="off" /></Field>
        </div>
      ) : (
        <div className="grid sm:grid-cols-2 gap-space-md">
          <Field label="Virksomhedsnavn"><Input required value={f.company_name} onChange={set("company_name")} /></Field>
          <Field label="CVR-nummer" error={fieldError(error, "cvr")}><Input required value={f.cvr} onChange={set("cvr")} inputMode="numeric" /></Field>
          <label className="flex items-center gap-space-xs font-body-sm text-body-sm sm:col-span-2"><input type="checkbox" checked={f.vat_registered} onChange={(e) => setF({ ...f, vat_registered: e.target.checked })} />Virksomheden er momsregistreret</label>
        </div>
      )}
      {minor && (
        <div className="rounded-lg bg-surface-container-low p-space-md space-y-space-sm">
          <p className="font-label-md text-label-md text-primary font-semibold flex items-center gap-1"><Icon name="family_restroom" size={18} />Du er under 18 – en forælder skal godkende</p>
          <p className="font-body-sm text-body-sm text-on-surface-variant">Vi sender en mail med aftalen og reglerne. Du kan godt dele dit link og skaffe kunder imens; vi udbetaler først, når aftalen er godkendt.</p>
          <div className="grid sm:grid-cols-2 gap-space-md">
            <Field label="Forælders navn" error={fieldError(error, "parent_name")}><Input required value={f.parent_name} onChange={set("parent_name")} /></Field>
            <Field label="Forælders e-mail" error={fieldError(error, "parent_email")}><Input type="email" required value={f.parent_email} onChange={set("parent_email")} /></Field>
          </div>
        </div>
      )}
      <div className="grid sm:grid-cols-2 gap-space-md">
        <Field label="Reg.nr. (kan vente)" error={fieldError(error, "bank_reg")}><Input value={f.bank_reg} onChange={set("bank_reg")} inputMode="numeric" maxLength={4} /></Field>
        <Field label="Kontonummer (kan vente)" hint="Hertil udbetaler vi. Gemmes krypteret." error={fieldError(error, "bank_account")}><Input value={f.bank_account} onChange={set("bank_account")} inputMode="numeric" /></Field>
      </div>
      <Field label="Din hilsen på din side (valgfri)" hint='Vises for dem, der bruger dit link. Fx "Min onkel bruger den i sit VVS-firma."'><Input maxLength={300} value={f.headline} onChange={set("headline")} /></Field>
      <Field label="Hvem vil du anbefale Dialogbot til? (valgfri)"><Textarea maxLength={1000} value={f.motivation} onChange={set("motivation")} /></Field>

      <fieldset className="space-y-space-md">
        <legend className="font-headline-sm text-headline-sm text-primary font-bold">Fire spørgsmål om reglerne</legend>
        {program.quiz.map((q, i) => (
          <div key={q.id} className={`rounded-lg p-space-md space-y-space-xs ${wrong.includes(q.id) ? "bg-error-container/40" : "bg-surface-container-low"}`}>
            <p className="font-label-lg text-label-lg">{i + 1}. {q.question}</p>
            {q.options.map((o) => (
              <label key={o.id} className="flex items-start gap-space-xs font-body-sm text-body-sm cursor-pointer">
                <input type="radio" name={q.id} value={o.id} checked={quiz[q.id] === o.id} onChange={() => setQuiz({ ...quiz, [q.id]: o.id })} className="mt-1" />{o.label}
              </label>
            ))}
            {wrong.includes(q.id) && <p className="font-label-sm text-label-sm text-error">Forkert – læs reglerne til venstre og prøv igen.</p>}
          </div>
        ))}
      </fieldset>
      {!answered && <Alert kind="info">Svar på alle fire spørgsmål for at tilmelde dig.</Alert>}
      <Button type="submit" icon="how_to_reg" disabled={pending || !answered} className="w-full h-12">{pending ? "Tilmelder…" : "Tilmeld mig som ambassadør"}</Button>
      <p className="font-label-sm text-label-sm text-on-surface-variant">Ved at tilmelde dig accepterer du reglerne. Vi godkender alle ambassadører manuelt – normalt inden for et par dage.</p>
    </form>
  );
}
