import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { cookies } from "next/headers";
import { ViewAsBanner } from "@/components/shell.client";
import { isLoggedIn } from "@/lib/api.server";
import { VIEWAS_COOKIE } from "@/lib/config";

/** Frame for ambassadors: the public site's header and footer (Byggevejledning design) with an "Ambassadør" pill.
 *  Many ambassadors are not customers and have no workspace, so the app shell is not used. */
export default async function AmbassadorLayout({ children }: { children: React.ReactNode }) {
  const loggedIn = await isLoggedIn();
  let viewAs: { name: string; email: string } | null = null;
  try { const raw = (await cookies()).get(VIEWAS_COOKIE)?.value; if (raw) viewAs = JSON.parse(raw); } catch { /* ignore a broken cookie */ }
  const nav: [string, string][] = [
    ["/ambassador/bliv", "Programmet"],
    loggedIn ? ["/ambassador", "Min side"] : ["/login?next=/ambassador", "Log ind"],
  ];
  return (
    <div className="min-h-dvh bg-white text-ink flex flex-col">
      <a href="#main" className="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[60] focus:px-4 focus:py-2 focus:rounded-lg focus:bg-ink focus:text-white">Spring til indhold</a>
      {viewAs && <ViewAsBanner who={viewAs} />}
      <SiteHeader nav={nav} navAlways badge="Ambassadør" />
      <main id="main" className="flex-1 w-full max-w-[1180px] mx-auto px-4 sm:px-6 py-8 md:py-12">{children}</main>
      <SiteFooter compact />
    </div>
  );
}
