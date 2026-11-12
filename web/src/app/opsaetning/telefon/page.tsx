import { redirect } from "next/navigation";
import Link from "@/i18n/link";
import { backend } from "@/lib/api.server";
import { setupStatus } from "@/lib/setup.server";
import { nextStep, stepHref, stepNumber } from "@/lib/setup-steps";
import { requireWorkspace } from "@/lib/workspace.server";
import { StepHead } from "@/components/setup-parts";
import { SetupShell } from "@/components/setup-shell";
import { getRaw, getT } from "@/i18n/server";
import type { Telephony } from "@/app/app/(admin)/settings/telephony/client";
import { Phone, Voice, type VoicesData } from "../_parts/channels";
import { StepFooter } from "../_parts/footer";

/** Telefon (only when «Tage telefonen» is chosen): the voice, the number customers ring and when calls are forwarded.
 *  The Dialogbot number is connected and tested once the subscription is in place (Betaling). */
export default async function TelefonStep() {
  const ws = await requireWorkspace();
  const staff = ws.role !== "reader";
  const [st, profile, voices, tel] = await Promise.all([
    setupStatus(ws.id, ws.role),
    backend<{ legal_name: string; phone: string | null; cvr: string | null; address_line: string | null; postal_code: string | null; city: string | null }>(`/workspaces/${ws.id}/profile`),
    // voices.read is staff+: a reader gets 403 – never let that take the page down (F-E2B-04-G01).
    staff ? backend<VoicesData>(`/workspaces/${ws.id}/voices`).catch(() => null) : Promise.resolve(null),
    staff ? backend<Telephony>(`/workspaces/${ws.id}/telephony`).catch(() => null) : Promise.resolve(null),
  ]);
  if (!st.goals.inbound_phone) redirect(stepHref(nextStep("viden", st.goals)));
  const t = await getT("setup.telefonPage");
  const ts = await getT("setup.shell");
  const raw = await getRaw();
  const n = stepNumber("telefon", st.goals);
  const next = nextStep("telefon", st.goals);
  const address = [profile.address_line, [profile.postal_code, profile.city].filter(Boolean).join(" ")].filter(Boolean).join(", ");
  const canManage = ws.role === "owner" || ws.role === "admin";
  return (
    <SetupShell step="telefon" steps={st.steps} workspaceName={ws.name} wide assistant={{ wsId: ws.id, canChange: staff }}>
      <StepHead n={n} eyebrow={t("eyebrow", { n, total: st.steps.length })} title={t("title")} intro={t("intro")} need={raw<[string, string, string?][]>("setup.telefonPage.need")} needTitle={raw<string>("setup.need.title")} />
      <div className="flex flex-col gap-6">
        {!staff && <p role="status" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("readOnly")}</p>}
        {voices && <Voice wsId={ws.id} data={voices} canManage={canManage} company={profile.legal_name} />}
        {tel && <Phone wsId={ws.id} t={tel} canManage={canManage} profilePhone={profile.phone ?? ""} company={profile.legal_name} cvr={profile.cvr ?? ""} address={address} />}
        {tel && !tel.active && !st.paid && (
          <p className="rounded-2xl border-2 border-ink bg-highlight px-4 py-3 text-[15px] text-ink" data-testid="phone-live-when-paid">
            <b>{t("liveWhenPaid")}</b>{" "}<Link href={stepHref("betaling")} className="underline font-semibold">{t("toPayment")}</Link>
          </p>
        )}
        <StepFooter href={stepHref(next)} label={ts("next", { n: stepNumber(next, st.goals), label: ts(`labels.${next}`) })} status={t("status")} />
      </div>
    </SetupShell>
  );
}
