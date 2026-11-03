import { PRODUCT_SCREENSHOT } from "@/lib/proof";
import { getT } from "@/i18n/server";

/** Product screenshot (knowledge-approval diff or daily report) beside the demo transcript. Renders nothing
 *  until a real screenshot is set in src/lib/proof.ts. */
export async function ApprovalScreenshot() {
  if (!PRODUCT_SCREENSHOT) return null;
  const s = PRODUCT_SCREENSHOT;
  const t = await getT("site");
  return (
    <figure className="basis-full m-0 flex flex-col gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={s.src} alt={t("proof.data.screenshotAlt")} width={s.width} height={s.height} loading="lazy" className="block w-full max-w-[880px] h-auto rounded-[20px] border-2 border-ink shadow-block" />
      <figcaption className="text-[15px] text-ink-soft">{t("proof.screenshotCaption")}</figcaption>
    </figure>
  );
}
