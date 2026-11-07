import Link from "@/i18n/link";
import { cookies } from "next/headers";
import { ArrowIcon } from "@/components/site-icons";
import { API_BASE_URL, KNOWN_ACCOUNT_COOKIE, REFERRAL_COOKIE, SESSION_COOKIE } from "@/lib/config";
import { getT } from "@/i18n/server";

type Recommender = { first_name: string; headline: string; code: string; customer_discount_bp: number };

/** The ambassador who sent this visitor (cookie set by /a/{slug}); null when none or no longer active, and
 *  never for someone who already has an account (logged in now, or has logged in from this browser before). */
export async function recommender(): Promise<Recommender | null> {
  const store = await cookies();
  if (store.get(SESSION_COOKIE)?.value || store.get(KNOWN_ACCOUNT_COOKIE)?.value) return null;
  const ref = store.get(REFERRAL_COOKIE)?.value;
  if (!ref) return null;
  try {
    const r = await fetch(`${API_BASE_URL}/api/v1/public/ambassadors/${encodeURIComponent(ref)}`, { cache: "no-store" });
    return r.ok ? ((await r.json()) as Recommender) : null;
  } catch { return null; }
}

/** The Trin-gul welcome strip at the top of the entry page and /erhverv: "«Name» har anbefalet Dialogbot til dig".
 *  Renders nothing without an active referral. Texts: site.json → home.referral.*. */
export async function ReferralBanner() {
  const rec = await recommender();
  if (!rec) return null;
  const t = await getT("site");
  return (
    <section aria-label={t("home.referral.label")} className="bg-highlight border-b-2 border-ink">
      <div className="max-w-[1180px] mx-auto px-4 sm:px-6 py-3 flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-6">
        <span className="w-10 h-10 rounded-full bg-ink text-highlight flex items-center justify-center font-display font-extrabold text-lg shrink-0" aria-hidden>{rec.first_name.slice(0, 1)}</span>
        <div className="flex-1 min-w-0 text-ink">
          <p className="font-semibold text-[15px]">{t("home.referral.offer", { name: rec.first_name, pct: rec.customer_discount_bp / 100 })}</p>
          {rec.headline && <p className="text-sm">&ldquo;{rec.headline}&rdquo;</p>}
          <p className="text-xs text-ink-soft">{t("home.referral.bonus", { name: rec.first_name })}</p>
        </div>
        <Link href="/signup" className="inline-flex items-center justify-center gap-2 min-h-11 bg-ink text-white font-semibold text-[15px] px-5 rounded-xl no-underline">{t("home.referral.cta")}<ArrowIcon size={16} /></Link>
      </div>
    </section>
  );
}
