"use client";
import Link from "@/i18n/link";
import { Part } from "@/components/setup-parts";
import { Icon } from "@/components/ui";
import { MobileActionBar } from "@/components/mobile-action-bar";
import { useT } from "@/i18n/client";
import { stepHref, type StepKey } from "@/lib/setup-steps";
import { ReviewQueue, Sources } from "@/app/app/(admin)/viden/client";
import type { Item, SourceImport } from "@/app/app/(admin)/viden/types";

/** Trin 2 – Viden. A: the three ways in (website, file, text – the same as on /app/viden). B: the review of every
 *  suggestion, grouped per category. Going on is never blocked: the chat needs something approved, and says so there. */
export function Viden({ wsId, canDraft, canApprove, aiReady, website, latest, review, approved, next, nextN }: { wsId: string; canDraft: boolean; canApprove: boolean; aiReady: boolean; website: string; latest: SourceImport | null; review: Item[]; approved: number; next: StepKey; nextN: number }) {
  const t = useT("setup.viden");
  const ts = useT("setup.shell");
  return (
    <div className="flex flex-col gap-6">
      {!canDraft && <p role="status" className="rounded-xl bg-highlight px-4 py-3 text-[14px] text-ink">{t("readOnly")}</p>}
      <Part letter="A" title={t("a.title")} hint={t("a.hint")}>
        {canDraft && <Sources wsId={wsId} defaultUrl={website} initial={latest} aiReady={aiReady} openWith={latest ? null : website ? "site" : "file"} />}
      </Part>
      <Part letter="B" title={t("b.title")} hint={t("b.hint")}>
        {review.length > 0
          ? <div data-testid="viden-review"><ReviewQueue wsId={wsId} items={review} canApprove={canApprove} canDraft={canDraft} /></div>
          : <p className="rounded-xl border-[1.5px] border-dashed border-ink px-4 py-3 text-[14px] text-ink-soft">{t("b.empty")}</p>}
        <p className="text-[14px] text-ink-soft">{t("b.all")} <Link href="/app/viden" className="font-semibold text-ink underline underline-offset-2">{t("b.allLink")}</Link></p>
      </Part>
      <MobileActionBar className="flex-col-reverse sm:flex-row sm:items-center sm:justify-between">
        <p className="text-[13px] leading-snug text-muted" role="status">{approved ? t("approved", { n: approved }) : t("noneApproved")}</p>
        <Link href={stepHref(next)} className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-xl font-semibold text-[16px] bg-accent text-white hover:bg-accent-deep">
          {ts("next", { n: nextN, label: ts(`labels.${next}`) })}<Icon name="arrow_forward" size={18} />
        </Link>
      </MobileActionBar>
    </div>
  );
}
