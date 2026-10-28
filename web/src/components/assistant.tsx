"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { Icon } from "./ui";

type Chip = { label: string; href: string };

/** Shortcuts per page. They are plain links to the place where the thing is changed today; the assistant that
 *  proposes the change itself (before → after, then «Godkend») replaces them in a later release. */
const CHIPS: { match: (p: string) => boolean; chips: Chip[] }[] = [
  { match: (p) => p === "/app", chips: [
    { label: "Ret åbningstider", href: "/app/indstillinger/virksomhed" }, { label: "Tilføj en pris", href: "/app/viden?tab=k03#tilfoej" }, { label: "Vis ugens tal", href: "/app/ugen" }] },
  { match: (p) => p.startsWith("/app/viden"), chips: [
    { label: "Læs min prisliste ind", href: "/app/viden?tab=k03" }, { label: "Test mig som kunde", href: "/app/viden?tab=r06" }, { label: "Ret hilsenen", href: "/app/indstillinger/hilsen" }] },
  { match: (p) => p.startsWith("/app/opkald"), chips: [
    { label: "Det, der venter på mig", href: "/app/opkald/henvendelser" }, { label: "Mine opgaver", href: "/app/opkald/opgaver" }, { label: "Ret hvem der får besked", href: "/app/indstillinger/telefoni" }] },
  { match: (p) => p.startsWith("/app/ugen"), chips: [
    { label: "Se opkaldene", href: "/app/opkald" }, { label: "Tilføj et svar", href: "/app/viden?tab=k03#tilfoej" }] },
  { match: (p) => p.startsWith("/app/aftaler"), chips: [
    { label: "Ret bookingregler", href: "/app/aftaler" }, { label: "Forbind kalenderen", href: "/app/indstillinger/integrationer" }] },
  { match: (p) => p.startsWith("/app/kampagner"), chips: [
    { label: "Hør jeres stemme", href: "/app/indstillinger/stemmer" }, { label: "Se afregningen", href: "/app/konto/fakturering" }] },
];
const FALLBACK: Chip[] = [{ label: "Alle indstillinger", href: "/app/indstillinger" }, { label: "Hjælp", href: "/app/hjaelp" }];

function Panel({ chips, onClose, className = "" }: { chips: Chip[]; onClose?: () => void; className?: string }) {
  return (
    <aside aria-label="Ændr noget" className={`bg-paper border-2 border-ink rounded-2xl flex flex-col overflow-hidden ${className}`}>
      <div className="flex items-center gap-3 px-4 py-3.5 border-b-2 border-ink">
        <span className="inline-flex w-9 h-9 rounded-[10px] bg-accent items-center justify-center font-display font-extrabold text-white" aria-hidden>D</span>
        <div className="flex flex-col flex-1 min-w-0">
          <span className="font-display font-bold text-[16px] text-ink">Ændr noget</span>
          <span className="text-[12px] text-muted">Du ser ændringen, før den gælder</span>
        </div>
        {onClose && <button type="button" onClick={onClose} aria-label="Luk" className="w-11 h-11 -mr-2 rounded-xl flex items-center justify-center text-ink hover:bg-panel"><Icon name="close" size={22} /></button>}
      </div>
      <div className="flex flex-col gap-3 p-4 flex-1">
        <p className="m-0 px-3.5 py-2.5 text-[14px] leading-relaxed max-w-[320px] border-2 border-ink bg-paper text-ink rounded-[14px] rounded-bl-[4px]">
          Hvad vil du ændre? Vælg en genvej – den fører dig direkte til det rigtige sted.
        </p>
        <p className="m-0 text-[13px] text-muted">Du kan endnu ikke skrive til mig her. Det kommer i en senere udgave, og intet bliver ændret uden din godkendelse.</p>
      </div>
      <div className="flex flex-col gap-2.5 px-4 pt-3.5 pb-4 border-t-2 border-ink bg-panel">
        <span className="eyebrow">Genveje</span>
        <div className="flex flex-wrap gap-2">
          {chips.map((c) => <Link key={c.label} href={c.href} onClick={onClose} className="inline-flex items-center min-h-[44px] px-3.5 rounded-full bg-paper border-2 border-ink text-ink text-[14px] font-semibold hover:bg-panel-deep">{c.label}</Link>)}
        </div>
        <Link href="/app/indstillinger" onClick={onClose} className="text-[13px] text-muted underline underline-offset-2 w-fit">Alle indstillinger</Link>
      </div>
    </aside>
  );
}

/** The assistant «Ændr noget»: a sticky right-hand column from 1280 px, a full-screen sheet behind a floating button
 *  below that (same pattern as the chat on the public site). On I dag the page carries its own panel for now. */
export function AssistantDock() {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [open]);
  if (path === "/app" || path.startsWith("/app/konto") || path.startsWith("/app/hjaelp")) return null;
  const chips = CHIPS.find((c) => c.match(path))?.chips ?? FALLBACK;
  return (
    <>
      <div className="hidden xl:block w-[360px] shrink-0"><div className="sticky top-24"><Panel chips={chips} className="shadow-block" /></div></div>
      {open && (
        <div role="dialog" aria-modal="true" aria-label="Ændr noget" className="xl:hidden fixed inset-0 z-50 bg-paper flex flex-col" style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
          <Panel chips={chips} onClose={() => setOpen(false)} className="flex-1 rounded-none border-0" />
        </div>
      )}
      <button type="button" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}
        className="xl:hidden fixed right-4 bottom-[76px] sm:bottom-6 sm:right-6 z-40 inline-flex items-center gap-2 min-h-[52px] pl-4 pr-5 rounded-full bg-ink text-paper border-2 border-ink shadow-block-highlight font-display font-bold text-[15px]">
        <Icon name="edit" size={18} />Ændr noget
      </button>
    </>
  );
}
