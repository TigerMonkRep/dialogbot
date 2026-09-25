"use client";
import { useId, useState } from "react";
import { Icon, inputCls } from "./ui";

export const PASSWORD_MIN = 10; // mirrors app/modules/identity/service.py

/** Password input with show/hide and a requirement list (A04). Only the length rule is enforced by the backend;
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
    <div className="space-y-space-sm">
      <div className="flex items-center justify-between">
        <label htmlFor={id} className="font-label-md text-label-md text-on-surface font-semibold">{label}</label>
      </div>
      <div className="relative">
        <input id={id} type={show ? "text" : "password"} required minLength={withRules ? PASSWORD_MIN : undefined} autoComplete={autoComplete} placeholder={placeholder ?? (withRules ? `Mindst ${PASSWORD_MIN} tegn` : undefined)}
          className={`${inputCls} pr-11 py-3`} value={value} onChange={(e) => onChange(e.target.value)} aria-describedby={withRules ? `${id}-rules` : undefined} aria-invalid={error ? true : undefined} />
        <button type="button" onClick={() => setShow(!show)} aria-label={show ? "Skjul adgangskode" : "Vis adgangskode"} aria-pressed={show} className="absolute right-2 top-1/2 -translate-y-1/2 w-9 h-9 rounded-lg flex items-center justify-center text-on-surface-variant hover:text-primary"><Icon name={show ? "visibility_off" : "visibility"} size={22} /></button>
      </div>
      {withRules && (
        <>
          <div className="grid grid-cols-3 gap-1" aria-hidden>{[0, 1, 2].map((i) => <span key={i} className={`h-1 rounded-full ${i < score ? (score === 3 ? "bg-secondary" : "bg-primary-container") : "bg-surface-container-highest"}`} />)}</div>
          <div id={`${id}-rules`} className="rounded-lg bg-surface-container-low p-space-sm space-y-1.5">
            <p className="font-label-sm text-label-sm uppercase tracking-wider text-on-surface-variant font-bold">Sikkerhedskrav</p>
            {rules.map(([text, ok, required]) => (
              <p key={text} className={`flex items-center gap-2 font-body-sm text-body-sm ${ok ? "text-primary" : "text-on-surface-variant"}`}>
                <Icon name={ok ? "check_circle" : "radio_button_unchecked"} size={18} className={ok ? "text-secondary" : ""} filled={ok} />
                <span>{text}{required && !ok ? <span className="sr-only"> (påkrævet, ikke opfyldt)</span> : null}</span>
              </p>
            ))}
          </div>
        </>
      )}
      {error && <p role="alert" className="font-label-md text-label-md text-error">{error}</p>}
    </div>
  );
}
