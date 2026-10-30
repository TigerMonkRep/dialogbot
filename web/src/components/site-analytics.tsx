"use client";
import { useEffect, useState } from "react";
import Script from "next/script";
import { usePathname } from "next/navigation";
import { Analytics } from "@vercel/analytics/next";

/** Website statistics, mounted once in the root layout.
 *
 *  Vercel Web Analytics sets no cookies and stores nothing about the person, so it runs everywhere without asking.
 *  Google Analytics 4 uses cookies, so it only loads after the visitor says yes in the banner below (the choice is
 *  kept in localStorage, and "Afvis" is remembered just like "Tillad"). Neither runs inside the customer app
 *  (/app) nor on the operator pages – those are logged-in users, not website visitors. The GA measurement id comes
 *  from NEXT_PUBLIC_GA_MEASUREMENT_ID; without it there is no banner and no Google script at all. */

const GA_ID = process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID;
const KEY = "db-consent";
type Consent = "granted" | "denied" | null;

function readConsent(): Consent {
  try { const v = localStorage.getItem(KEY); return v === "granted" || v === "denied" ? v : null; } catch { return null; }
}

export function SiteAnalytics() {
  const pathname = usePathname() ?? "/";
  const isApp = pathname.startsWith("/app") || pathname.startsWith("/login") || pathname.startsWith("/signup") || pathname.startsWith("/gastrohall");
  const [consent, setConsent] = useState<Consent>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => { setConsent(readConsent()); setReady(true); }, []);
  useEffect(() => {
    const onChange = () => setConsent(readConsent());
    window.addEventListener("db-consent", onChange);
    return () => window.removeEventListener("db-consent", onChange);
  }, []);

  const choose = (v: Exclude<Consent, null>) => {
    try { localStorage.setItem(KEY, v); } catch {}
    setConsent(v);
    window.dispatchEvent(new Event("db-consent"));
  };

  const showGa = Boolean(GA_ID) && !isApp && consent === "granted";
  const showBanner = Boolean(GA_ID) && !isApp && ready && consent === null;

  return (
    <>
      {!isApp && <Analytics />}
      {showGa && (
        <>
          <Script src={`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`} strategy="afterInteractive" />
          <Script id="ga4" strategy="afterInteractive">{`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());
            gtag('consent', 'default', {analytics_storage: 'granted', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied'});
            gtag('config', '${GA_ID}', {anonymize_ip: true});
          `}</Script>
        </>
      )}
      {showBanner && (
        <div role="dialog" aria-label="Cookies til statistik"
          className="fixed z-[70] left-3 right-3 bottom-3 sm:left-auto sm:right-5 sm:bottom-5 sm:max-w-[420px] rounded-2xl bg-white border-2 border-ink shadow-block p-4 flex flex-col gap-3"
          style={{ paddingBottom: "max(1rem, env(safe-area-inset-bottom))" }}>
          <p className="m-0 font-display font-bold text-[16px] text-ink">Må vi måle besøg?</p>
          <p className="m-0 text-[14px] text-ink-soft">
            Vi vil gerne bruge Google Analytics til at se, hvilke sider der bliver læst, så vi kan gøre hjemmesiden bedre.
            Det sætter en statistikcookie. Du kan sige nej – siden virker præcis lige godt. <a href="/privatliv" className="underline text-ink">Læs mere</a>.
          </p>
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={() => choose("granted")}
              className="inline-flex items-center justify-center min-h-11 px-4 rounded-xl bg-accent text-white font-semibold text-[15px] border-0 cursor-pointer hover:bg-accent-deep">Ja, det er fint</button>
            <button type="button" onClick={() => choose("denied")}
              className="inline-flex items-center justify-center min-h-11 px-4 rounded-xl bg-white border-2 border-ink text-ink font-semibold text-[15px] cursor-pointer hover:bg-panel">Nej tak</button>
          </div>
        </div>
      )}
    </>
  );
}

/** A small "Cookieindstillinger" link for the footer: clears the choice so the banner shows again. */
export function CookieSettingsLink({ className = "" }: { className?: string }) {
  if (!GA_ID) return null;
  return (
    <button type="button" className={`bg-transparent border-0 p-0 cursor-pointer ${className}`}
      onClick={() => { try { localStorage.removeItem(KEY); } catch {} window.dispatchEvent(new Event("db-consent")); }}>
      Cookieindstillinger
    </button>
  );
}
