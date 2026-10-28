"use client";
import Link from "next/link";
import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

/** The old settings page, opened over «Alle indstillinger» from the right (full screen on a phone). Escape and the backdrop close it. */
export function Sheet({ title, children }: { title: string; children: React.ReactNode }) {
  const router = useRouter();
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") router.push("/app/indstillinger"); };
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [router]);
  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <Link href="/app/indstillinger" aria-label="Luk" tabIndex={-1} className="hidden sm:block flex-1 bg-ink/40" />
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" aria-label={title} className="w-full sm:w-[min(760px,92vw)] bg-panel border-l-2 border-ink overflow-y-auto outline-none" style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
        <div className="sticky top-0 z-10 flex items-center justify-between gap-3 bg-paper border-b-2 border-ink px-4 py-3">
          <h2 className="font-display font-extrabold text-[20px] text-ink">{title}</h2>
          <Link href="/app/indstillinger" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink text-[14px] font-semibold text-ink hover:bg-panel">Luk</Link>
        </div>
        <div className="p-4 md:p-6">{children}</div>
      </div>
    </div>
  );
}
