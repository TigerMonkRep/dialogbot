import { FOUNDER } from "@/lib/proof";
import { getT } from "@/i18n/server";

/** The named person behind Dialogbot. Renders nothing until FOUNDER is filled in in src/lib/proof.ts. */
export async function FounderBlock({ className = "" }: { className?: string }) {
  if (!FOUNDER) return null;
  const t = await getT("site");
  return (
    <section aria-label={t("proof.founderLabel")} className={`flex flex-wrap items-center gap-5 p-5 sm:p-6 rounded-[20px] bg-white border-2 border-ink ${className}`}>
      {FOUNDER.photo && /* eslint-disable-next-line @next/next/no-img-element */ <img src={FOUNDER.photo} alt={FOUNDER.name} width={88} height={88} className="w-22 h-22 rounded-full object-cover border-2 border-ink" />}
      <div className="flex-1 min-w-[240px] flex flex-col gap-1.5">
        <span className="font-display font-bold text-xl">{FOUNDER.name} <span className="text-[15px] font-medium text-muted">· {t("proof.data.founderRole")}</span></span>
        <p className="m-0 text-[16px] leading-[1.5] text-ink-soft">{t("proof.data.founderWhy")}</p>
        {FOUNDER.profileUrl && <a href={FOUNDER.profileUrl} rel="noreferrer" className="text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">{t("proof.linkedin")}</a>}
      </div>
    </section>
  );
}
