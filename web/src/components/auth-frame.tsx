import Link from "next/link";
import { Icon } from "./ui";

/** Centered auth layout (A01–A05): logo block, headline, white card. */
export function AuthFrame({ title, subtitle, children, code }: { title: string; subtitle?: string; children: React.ReactNode; code?: string }) {
  return (
    <main className="min-h-dvh bg-surface flex flex-col">
      <header className="h-16 px-margin lg:px-margin-lg flex items-center justify-between">
        <Link href="/" className="flex items-center gap-space-sm"><div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center"><Icon name="support_agent" size={20} className="text-secondary-fixed" /></div><span className="font-display text-headline-sm text-primary font-bold tracking-tight">Dialogbot</span></Link>
        <Link href="/" className="text-label-md text-on-surface-variant hover:text-on-surface">Tilbage til forsiden</Link>
      </header>
      <div className="flex-1 flex items-start justify-center px-gutter py-margin-lg">
        <div className="w-full max-w-md space-y-space-lg">
          <div className="space-y-1">{code && <span className="text-secondary text-label-sm font-bold uppercase tracking-wider">{code}</span>}<h1 className="font-display text-headline-lg text-primary tracking-tight">{title}</h1>{subtitle && <p className="text-body-md text-on-surface-variant">{subtitle}</p>}</div>
          <div className="rounded-xl bg-surface-container-lowest p-space-xl shadow-sm">{children}</div>
        </div>
      </div>
    </main>
  );
}
