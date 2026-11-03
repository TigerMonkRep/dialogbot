import { FOUNDER } from "@/lib/proof";

/** The named person behind Dialogbot. Renders nothing until FOUNDER is filled in in src/lib/proof.ts. */
export function FounderBlock({ className = "" }: { className?: string }) {
  if (!FOUNDER) return null;
  return (
    <section aria-label="Manden bag Dialogbot" className={`flex flex-wrap items-center gap-5 p-5 sm:p-6 rounded-[20px] bg-white border-2 border-ink ${className}`}>
      {FOUNDER.photo && /* eslint-disable-next-line @next/next/no-img-element */ <img src={FOUNDER.photo} alt={FOUNDER.name} width={88} height={88} className="w-22 h-22 rounded-full object-cover border-2 border-ink" />}
      <div className="flex-1 min-w-[240px] flex flex-col gap-1.5">
        <span className="font-display font-bold text-xl">{FOUNDER.name} <span className="text-[15px] font-medium text-muted">· {FOUNDER.role}</span></span>
        <p className="m-0 text-[16px] leading-[1.5] text-ink-soft">{FOUNDER.why}</p>
        {FOUNDER.profileUrl && <a href={FOUNDER.profileUrl} rel="noreferrer" className="text-[15px] font-semibold text-ink underline underline-offset-4 inline-flex items-center min-h-11">Find mig på LinkedIn →</a>}
      </div>
    </section>
  );
}
