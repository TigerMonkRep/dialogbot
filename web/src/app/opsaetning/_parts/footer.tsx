"use client";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Icon } from "@/components/ui";
import { MobileActionBar } from "@/components/mobile-action-bar";

/** The step's one «Videre» (pinned on a phone): saves what is waiting first (`before`), then the next step. */
export function StepFooter({ href, label, status, before }: { href: string; label: string; status?: React.ReactNode; before?: (() => Promise<boolean>) | null }) {
  const router = useRouter();
  const [going, setGoing] = useState(false);
  return (
    <MobileActionBar className="flex-col-reverse sm:flex-row sm:items-center sm:justify-between">
      <p className="text-[13px] leading-snug text-muted" role="status">{status}</p>
      <button type="button" disabled={going} onClick={async () => {
        setGoing(true);
        if (before && !(await before())) { setGoing(false); return; }
        router.push(href);
      }} className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-xl font-semibold text-[16px] bg-accent text-white hover:bg-accent-deep disabled:opacity-70">
        {label}<Icon name="arrow_forward" size={18} />
      </button>
    </MobileActionBar>
  );
}
