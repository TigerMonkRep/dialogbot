import { backend } from "@/lib/api.server";
import { requireWorkspace } from "@/lib/workspace.server";
import { Stemmetest, type Overview } from "./client";

/** Operator view: compare Danish speech-recognition profiles on the same recordings. Test mode only – no customer call
 *  is moved by anything on this page. */
export default async function StemmetestPage() {
  await requireWorkspace();
  let data: Overview;
  try {
    data = await backend<Overview>("/operator/stemmetest");
  } catch {
    return <p className="bg-surface-container-lowest rounded-2xl p-space-lg border-2 border-ink font-body-md text-body-md text-on-surface-variant">Stemmetesten er kun for Dialogbot-operatører.</p>;
  }
  return (
    <section className="flex flex-col gap-space-lg">
      <div>
        <span className="eyebrow">Operatør</span>
        <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">Stemmetest</h1>
        <p className="font-body-sm text-body-sm text-on-surface-variant max-w-3xl">Sammenlign talegenkendelse på dansk med samme lyd. Testen flytter ingen kundeopkald og ændrer ikke produktionsruten.</p>
      </div>
      <Stemmetest data={data} />
    </section>
  );
}
