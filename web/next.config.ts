import type { NextConfig } from "next";
import { readFileSync } from "node:fs";

// Shown in the app footer: the release version from package.json plus the short commit Vercel built.
const { version } = JSON.parse(readFileSync(new URL("./package.json", import.meta.url), "utf8")) as { version: string };
const commit = (process.env.VERCEL_GIT_COMMIT_SHA ?? "").slice(0, 7);

/** Content-Security-Policy, delivered as Report-Only first so nothing breaks while we watch the browser console for
 *  violations. Everything the site loads is same-origin today: fonts and the icon subset are self-hosted, the backend is
 *  reached through /api/backend, voice samples and recordings are same-origin audio, and Stripe is a redirect to its
 *  hosted checkout (no script on our pages). 'unsafe-inline' is required by Next.js' inline hydration scripts and
 *  Tailwind's inline styles until a nonce is wired through. Switch the header name to Content-Security-Policy once the
 *  report-only run has been quiet. */
const CSP = [
  "default-src 'self'",
  "script-src 'self' 'unsafe-inline'",
  "style-src 'self' 'unsafe-inline'",
  "img-src 'self' data: blob:",
  "font-src 'self'",
  "connect-src 'self'",
  "media-src 'self' blob:",
  "frame-ancestors 'none'",
  "form-action 'self'",
  "base-uri 'self'",
  "object-src 'none'",
].join("; ");

/** Security headers for every route. Cache-Control for /app, /onboarding and /api stays in vercel.json. The microphone is
 *  allowed because the app records the owner's own voice (voices/own); camera and geolocation are never used. */
const SECURITY_HEADERS = [
  { key: "Strict-Transport-Security", value: "max-age=63072000; includeSubDomains" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), geolocation=(), microphone=(self), payment=()" },
  { key: "Content-Security-Policy-Report-Only", value: CSP },
];

const nextConfig: NextConfig = {
  env: { APP_VERSION: `v${version}`, APP_COMMIT: commit },
  async headers() {
    return [{ source: "/(.*)", headers: SECURITY_HEADERS }];
  },
};

export default nextConfig;
