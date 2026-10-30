"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ArrowIcon, CloseIcon, PlayIcon } from "./site-icons";
import { VIDEO } from "@/lib/video";

/** The 70-second explainer (web/public/video/). A poster "chip" opens our own player – no iframe, nothing third
 *  party. On a phone the player takes the whole screen; on wider screens it is a dialog. The "Prøv Dialogbot" the
 *  video ends on is pixels, so when it ends we lay a real CTA card over it (and the same links always sit under the
 *  video for people who skip). Captions are burned in; the VTT track is there for screen readers but off by default. */

export function ExplainerVideo({ variant = "chip" }: { variant?: "chip" | "button" | "poster" }) {
  const [open, setOpen] = useState(false);
  const [ended, setEnded] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    // The visitor just clicked, so playing with sound is allowed; if the browser still refuses, the controls are there.
    videoRef.current?.play().catch(() => {});
    return () => { document.body.style.overflow = prev; window.removeEventListener("keydown", onKey); };
  }, [open]);

  const close = () => { setOpen(false); setEnded(false); };
  const again = () => { setEnded(false); const v = videoRef.current; if (v) { v.currentTime = 0; v.play().catch(() => {}); } };

  return (
    <>
      {variant === "poster" ? (
        <button type="button" onClick={() => setOpen(true)} aria-label={`${VIDEO.title} – afspil videoen (70 sekunder)`}
          className="group relative block w-full max-w-full aspect-video rounded-[20px] overflow-hidden border-2 border-ink bg-panel shadow-block text-left cursor-pointer p-0">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={VIDEO.poster} alt="" width={1920} height={1080} className="block w-full h-full object-cover" />
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="inline-flex items-center gap-3 pl-4 pr-6 min-h-16 rounded-full bg-ink text-white font-display font-bold text-lg border-2 border-ink shadow-block-highlight group-hover:bg-accent transition-colors">
              <span className="inline-flex w-10 h-10 rounded-full bg-accent text-white items-center justify-center"><PlayIcon size={18} /></span>
              Se, hvad Dialogbot kan · 70 sek.
            </span>
          </span>
        </button>
      ) : variant === "chip" ? (
        <button type="button" onClick={() => setOpen(true)}
          className="group inline-flex items-center gap-3.5 p-2 pr-5 rounded-2xl bg-white border-2 border-ink text-ink text-left cursor-pointer hover:bg-panel transition-colors max-w-full">
          <span className="relative block w-[104px] h-[62px] shrink-0 rounded-[10px] overflow-hidden border-[1.5px] border-ink bg-panel">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={VIDEO.thumb} alt="" width={640} height={360} className="block w-full h-full object-cover" />
            <span className="absolute inset-0 flex items-center justify-center">
              <span className="inline-flex w-8 h-8 rounded-full bg-accent text-white items-center justify-center group-hover:scale-110 transition-transform"><PlayIcon size={14} /></span>
            </span>
          </span>
          <span className="flex flex-col gap-0.5 min-w-0">
            <span className="font-display font-bold text-[16px] leading-tight">{VIDEO.title}</span>
            <span className="text-[13px] text-muted">70 sekunder · med undertekster · forklarer præcis, hvad vi tilbyder</span>
          </span>
        </button>
      ) : (
        <button type="button" onClick={() => setOpen(true)}
          className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-[22px] rounded-[14px] bg-white border-2 border-ink text-ink font-semibold text-[17px] cursor-pointer hover:bg-panel">
          <PlayIcon size={18} />{VIDEO.title} · 70 sek.
        </button>
      )}

      {open && (
        <div role="dialog" aria-modal="true" aria-label={VIDEO.title}
          className="fixed inset-0 z-[60] bg-ink sm:bg-ink/85 flex flex-col sm:items-center sm:justify-center sm:p-6"
          onClick={(e) => { if (e.target === e.currentTarget) close(); }}>
          <div className="flex flex-col w-full h-full sm:h-auto sm:max-w-[960px] bg-white sm:rounded-[20px] sm:border-2 sm:border-ink sm:shadow-block sm:overflow-hidden"
            style={{ paddingTop: "env(safe-area-inset-top)", paddingBottom: "env(safe-area-inset-bottom)" }}>
            <div className="flex items-center gap-3 px-4 py-3 border-b-2 border-ink">
              <span className="inline-flex w-8 h-8 rounded-[9px] bg-accent items-center justify-center text-white"><PlayIcon size={14} /></span>
              <span className="font-display font-bold text-[16px] flex-1 min-w-0 truncate">{VIDEO.title}</span>
              <button type="button" onClick={close} aria-label="Luk videoen" className="w-11 h-11 rounded-[10px] inline-flex items-center justify-center text-ink hover:bg-panel cursor-pointer"><CloseIcon size={18} /></button>
            </div>

            <div className="relative flex-1 flex flex-col min-h-0">
            <div className="bg-ink aspect-video w-full sm:my-0 my-auto">
              <video ref={videoRef} controls playsInline preload="none" poster={VIDEO.poster} onEnded={() => setEnded(true)}
                className="block w-full h-full" aria-label={VIDEO.description}>
                <source src={VIDEO.src} type="video/mp4" />
                <track kind="captions" src={VIDEO.captions} srcLang="da" label="Dansk" />
                Din browser kan ikke afspille videoen. <a href={VIDEO.src}>Hent videoen</a>.
              </video>
            </div>

            <div className="flex flex-wrap items-center gap-3 px-4 py-3 sm:py-4 border-t-2 border-ink bg-panel">
              <span className="text-[14px] text-ink-soft flex-1 min-w-[200px]">Lyder det som noget for jer?</span>
              <Link href="/proev" className="inline-flex items-center justify-center gap-2 min-h-11 px-4 rounded-xl bg-accent hover:bg-accent-deep text-white font-semibold text-[15px] no-underline">Prøv Dialogbot<ArrowIcon size={16} /></Link>
              <Link href="/byggevejledning" className="inline-flex items-center justify-center min-h-11 px-4 rounded-xl bg-white border-2 border-ink text-ink font-semibold text-[15px] no-underline hover:bg-panel">Byggevejledningen</Link>
            </div>
              {ended && (
                <div className="absolute inset-0 bg-ink/85 flex items-center justify-center p-4 overflow-y-auto">
                  <div className="flex flex-col gap-3 p-5 sm:p-6 rounded-[20px] bg-white border-2 border-ink shadow-block-highlight max-w-[420px] w-full text-center">
                    <span className="font-display font-extrabold text-[24px] leading-tight tracking-[-0.4px]">Prøv Dialogbot selv</span>
                    <span className="text-[15px] text-ink-soft">Den ringer til dig om 10 sekunder og tager imod dig som din egen receptionist.</span>
                    <Link href="/proev" className="inline-flex items-center justify-center gap-2.5 min-h-[52px] px-5 rounded-[14px] bg-accent hover:bg-accent-deep text-white font-semibold text-[17px] no-underline">Prøv den – den ringer til dig<ArrowIcon size={18} /></Link>
                    <Link href="/byggevejledning" className="inline-flex items-center justify-center min-h-11 px-4 rounded-xl bg-white border-2 border-ink text-ink font-semibold text-[15px] no-underline hover:bg-panel">Åbn byggevejledningen</Link>
                    <button type="button" onClick={again} className="text-sm font-semibold text-muted underline underline-offset-4 bg-transparent border-0 cursor-pointer">Se den igen</button>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
