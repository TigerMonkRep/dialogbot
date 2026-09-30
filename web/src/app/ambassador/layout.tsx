import Link from "next/link";
import { Icon } from "@/components/ui";
import { isLoggedIn } from "@/lib/api.server";

/** Standalone frame for ambassadors: many are not customers and have no workspace, so the app shell is not used. */
export default async function AmbassadorLayout({ children }: { children: React.ReactNode }) {
  const loggedIn = await isLoggedIn();
  return (
    <div className="min-h-dvh bg-surface flex flex-col">
      <header className="sticky top-0 z-40 bg-surface/90 backdrop-blur-xl shadow-[0_1px_8px_rgba(22,78,67,0.06)]">
        <div className="h-16 max-w-6xl mx-auto px-4 sm:px-margin-md flex items-center justify-between gap-space-md">
          <Link href="/ambassador" className="flex items-center gap-space-sm min-w-0">
            <span className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center text-on-primary flex-shrink-0"><Icon name="support_agent" size={20} /></span>
            <span className="font-headline-sm text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span>
            <span className="hidden sm:inline px-2 py-0.5 rounded-full bg-secondary-container text-on-secondary-container font-label-sm text-label-sm font-bold uppercase tracking-wider">Ambassadør</span>
          </Link>
          <nav className="flex items-center gap-space-xs">
            <Link href="/ambassador/bliv" className="px-space-sm py-2 rounded-lg font-label-md text-label-md text-on-surface-variant hover:bg-surface-container">Programmet</Link>
            {loggedIn ? <Link href="/ambassador" className="px-space-sm py-2 rounded-lg font-label-md text-label-md text-primary font-semibold hover:bg-surface-container">Min side</Link>
              : <Link href="/login?next=/ambassador" className="px-space-sm py-2 rounded-lg font-label-md text-label-md text-primary font-semibold hover:bg-surface-container">Log ind</Link>}
          </nav>
        </div>
      </header>
      <main id="main" className="flex-1 w-full max-w-6xl mx-auto px-4 sm:px-margin-md py-space-lg md:py-space-xl">{children}</main>
      <footer className="text-center font-label-sm text-label-sm text-on-surface-variant py-space-lg px-4">Dialogbot Ambassadør · Spørgsmål? Skriv til os fra <Link href="/ambassador" className="underline">din side</Link>.</footer>
    </div>
  );
}
