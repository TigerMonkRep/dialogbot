import { expect, test } from "@playwright/test";

/* Journey audit Erhverv (F-JE-07): a German visitor (dlg_lang=de) signs up on /signup. The register call must carry the
 * visitor's language, or the verify mail – and every later account mail – is Danish.
 * Read-only against a shared stack: /api/backend/auth/register and /api/auth/login are intercepted and fulfilled here, so
 * nothing is written. /signup?next=/invite/… passes the preview gate (proxy.ts gateFor). */
const EVID = "../qa/evidence/A01-journey";

test("F-JE-07 · /signup sends interface_language for a non-Danish visitor", async ({ page, context, baseURL }, info) => {
  test.fail(!process.env.QA_RUNXFAIL, "F-JE-07: web/src/app/signup/page.tsx never sends interface_language → verify mail is always Danish");
  await context.addCookies([{ name: "dlg_lang", value: "de", url: baseURL ?? "http://localhost:3000" }]);
  let body: Record<string, unknown> | null = null;
  await page.route("**/api/backend/auth/register", async (r) => {
    body = r.request().postDataJSON();
    await r.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({ id: "x", email: "de@fjordgulv.example", display_name: "Mads Jensen", email_verified: false, signup_intent: "reception", interface_language: "da", created_at: new Date().toISOString() }) });
  });
  await page.route("**/api/auth/login", (r) => r.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ user: {} }) }));
  await page.route("**/invite/**", (r) => r.fulfill({ status: 200, contentType: "text/html", body: "<html><body>stop</body></html>" }));
  await page.goto("/signup?next=%2Finvite%2Fqa-journey");
  await expect(page.locator("html")).toHaveAttribute("lang", "de"); // the page itself is German
  await page.locator('input[autocomplete="name"]').fill("Mads Jensen");
  await page.locator('input[type="email"]').fill("de@fjordgulv.example");
  await page.locator('input[type="password"]').first().fill("CorrectHorse!42");
  await page.screenshot({ path: `${EVID}/${info.project.name}-signup-de.png`, fullPage: true });
  await page.locator('button[type="submit"]').click();
  await expect.poll(() => body).not.toBeNull();
  expect(body!["interface_language"]).toBe("de");
});
