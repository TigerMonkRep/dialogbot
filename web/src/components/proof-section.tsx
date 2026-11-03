import { CUSTOMER_QUOTES, REVIEW_SCORE, USAGE_COUNT } from "@/lib/proof";
import { getT } from "@/i18n/server";

/** Customer proof between the demo call and the price. Renders nothing until real data is filled in
 *  in src/lib/proof.ts. */
export async function ProofSection() {
  if (!CUSTOMER_QUOTES.length && !USAGE_COUNT && !REVIEW_SCORE) return null;
  const t = await getT("site");
  return (
    <section aria-labelledby="proof-title" className="bg-white border-b-2 border-ink">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-14 sm:py-20 flex flex-col gap-9">
        <div className="flex flex-col gap-3 max-w-[640px]">
          <span className="eyebrow text-[13px] tracking-[1.5px]">{t("proof.eyebrow")}</span>
          <h2 id="proof-title" className="m-0 font-display font-extrabold text-[clamp(30px,3.4vw,44px)] leading-[1.05] tracking-[-1px]">{t("proof.title")}</h2>
        </div>
        {(USAGE_COUNT || REVIEW_SCORE) && (
          <div className="flex flex-wrap gap-x-10 gap-y-4 items-baseline">
            {USAGE_COUNT && <p className="m-0"><span className="font-display font-extrabold text-[40px] tracking-[-1px] mr-2">{USAGE_COUNT.value}</span><span className="text-[17px] text-ink-soft">{t("proof.data.usageLabel")}</span></p>}
            {REVIEW_SCORE && <a href={REVIEW_SCORE.url} rel="noreferrer" className="text-ink text-[17px] underline underline-offset-4"><span className="font-display font-extrabold text-[40px] tracking-[-1px] mr-2 no-underline inline-block">{REVIEW_SCORE.rating}</span>{t("proof.trustpilot", { n: REVIEW_SCORE.reviews })}</a>}
          </div>
        )}
        {CUSTOMER_QUOTES.length > 0 && (
          <div className="grid gap-5 [grid-template-columns:repeat(auto-fit,minmax(min(260px,100%),1fr))]">
            {CUSTOMER_QUOTES.map((c) => (
              <figure key={c.id} className="m-0 flex flex-col gap-4 p-5 rounded-2xl bg-panel border-[1.5px] border-ink">
                <blockquote className="m-0 text-[16px] leading-[1.5]">&ldquo;{t(`proof.data.quotes.${c.id}.quote`)}&rdquo;</blockquote>
                <figcaption className="flex items-center gap-3 text-[14px] text-ink-soft">
                  {c.photo && /* eslint-disable-next-line @next/next/no-img-element */ <img src={c.photo} alt={c.name} width={44} height={44} className="w-11 h-11 rounded-full object-cover border-2 border-ink" />}
                  <span><strong className="text-ink">{c.name}</strong><br />{t(`proof.data.quotes.${c.id}.business`)}</span>
                </figcaption>
              </figure>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
