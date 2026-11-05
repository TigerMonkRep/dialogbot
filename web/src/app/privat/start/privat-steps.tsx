"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useRaw, useT } from "@/i18n/client";
import { BuildProgress, Choice, CodeStep, FunnelShell, FunnelState, Gate, NextButton, Question, reachableStep, useFunnel, type BuildRow, type Option } from "@/components/funnel";
import { HATE_CALLS, HOOKS, HOUSEHOLD, POSTPONED, REMIND_AT, type BuildPrivat } from "@/lib/funnel/api";
import { LogoMark } from "@/components/ui";

const GATE = 6;
const ICON: Record<string, string> = {
  dentist: "stethoscope", bike: "sparkle", car_inspection: "car", gift: "gift", doctor: "stethoscope", hairdresser: "sparkle", insurance: "receipt", landlord: "home",
  alone: "user", couple: "users", kids: "cake", parents: "users",
  health: "stethoscope", workshop: "car", municipality: "receipt", restaurant: "utensils",
  morning: "bell", lunch: "bell", evening: "bell",
};

/** The six Privat screens (funnel brief, table «Privat-funnel»); step 6 is the gate and, once the code is sent, the
 *  code – then the person lands in Min dag with their own tasks. */
export function PrivatStep({ step }: { step: number }) {
  const f = useFunnel();
  const router = useRouter();
  useEffect(() => {
    if (f.status !== "ready") return;
    if (f.draft?.gated) { void f.restart(); return; }
    const r = Math.min(f.total, reachableStep(f.draft, f.gate, GATE));
    if (step > r) router.replace(`${f.base}/${r}`);
  }, [f, step, router]);
  return (
    <FunnelShell brand="Dialogbot Privat">
      {f.status !== "ready" || !f.draft ? <FunnelState status={f.status === "error" ? "error" : "loading"} error={f.error} onRetry={() => void f.restart()} />
        : step === 1 ? <Step1 /> : step === 2 ? <Step2 /> : step === 3 ? <Step3 /> : step === 4 ? <Step4 /> : step === 5 ? <Step5 /> : <Step6 />}
    </FunnelShell>
  );
}

function useSingle(step: number, key: "household" | "hate_calls" | "remind_at") {
  const { draft, answer, next } = useFunnel();
  const [busy, setBusy] = useState(false);
  const pick = async (v: string | string[]) => {
    if (busy) return;
    setBusy(true);
    await answer(step, { [key]: v as string });
    setBusy(false);
    next();
  };
  return { value: draft?.answers[key] ?? null, pick, busy };
}

function Step1() {
  const t = useT("privat.funnel.s1");
  const { draft, hook, answer, next } = useFunnel();
  const [chosen, setChosen] = useState<string[]>(draft?.answers.postponed ?? []);
  const [name, setName] = useState<string>(draft?.answers.assistant_name ?? "");
  const [busy, setBusy] = useState(false);
  const h = hook && (HOOKS as readonly string[]).includes(hook) ? hook : "default";
  const options: Option[] = POSTPONED.map((k) => ({ key: k, label: t(`postponed.${k}`), icon: ICON[k] }));
  const go = async () => {
    if (!chosen.length || busy) return;
    setBusy(true);
    await answer(1, { postponed: chosen, assistant_name: name.trim() });
    setBusy(false);
    next();
  };
  return (
    <>
      <Question eyebrow={h === "default" ? undefined : t(`hooks.${h}`)} title={t("title")} help={t("help")} />
      <Choice options={options} value={chosen} onChange={(v) => setChosen(v as string[])} multi columns={2} />
      <label className="flex flex-col gap-1 text-[14px] text-ink-soft">
        {t("nameLabel")}
        <input value={name} maxLength={20} onChange={(e) => setName(e.target.value)} placeholder="Peter" data-testid="assistant-name"
          className="min-h-[48px] rounded-[14px] border-2 border-ink bg-paper px-3.5 text-[16px] text-ink" />
        <span className="text-[12px] text-muted">{t("nameHint")}</span>
      </label>
      <NextButton onClick={() => void go()} disabled={!chosen.length} busy={busy} />
    </>
  );
}

function Step2() {
  const t = useT("privat.funnel.s2");
  const { value, pick } = useSingle(2, "household");
  const options: Option[] = HOUSEHOLD.map((k) => ({ key: k, label: t(`household.${k}.label`), hint: t(`household.${k}.hint`), icon: ICON[k] }));
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      <Choice options={options} value={value} onChange={pick} />
    </>
  );
}

function Step3() {
  const t = useT("privat.funnel.s3");
  const raw = useRaw();
  const { draft, answer, next } = useFunnel();
  const [choice, setChoice] = useState<string | null>(draft?.answers.hate_calls ?? null);
  const [busy, setBusy] = useState(false);
  const options: Option[] = HATE_CALLS.map((k) => ({ key: k, label: t(`hate.${k}`), icon: ICON[k] }));
  const lines = choice ? raw<{ who: "peter" | "them"; text: string }[]>(`privat.funnel.s3.examples.${choice}`) ?? [] : [];
  const go = async () => {
    if (!choice || busy) return;
    setBusy(true);
    await answer(3, { hate_calls: choice });
    setBusy(false);
    next();
  };
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      <Choice options={options} value={choice} onChange={(v) => setChoice(v as string)} columns={2} />
      {choice && (
        <section aria-label={t("exampleAria")} className="rounded-[22px] border-2 border-ink bg-white p-4 flex flex-col gap-2.5" data-example={choice}>
          <div className="flex items-center gap-2 text-[13px] text-muted"><LogoMark size={26} /><span><b className="text-ink">Peter</b> · {t("exampleRole")}</span></div>
          {lines.map((l, i) => (
            <p key={i} className={`m-0 max-w-[88%] px-3.5 py-2.5 text-[15px] leading-[1.45] ${l.who === "peter" ? "self-start bg-panel border-2 border-ink rounded-[18px_18px_18px_6px]" : "self-end bg-ink text-white rounded-[18px_18px_6px_18px]"}`}>{l.text}</p>
          ))}
          <p className="m-0 text-[13px] text-muted">{t("exampleNote")}</p>
        </section>
      )}
      <NextButton onClick={() => void go()} disabled={!choice} busy={busy} />
    </>
  );
}

function Step4() {
  const t = useT("privat.funnel.s4");
  const { value, pick } = useSingle(4, "remind_at");
  const options: Option[] = REMIND_AT.map((k) => ({ key: k, label: t(`remind.${k}.label`), hint: t(`remind.${k}.hint`), icon: ICON[k] }));
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      <Choice options={options} value={value} onChange={pick} />
    </>
  );
}

function Step5() {
  const t = useT("privat.funnel.s5");
  const { draft, answer, next } = useFunnel();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const b = (draft?.build ?? null) as BuildPrivat | null;
  const rows = useMemo<BuildRow[]>(() => [
    { key: "tasks", label: t("rows.tasks"), state: b ? "done" : "pending", detail: b ? t("detail.tasks", { n: b.tasks }) : undefined },
    { key: "lists", label: t("rows.lists"), state: b ? (b.lists > 0 ? "done" : "skipped") : "pending", detail: b ? t("detail.lists", { n: b.lists }) : undefined },
    { key: "first_call", label: t("rows.firstCall"), state: b ? (b.first_call ? "done" : "skipped") : "pending", detail: b ? (b.first_call ? b.first_call.title : t("detail.noCall")) : undefined },
  ], [b, t]);
  const settled = useCallback(() => setReady(true), []);
  const go = async () => {
    if (busy) return;
    setBusy(true);
    await answer(5, {});
    setBusy(false);
    next();
  };
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      {b && (
        <p className="m-0 rounded-2xl border-2 border-ink bg-highlight px-4 py-3 font-display font-extrabold text-[20px] text-ink" data-summary>
          {[t("summary.tasks", { n: b.tasks }), t("summary.lists", { n: b.lists }), b.first_call ? t("summary.call", { n: 1 }) : null].filter(Boolean).join(" · ")}
        </p>
      )}
      <BuildProgress rows={rows} onSettled={settled} />
      <NextButton onClick={() => void go()} disabled={!ready} busy={busy}>{t("cta")}</NextButton>
    </>
  );
}

/** Gate, then – in the same URL – the code. */
function Step6() {
  const t = useT("privat.funnel.s6");
  const { gate, draft } = useFunnel();
  const [codeSent, setCodeSent] = useState<boolean>(() => !!gate && gate.draftId === draft?.id);
  if (codeSent) return <CodeStep title={t("codeTitle")} gateStep={GATE} onBack={() => setCodeSent(false)} />;
  return <Gate title={t("title")} lead={t("lead")} consent={t("consent")} onCodeSent={() => setCodeSent(true)} />;
}
