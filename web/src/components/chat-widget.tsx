"use client";
import { useState } from "react";
import Link from "next/link";
import { ChatIcon, CloseIcon } from "./site-icons";

/** The floating "Snak med Dialogbot" popup from Main.dc.html. Open by default on /byggevejledning, closed elsewhere.
 *  Static greeting with three doors; the real conversation happens on /proev. Everything is a real <a>/<button>. */
export function ChatWidget({ defaultOpen = false }: { defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="fixed right-4 bottom-4 sm:right-6 sm:bottom-6 z-50 flex flex-col items-end gap-3 max-w-[calc(100vw-32px)] sm:max-w-[calc(100vw-48px)]">
      {open && (
        <section aria-label="Chat med Dialogbot" className="w-[380px] max-w-full bg-white border-2 border-ink rounded-[20px] shadow-block flex flex-col overflow-hidden">
          <div className="flex items-center gap-2.5 px-3.5 py-3 border-b-2 border-ink">
            <span className="inline-flex w-[34px] h-[34px] rounded-[10px] bg-accent items-center justify-center font-display font-extrabold text-white">D</span>
            <div className="flex flex-col">
              <span className="font-display font-bold text-[15px]">Dialogbot</span>
              <span className="text-xs text-muted flex items-center gap-1.5"><span aria-hidden className="w-[7px] h-[7px] rounded-full bg-[#1B9E5A]" />Svarer med det samme</span>
            </div>
            <button type="button" onClick={() => setOpen(false)} aria-label="Luk chatten" className="ml-auto w-11 h-11 rounded-[10px] bg-white inline-flex items-center justify-center text-ink hover:bg-panel">
              <CloseIcon size={18} />
            </button>
          </div>
          <div className="flex flex-col gap-2.5 p-3.5">
            <div className="flex gap-2 items-end">
              <span className="flex-none w-7 h-7 rounded-full bg-accent inline-flex items-center justify-center font-display font-extrabold text-xs text-white">P</span>
              <p className="m-0 px-3.5 py-2.5 rounded-[14px_14px_14px_4px] bg-white border-2 border-ink text-sm leading-normal">
                Hej! Jeg hedder Peter og er Dialogbots digitale receptionist. Vil du høre, hvordan jeg lyder, når jeg tager telefonen for <b>din</b> virksomhed? Jeg kan ringe til dig om 10 sekunder.
              </p>
            </div>
          </div>
          <div className="flex flex-col gap-2 px-3.5 pb-3.5">
            <Link href="/proev" className="inline-flex items-center justify-center min-h-[46px] px-4 rounded-xl bg-accent hover:bg-accent-deep text-white no-underline font-semibold text-[15px]">Ja, ring til mig</Link>
            <div className="flex gap-2">
              <Link href="/proev" className="flex-1 inline-flex items-center justify-center min-h-11 px-3 rounded-full bg-white border-2 border-ink text-ink no-underline font-semibold text-sm hover:bg-panel">Hvad kan du?</Link>
              <Link href="/byggevejledning#pris" className="flex-1 inline-flex items-center justify-center min-h-11 px-3 rounded-full bg-white border-2 border-ink text-ink no-underline font-semibold text-sm hover:bg-panel">Hvad koster det?</Link>
            </div>
          </div>
        </section>
      )}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-label={open ? "Luk chatten" : "Åbn chatten"} aria-expanded={open}
        className="inline-flex items-center gap-2.5 min-h-14 pl-4 pr-5 rounded-full bg-ink text-white border-2 border-ink shadow-block-highlight font-display font-bold text-base cursor-pointer">
        <ChatIcon size={22} />
        {open ? "Luk" : "Snak med Dialogbot"}
      </button>
    </div>
  );
}
