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
  ["/app/reception", "/app/indstillinger/hilsen"],
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
  ["/app/settings/profile", "/app/konto/profil"],
  ["/app/settings/agreement", "/app/konto/abonnement"],
  ["/app/billing", "/app/konto/fakturering"],
  ["/app/settings/activity", "/app/indstillinger/log"],
  ["/app/settings/business", "/opsaetning/1"],
  ["/app/settings/telephony", "/app/indstillinger/telefoni"],
  ["/app/settings/webchat", "/app/indstillinger/webchat"],
  ["/app/settings/integrationer", "/app/indstillinger/integrationer"],
  ["/app/voices", "/app/indstillinger/stemmer"],
  ["/app/voices/own", "/app/indstillinger/stemmer/egen"],
  ["/app/help", "/app/hjaelp"],
  ["/app/setup/readiness", "/app/setup"],
  ["/app/setup/launch", "/app/setup"],
  ["/onboarding/:path*", "/opsaetning/1"],
  ["/app/not-yet", "/app/hjaelp"],
];

const nextConfig: NextConfig = {
  env: { APP_VERSION: `v${version}`, APP_COMMIT: commit },
  async redirects() {
    return [
      // Back from the calendar provider's consent screen: while the person is in trin 2, the integrations page hands them back to it.
      { source: "/app/settings/integrationer", has: [{ type: "cookie" as const, key: "db_setup_return" }], destination: "/opsaetning/2", permanent: false },
      ...MOVED.map(([source, destination]) => ({ source, destination, permanent: true })),
    ];
  },
};

export default nextConfig;
