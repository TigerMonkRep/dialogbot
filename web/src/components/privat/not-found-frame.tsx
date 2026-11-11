import Link from "next/link";
import { LogoMark } from "@/components/ui";

/** The frame of the Privat 404 and error pages (F-JP-11): the orange theme, the Privat header and a way back. Used by
 *  app/privat/not-found.tsx (server) and app/privat/error.tsx (client) – no session, no backend. */
export function PrivatProblem({ title, text, children }: { title: string; text: string; children: React.ReactNode }) {
  return (
    <div data-theme="privat" className="min-h-dvh flex flex-col bg-panel text-ink app-type">
      <header className="flex-none flex items-center gap-2.5 px-4 min-h-16 border-b-2 border-ink bg-paper pt-safe">
        <Link href="/privat" className="flex items-center gap-2.5 min-h-[44px]"><LogoMark size={32} />
          <span className="font-display font-extrabold text-[20px] tracking-[-0.3px]">Dialogbot</span>
          <span className="text-[11px] font-bold tracking-[0.08em] uppercase text-accent border-[1.5px] border-accent rounded-full px-2 py-0.5">Privat</span></Link>
      </header>
      <main id="main" className="flex-1 flex flex-col items-center text-center gap-4 px-6 py-10 max-w-[480px] w-full mx-auto">
        <h1 className="m-0 font-display font-extrabold text-[28px] leading-[1.05] tracking-[-0.02em]">{title}</h1>
        <p className="m-0 text-[15px] leading-normal text-ink-soft">{text}</p>
        <div className="flex flex-col gap-2 w-full">{children}</div>
      </main>
    </div>
  );
}

export const PRIMARY = "inline-flex items-center justify-center min-h-[48px] rounded-xl bg-accent text-white font-semibold hover:bg-accent-deep";
export const SECONDARY = "inline-flex items-center justify-center min-h-[44px] rounded-xl border-2 border-ink font-semibold text-[15px] hover:bg-paper";
