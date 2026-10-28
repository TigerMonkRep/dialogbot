"use client";
import { useId, useState } from "react";
import { Icon, inputCls } from "./ui";

export const PASSWORD_MIN = 10; // mirrors app/modules/identity/service.py

/** Password input with show/hide and a requirement list. Only the length rule is enforced by the backend;
 *  the others are shown as recommendations so the UI never claims a check the server does not make. */
export function PasswordField({ label, value, onChange, error, autoComplete = "new-password", withRules = true, placeholder }: {
  label: string; value: string; onChange: (v: string) => void; error?: string; autoComplete?: string; withRules?: boolean; placeholder?: string;
}) {
  const id = useId();
  const [show, setShow] = useState(false);
  const rules: [string, boolean, boolean][] = [
    [`Mindst ${PASSWORD_MIN} tegn`, value.length >= PASSWORD_MIN, true],
    ["Både store og små bogstaver (anbefalet)", /[a-zæøå]/.test(value) && /[A-ZÆØÅ]/.test(value), false],
    ["Mindst ét tal eller specialtegn (anbefalet)", /[0-9!@#$%&*?_\-+=.,;:]/.test(value), false],
  ];
  const score = rules.filter(([, ok]) => ok).length;
  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="text-[13px] font-semibold text-ink">{label}</label>
      </div>
      <div className="relative">
        <input id={id} type={show ? "text" : "password"} required minLength={withRules ? PASSWORD_MIN : undefined} autoComplete={autoComplete} placeholder={placeholder ?? (withRules ? `Mindst ${PASSWORD_MIN} tegn` : undefined)}
          className={`${inputCls} pr-12`} value={value} onChange={(e) => onChange(e.target.value)} aria-describedby={withRules ? `${id}-rules` : undefined} aria-invalid={error ? true : undefined} />
        <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Skjul adgangskode" : "Vis adgangskode"} aria-pressed={show} className="absolute right-1.5 top-1/2 -translate-y-1/2 w-10 h-10 rounded-lg flex items-center justify-center text-muted hover:text-ink hover:bg-panel"><Icon name={show ? "visibility_off" : "visibility"} size={22} /></button>
      </div>
      {withRules && (
        <>
          <div className="grid grid-cols-3 gap-1" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className={`h-1.5 rounded-full ${i < score ? (score === 3 ? "bg-success" : "bg-accent") : "bg-line"}`} />)}</div>
          <div id={`${id}-rules`} className="rounded-xl bg-panel border-[1.5px] border-ink p-3 space-y-1.5">
            <p className="eyebrow">Sikkerhedskrav</p>
            {rules.map(([text, ok, required]) => (
              <p key={text} className={`flex items-center gap-2 font-body-sm text-body-sm ${ok ? "text-ink" : "text-muted"}`}>
                <Icon name={ok ? "check_circle" : "radio_button_unchecked"} size={18} className={ok ? "text-success" : ""} filled={ok} />
                <span>{text}{required && !ok ? <span className="sr-only"> (påkrævet, ikke opfyldt)</span> : null}</span>
              </p>
            ))}
          </div>
        </>
      )}
      {error && <p role="alert" className="text-label-md text-danger">{error}</p>}
    </div>
  );
}
