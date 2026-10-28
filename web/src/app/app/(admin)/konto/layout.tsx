import Link from "next/link";
import { backend } from "@/lib/api.server";
import { SubNav } from "../subnav";
import { LogoutButton } from "./logout";

const ITEMS: [string, string][] = [
  ["/app/konto", "Hvem må se og ændre"], ["/app/konto/abonnement", "Abonnement"], ["/app/konto/fakturering", "Fakturaer"], ["/app/konto/profil", "Min profil"],
];

/** Konto: who may see and change, the subscription, the invoices and your own profile. Reached from the avatar. */
export default async function KontoLayout({ children }: { children: React.ReactNode }) {
  const me = await backend<{ display_name: string; email: string; is_platform_operator?: boolean }>("/auth/me").catch(() => null);
  return (
    <section className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <span className="eyebrow">Konto</span>
          <h1 className="font-display font-extrabold text-[28px] md:text-[34px] leading-[1.05] tracking-[-0.8px] text-ink">{me?.display_name ?? "Konto"}</h1>
          {me && <p className="text-[14px] text-muted mt-1">{me.email}</p>}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/app/indstillinger" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-ink text-[14px] font-semibold hover:bg-panel">Alle indstillinger</Link>
          <Link href="/ambassador" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-paper text-ink text-[14px] font-semibold hover:bg-panel">Ambassadør</Link>
          {me?.is_platform_operator && <Link href="/app/operator/admin" className="inline-flex items-center min-h-[44px] px-4 rounded-xl border-2 border-ink bg-highlight text-ink text-[14px] font-semibold hover:bg-highlight-deep">Operatør</Link>}
          <LogoutButton />
        </div>
      </div>
      <SubNav label="Konto" items={ITEMS} />
      {children}
    </section>
  );
}
