import type { NextConfig } from "next";
import { readFileSync } from "node:fs";

// Shown in the app footer: the release version from package.json plus the short commit Vercel built.
const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
const commit = (process.env.VERCEL_GIT_COMMIT_SHA ?? "").slice(0, 7);

/** Kundeapp v2: the old routes live on as permanent (308) redirects so bookmarks, e-mails, invitations and the PWA start
 *  URL keep working. Query strings (e.g. ?tab=k03) are carried over. Remove them only after a release or more. */
const MOVED: [string, string][] = [
  ["/app/overview", "/app"],
  ["/app/knowledge", "/app/viden"],
  ["/app/reception", "/app/indstillinger?ark=hilsen"],
  // The requirement matrix's reception sub-routes (R04–R07, F-V2-07-R05): widget → webchat sheet, script → greeting
  // sheet, test → «Det ved den» (the assistant's test mode), routing/hours/handoff → telephony sheet.
  ["/app/reception/widget", "/app/indstillinger?ark=webchat"],
  ["/app/reception/assistant", "/app/indstillinger?ark=hilsen"],
  ["/app/reception/test", "/app/viden"],
  ["/app/reception/routing", "/app/indstillinger?ark=telefoni"],
  ["/app/inbox", "/app/opkald"],
  ["/app/inbox/:id", "/app/opkald/:id"],
  ["/app/leads", "/app/opkald?f=to_you"],
  ["/app/leads/:id", "/app/opkald/henvendelser/:id"],
  ["/app/tasks", "/app/opkald?f=to_you"],
  ["/app/notifications", "/app/opkald?f=to_you"],
  ["/app/reports", "/app/ugen"],
  ["/app/bookings", "/app/aftaler"],
  ["/app/campaigns", "/app/kampagner"],
  ["/app/campaigns/:id", "/app/kampagner/:id"],
  ["/app/settings", "/app/indstillinger"],
  ["/app/settings/team", "/app/konto"],
  ["/app/konto/profil", "/app/konto"],
  ["/app/konto/abonnement", "/app/konto"],
  ["/app/konto/fakturering", "/app/konto"],
  ["/app/settings/profile", "/app/konto"],
  ["/app/settings/agreement", "/app/konto"],
  ["/app/billing", "/app/konto"],
  ["/app/settings/activity", "/app/indstillinger?ark=log"],
  ["/app/settings/business", "/opsaetning/1"],
  ["/app/settings/telephony", "/app/indstillinger?ark=telefoni"],
  ["/app/settings/webchat", "/app/indstillinger?ark=webchat"],
  ["/app/settings/integrationer", "/app/indstillinger?ark=integrationer"],
  ["/app/voices", "/app/indstillinger?ark=stemmer"],
  ["/app/voices/own", "/app/indstillinger/stemmer/egen"],
  ["/app/help", "/app/hjaelp"],
  // M06 in the requirement matrix is /admin/support; the operator admin lives under /app/operator/admin.
  ["/admin/support", "/app/operator/admin/support"],
  ["/app/operator/support", "/app/operator/admin/support"],
  ["/app/setup/readiness", "/app/setup"],
  ["/app/setup/launch", "/app/setup"],
  ["/onboarding/:path*", "/opsaetning/1"],
  ["/app/not-yet", "/app/hjaelp"],
];

/** Baseline security headers on every page (audit 2026-11-12, F-AUD26-01): no page of dialogbot.app may be framed by
 *  another site (clickjacking of «Godkend opkald», «Gå live», checkout), browsers must not sniff types, and full URLs
 *  (tokens in /invite, /verify-email, /password) never leak to other sites through Referer. The embeddable webchat
 *  is served by the API origin (PUBLIC_BASE_URL/api/v1/public/webchat/{key}/frame), not by this app; the BFF's /api/*
 *  route handlers are left out anyway, so a proxied API answer keeps the API's own headers. */
const FRAME_CSP = { key: "Content-Security-Policy", value: "frame-ancestors 'self'" };
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
];

const nextConfig: NextConfig = {
  env: { APP_VERSION: `v${version}`, APP_COMMIT: commit },
  async headers() {
    // /privat/tp-verify sets its own, stricter CSP («sandbox allow-scripts; frame-ancestors 'self'», #205); a config
    // header would replace it (F-VER26-01), so the page-wide frame-ancestors CSP skips exactly that route.
    return [
      { source: "/((?!api/).*)", headers: SECURITY_HEADERS },
      { source: "/((?!api/|privat/tp-verify).*)", headers: [FRAME_CSP] },
    ];
  },
  async rewrites() {
    // Static, password-protected pages kept in web/public/<slug>/index.html (see docs/site-pages.md).
    return [{ source: "/gastrohall", destination: "/gastrohall/index.html" }];
  },
  async redirects() {
    return [
      // HeyCatch short links: one letter or digit, e.g. /x. The query carries the channel attribution. No real
      // single-character route exists (/a/[slug] is a longer path).
      { source: "/:l([a-z0-9])", destination: "/?utm_source=heycatch&utm_campaign=:l", permanent: false },
      // Back from the calendar provider's consent screen: while the person is in trin 2, the integrations page hands them back to it.
      { source: "/app/settings/integrationer", has: [{ type: "cookie" as const, key: "db_setup_return" }], destination: "/opsaetning/kalender", permanent: false },
      // The quiz-funnels: the ad/sitemap URL is the funnel itself; step 1 is where it starts. The query (b=, h=, utm_*)
      // is carried over automatically.
      { source: "/start", destination: "/start/1", permanent: false },
      { source: "/privat/start", destination: "/privat/start/1", permanent: false },
      ...MOVED.map(([source, destination]) => ({ source, destination, permanent: true })),
    ];
  },
};

export default nextConfig;
