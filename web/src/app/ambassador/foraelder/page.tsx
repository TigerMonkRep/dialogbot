"use client";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { api, type ApiError } from "@/lib/client";
import { Alert, Button, ErrorBox, Field, Icon, Input, useSubmit } from "@/components/ui";
import { StepNumber } from "@/components/lego";
import { useT } from "@/i18n/client";
import { kr, pct } from "../shared";

type Preview = { ambassador_name: string; parent_name: string | null; rules_text: string; terms: { bonus_minor: number; rate_bp: number; months: number }; confirmed: boolean };

/** A parent confirms that their child (under 18) may be a Dialogbot ambassador. Reached from the e-mail link. */
function Consent() {
  const token = useSearchParams().get("token") ?? "";
  const t = useT("landing.ambassador.parent");
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
  if (!token || loadErr) return <Alert kind="error">{t("invalid")}</Alert>;
  if (!p) return <p className="m-0 text-[17px] text-ink-soft">{t("loading")}</p>;
  const first = p.ambassador_name.split(" ")[0];
  if (ok || p.confirmed) return <Alert kind="ok">{t("done", { first })}</Alert>;
  return (
    <form onSubmit={(e) => { e.preventDefault(); run(); }} className="flex flex-col gap-4">
      <p className="m-0 text-[17px] leading-normal text-ink">{t("intro", { name: p.ambassador_name, first })}</p>
      <ul className="m-0 p-0 list-none text-[15px] leading-normal text-ink flex flex-col gap-2">
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{t("bonus", { amount: kr(p.terms.bonus_minor) })}</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{t("share", { rate: pct(p.terms.rate_bp), months: p.terms.months })}</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{t("payout", { first })}</li>
        <li className="flex gap-2.5"><Icon name="check" size={20} className="text-accent flex-shrink-0" />{t("stop")}</li>
      </ul>
      <div className="rounded-xl border-[1.5px] border-ink bg-panel p-4"><p className="m-0 eyebrow mb-1.5">{t("rulesTitle", { first })}</p><p className="m-0 text-[15px] leading-normal text-ink-soft">{p.rules_text}</p></div>
      <ErrorBox error={error} />
      <Field label={t("yourName")}><Input required value={name} onChange={(e) => setName(e.target.value)} autoComplete="name" /></Field>
      <label className="flex items-start gap-2.5 min-h-[44px] text-[15px] leading-normal text-ink"><input type="checkbox" checked={check} onChange={(e) => setCheck(e.target.checked)} className="mt-0.5 w-5 h-5 accent-accent flex-shrink-0" />{t("confirm", { name: p.ambassador_name, first })}</label>
      <Button type="submit" icon="verified" disabled={pending || !check || !name.trim()} className="w-full min-h-[52px] text-[17px] rounded-[14px]">{pending ? t("confirming") : t("submit")}</Button>
    </form>
  );
}

export default function ParentPage() {
  const t = useT("landing.ambassador.parent");
  return (
    <div className="max-w-xl mx-auto rounded-[20px] bg-white border-2 border-ink p-6 md:p-8 flex flex-col gap-5 shadow-block">
      <div className="flex items-center gap-3.5"><StepNumber value="1" /><div className="flex flex-col gap-1"><span className="eyebrow">{t("eyebrow")}</span><h1 className="m-0 font-display font-extrabold text-[clamp(24px,3vw,30px)] leading-[1.1] tracking-[-0.5px] text-ink">{t("title")}</h1></div></div>
      <Suspense><Consent /></Suspense>
    </div>
  );
}
