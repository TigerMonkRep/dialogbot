"use client";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useT } from "@/i18n/client";
import Link from "@/i18n/link";
import { SIGNUP_ERHVERV } from "@/lib/contact";
import { BuildProgress, Choice, CodeStep, Estimate, FunnelShell, FunnelState, Gate, NextButton, PlaceSearch, Question, reachableStep, useFunnel, type BuildRow, type Option } from "@/components/funnel";
import { HOOKS, INDUSTRIES, MISSED, WANTS, localEstimate, type BuildErhverv, type Industry, type Place } from "@/lib/funnel/api";

const GATE = 6;
const ICON: Record<Industry, string> = { haandvaerker: "home", klinik: "stethoscope", salon: "sparkle", vaerksted: "car", raadgiver: "suitcase", restaurant: "utensils" };

/** The seven Erhverv screens (funnel brief, table «Erhverv-funnel»). One question each; the answer is PATCHed to the
 *  draft and the URL moves on. A deep link past what the draft has answered is sent back to the right step. */
export function ErhvervStep({ step }: { step: number }) {
  const f = useFunnel();
  const t = useT("site.funnel.erhverv");
  const router = useRouter();
  useEffect(() => {
    if (f.status !== "ready") return;
    if (f.draft?.gated) { void f.restart(); return; }
    const r = Math.min(f.total, reachableStep(f.draft, f.gate, GATE));
    if (step > r) router.replace(`${f.base}/${r}`);
  }, [f, step, router]);
  return (
    <FunnelShell>
      {f.status !== "ready" || !f.draft ? <FunnelState status={f.status === "error" ? "error" : "loading"} error={f.error} onRetry={() => void f.restart()} />
        : step === 1 ? <Step1 /> : step === 2 ? <Step2 /> : step === 3 ? <Step3 /> : step === 4 ? <Step4 /> : step === 5 ? <Step5 /> : step === 6 ? <Step6 /> : <Step7 />}
      {/* The quiz is one way in, never the only one: sign-up is open day and night without it (S0). */}
      {step < GATE && <Link href={SIGNUP_ERHVERV} data-signup-direct className="self-start mt-2 text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">{t("signupDirect")}</Link>}
    </FunnelShell>
  );
}

function Step1() {
  const t = useT("site.funnel.erhverv");
  const { draft, hook, answer, next } = useFunnel();
  const [busy, setBusy] = useState(false);
  const h = hook && (HOOKS as readonly string[]).includes(hook) ? hook : "default";
  const options: Option[] = INDUSTRIES.map((k) => ({ key: k, label: t(`industries.${k}`), icon: ICON[k] }));
  const pick = async (v: string | string[]) => {
    if (busy) return;
    setBusy(true);
    await answer(1, { industry: v as Industry });
    setBusy(false);
    next();
  };
  return (
    <>
      <Question eyebrow={h === "default" ? undefined : t(`hooks.${h}.eyebrow`)} title={t(`hooks.${h}.title`)} help={t(`hooks.${h}.help`)} />
      <Choice options={options} value={draft?.answers.industry ?? null} onChange={pick} columns={2} />
    </>
  );
}

function Step2() {
  const t = useT("site.funnel.erhverv.s2");
  const { draft, answer, next } = useFunnel();
  const [name, setName] = useState(draft?.answers.company_name ?? "");
  const [place, setPlace] = useState<Place | null>(draft?.company && draft.answers.place_id ? { place_id: draft.answers.place_id, name: draft.company.name, address: draft.company.address ?? "", phone_display: draft.company.phone_display, website: draft.company.website, open_now: null } : null);
  const [busy, setBusy] = useState(false);
  const ok = name.trim().length >= 2;
  const go = async () => {
    if (!ok || busy) return;
    setBusy(true);
    await answer(2, { company_name: name.trim(), place_id: place?.place_id ?? null });
    setBusy(false);
    next();
  };
  return (
    <form onSubmit={(e) => { e.preventDefault(); void go(); }} className="flex flex-col gap-5">
      <Question title={t("title")} help={t("help")} />
      <PlaceSearch value={name} place={place} industry={draft?.answers.industry} onChange={(n, p) => { setName(n); setPlace(p); }} />
      <NextButton type="submit" disabled={!ok} busy={busy} />
    </form>
  );
}

function Step3() {
  const t = useT("site.funnel.erhverv.s3");
  const { draft, answer, next } = useFunnel();
  const [missed, setMissed] = useState<string[]>(draft?.answers.missed ?? []);
  const [perWeek, setPerWeek] = useState<number | null>(draft?.answers.missed_per_week ?? null);
  const [busy, setBusy] = useState(false);
  const est = draft?.estimate ?? localEstimate(draft?.answers.industry, missed);
  const value = perWeek ?? est.missed_per_week;
  const options: Option[] = MISSED.map((k) => ({ key: k, label: t(`missed.${k}`) }));
  const toggle = (v: string | string[]) => {
    const m = v as string[];
    setMissed(m);
    if (m.length) void answer(3, { missed: m }); // the backend answers with its estimate
  };
  const go = async () => {
    if (!missed.length || busy) return;
    setBusy(true);
    await answer(3, { missed, missed_per_week: value });
    setBusy(false);
    next();
  };
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      <Choice options={options} value={missed} onChange={toggle} multi />
      {missed.length > 0 && <Estimate value={value} onChange={setPerWeek} />}
      <NextButton onClick={() => void go()} disabled={!missed.length} busy={busy} />
    </>
  );
}

function Step4() {
  const t = useT("site.funnel.erhverv.s4");
  const { draft, answer, next } = useFunnel();
  const [wants, setWants] = useState<string[]>(draft?.answers.wants ?? []);
  const [busy, setBusy] = useState(false);
  const options: Option[] = WANTS.map((k) => ({ key: k, label: t(`wants.${k}.label`), hint: t(`wants.${k}.hint`) }));
  const go = async () => {
    if (!wants.length || busy) return;
    setBusy(true);
    await answer(4, { wants });
    setBusy(false);
    next();
  };
  return (
    <>
      <Question title={t("title")} help={t("help")} />
      <Choice options={options} value={wants} onChange={(v) => setWants(v as string[])} multi />
      <NextButton onClick={() => void go()} disabled={!wants.length} busy={busy} />
    </>
  );
}

function Step5() {
  const t = useT("site.funnel.erhverv.s5");
  const { draft, answer, next } = useFunnel();
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const b = (draft?.build ?? null) as BuildErhverv | null;
  const company = draft?.company?.name ?? draft?.answers.company_name ?? "";
  const rows = useMemo<BuildRow[]>(() => [
    { key: "knowledge", label: t("rows.knowledge"), state: b?.knowledge ?? "pending", detail: b?.knowledge === "skipped" ? t("detail.knowledgeSkipped") : undefined },
    { key: "voice", label: t("rows.voice"), state: b?.voice ?? "pending" },
    { key: "hours", label: t("rows.hours"), state: b?.hours ?? "pending", detail: b?.hours === "default" ? t("detail.hoursDefault") : b?.hours === "done" && draft?.company?.opening_hours_text ? t("detail.hoursDone", { hours: draft.company.opening_hours_text }) : undefined },
    { key: "number", label: t("rows.number"), state: b?.number ?? "pending" },
  ], [b, t, draft?.company?.opening_hours_text]);
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
      <Question title={company ? t("titleNamed", { company }) : t("title")} help={t("help")} />
      <BuildProgress rows={rows} onSettled={settled} />
      <NextButton onClick={() => void go()} disabled={!ready} busy={busy}>{t("cta")}</NextButton>
    </>
  );
}

function Step6() {
  const t = useT("site.funnel.erhverv.s6");
  const { go } = useFunnel();
  return <Gate title={t("title")} lead={t("lead")} consent={t("consent")} onCodeSent={() => go(7)} />;
}

function Step7() {
  const t = useT("site.funnel.erhverv.s7");
  return <CodeStep title={t("title")} gateStep={GATE} />;
}
