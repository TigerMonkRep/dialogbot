"use client";
import { useEffect, useState } from "react";
import { ChatIcon } from "./site-icons";
import { ProevChat } from "@/app/proev/proev-chat";

/** The floating "Snak med Dialogbot" chat. Open by default on /byggevejledning (wide screens only), closed elsewhere.
 *  It is the real /proev conversation (proev-chat.tsx): on a phone it takes the whole screen, on wider screens it is
 *  a panel above the launcher. Everything inside is a real <a>/<button>; closing never loses the conversation state
 *  only because the panel unmounts – reopening starts over, which is what "Luk" means here. */
export function ChatWidget({ defaultOpen = false }: { defaultOpen?: boolean }) {
  // Starts closed on the server; opens after mount on wide screens only – on a phone the chat takes the whole
  // screen, so it must never cover the page the visitor just asked for.
  const [open, setOpen] = useState(false);
  useEffect(() => {
    if (defaultOpen && window.matchMedia("(min-width: 640px)").matches) setOpen(true);
  }, [defaultOpen]);

  // Full-screen on phones: stop the page behind from scrolling while the chat is open.
  useEffect(() => {
    if (!open || !window.matchMedia("(max-width: 639px)").matches) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      {open && (
        <div className="fixed inset-0 z-50 bg-white sm:inset-auto sm:right-6 sm:bottom-24 sm:w-[400px] sm:max-w-[calc(100vw-48px)] sm:h-[min(540px,calc(100vh-140px))] sm:rounded-[20px] sm:border-2 sm:border-ink sm:shadow-block sm:overflow-hidden"
          style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
          <ProevChat embedded onClose={() => setOpen(false)} />
        </div>
      )}
      <button type="button" onClick={() => setOpen((o) => !o)} aria-label={open ? "Luk chatten" : "Åbn chatten"} aria-expanded={open}
        className={`fixed right-4 bottom-4 sm:right-6 sm:bottom-6 z-50 items-center gap-2.5 min-h-14 pl-4 pr-5 rounded-full bg-ink text-white border-2 border-ink shadow-block-highlight font-display font-bold text-base cursor-pointer ${open ? "hidden sm:inline-flex" : "inline-flex"}`}>
        <ChatIcon size={22} />
        {open ? "Luk" : "Snak med Dialogbot"}
      </button>
    </>
  );
}
