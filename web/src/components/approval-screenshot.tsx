import { PRODUCT_SCREENSHOT } from "@/lib/proof";

/** Product screenshot (knowledge-approval diff or daily report) beside the demo transcript. Renders nothing
 *  until a real screenshot is set in src/lib/proof.ts. */
export function ApprovalScreenshot() {
  if (!PRODUCT_SCREENSHOT) return null;
  const s = PRODUCT_SCREENSHOT;
  return (
    <figure className="basis-full m-0 flex flex-col gap-3">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img src={s.src} alt={s.alt} width={s.width} height={s.height} loading="lazy" className="block w-full max-w-[880px] h-auto rounded-[20px] border-2 border-ink shadow-block" />
      <figcaption className="text-[15px] text-ink-soft">Sådan ser det ud, når I godkender: Dialogbot viser jer ændringen først – før → efter, «Godkend?».</figcaption>
    </figure>
  );
}
