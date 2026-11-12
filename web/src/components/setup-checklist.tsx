import Link from "@/i18n/link";
import { getT } from "@/i18n/server";
import type { SetupStatus } from "@/lib/setup.server";
import { stepHref } from "@/lib/setup-steps";
import { Icon } from "./ui";

/** The one checklist of the setup – the same truth on «I dag», in «Alle indstillinger» and in the guide (Betaling): this
 *  workspace's steps (only the relevant ones), each done or not from the real data, so what is set up by hand on the
 *  settings pages counts exactly as in the guide. The headline names the one next thing:
 *   - something is not set up → «… ikke færdig · næste: <step>» (I dag / settings) with «Fortsæt» / «Tilbage til guiden»
 *   - set up, not paid → «Sidste skridt: vælg abonnement og betaling»
 *   - paid, a channel not live yet → «gå live»
 *  Renders nothing when everything is done. `where` only changes the words of the headline and the link. */
export async function SetupChecklist({ st, where }: { st: SetupStatus; where: "today" | "settings" | "guide" }) {
  // In the guide (Betaling) only while something before it is missing – the step itself is the payment and going live.
  if (st.done || (where === "guide" && st.setupDone)) return null;
  const t = await getT("setup.checklist");
  const ts = await getT("setup.shell");
  const label = (k: string) => ts(`labels.${k}`);
  const last = st.setupDone;
  const head = !last
    ? t(`next.${where}`, { label: label(st.next) })
    : !st.paid ? t("payNext") : t("goLive");
  const cta = where === "settings" && !last ? t("backToGuide") : t("continue");
  return (
    <section aria-label={t("aria")} data-testid="setup-checklist" className={`flex flex-col gap-3 px-5 py-4 rounded-2xl border-2 ${last ? "border-ink bg-highlight" : "border-dashed border-ink bg-paper"}`}>
      <Link href={stepHref(last ? "betaling" : st.next)} className="flex flex-wrap items-center gap-3 rounded-xl hover:underline underline-offset-2">
        <span className={`inline-flex px-2.5 py-1 rounded-full ${last ? "bg-paper" : "bg-highlight"} text-[11px] font-semibold uppercase tracking-[0.08em]`}>{last ? t("lastTag") : t("tag")}</span>
        <span className="flex-1 min-w-[200px] text-[15px] font-semibold text-ink">{head}</span>
        <span className="inline-flex items-center gap-1 text-[14px] font-semibold text-ink">{cta}<Icon name="arrow_forward" size={18} /></span>
      </Link>
      <ol className="flex flex-wrap gap-2" aria-label={t("listAria")}>
        {st.steps.map((s, i) => {
          const done = s.state === "done";
          return (
            <li key={s.key}>
              <Link href={stepHref(s.key)} aria-label={`${label(s.key)}: ${done ? t("done") : t("todo")}`} className={`inline-flex items-center gap-2 min-h-[44px] pl-1.5 pr-3 rounded-full border-[1.5px] border-ink text-[14px] font-semibold ${done ? "bg-ink text-paper" : s.key === st.next ? "bg-highlight text-ink" : "bg-paper text-ink"}`}>
                <span className={`w-8 h-8 rounded-full inline-flex items-center justify-center ${done ? "bg-paper text-ink" : "border-[1.5px] border-ink"}`} aria-hidden>{done ? <Icon name="check" size={16} /> : i + 1}</span>
                {label(s.key)}
              </Link>
            </li>
          );
        })}
      </ol>
      {where !== "guide" && <p className="text-[13px] text-ink-soft">{t("manualCounts")}</p>}
    </section>
  );
}
