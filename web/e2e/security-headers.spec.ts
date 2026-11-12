import { expect, test } from "@playwright/test";

/** Audit 2026-11-12, F-AUD26-01: every page answers with anti-framing, nosniff and a referrer policy. Before the fix
 *  dialogbot.app sent none of them (only HSTS from Vercel), so /login, /app and /privat could be framed by any site. */
const PAGES = ["/da", "/login", "/signup", "/privat", "/app", "/invite/x", "/verify-email"];

test.describe("security headers", () => {
  for (const path of PAGES) {
    test(`${path} cannot be framed by another site`, async ({ request }) => {
      test.skip(test.info().project.name !== "desktop-1440", "headers do not depend on the viewport");
      const r = await request.get(path, { maxRedirects: 0 });
      const h = r.headers();
      expect(h["content-security-policy"] ?? "").toContain("frame-ancestors 'self'");
      expect(h["x-frame-options"]).toBe("SAMEORIGIN");
      expect(h["x-content-type-options"]).toBe("nosniff");
      expect(h["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    });
  }
});
