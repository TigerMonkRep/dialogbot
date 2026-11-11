import { expect, test } from "@playwright/test";
import { login, SEEDED } from "../../helpers";
import { evid, snap } from "./p1a-helpers";

/* QA X25 (e2e-erhverv A, wave 2): Ingen «Staging»-mærkat i logged-in UI (APP_ENV=prod-adfærd).
 * Source: web/src/components/shell.tsx:77 – the badge shows only when capabilities[0].environment !== "prod";
 * «Staging» only when it is "staging". Production's APP_ENV is prod (infra/render.yaml). On this stack APP_ENV=test,
 * so the badge must read «Udvikling» (never «Staging»), and it must follow the backend's environment exactly. The
 * prod half (APP_ENV=prod → environment "prod" → no badge) is tests/qa/test_qa_X25.py. */
const ID = "X25";
evid(ID);
const PAGES = ["/app", "/app/opkald", "/app/aftaler", "/app/kampagner", "/app/viden", "/app/ugen", "/app/indstillinger",
  "/app/indstillinger?ark=integrationer", "/app/konto", "/app/hjaelp"];

for (const who of ["owner", "staff", "reader"] as const) {
  test(`X25 · ${who}: ingen «Staging» på nogen app-side; mærkatet følger backendens miljø`, async ({ page }, info) => {
    await login(page, SEEDED[who]);
    const caps = await (await page.request.get("/api/backend/integrations/capabilities")).json();
    const env: string = caps.items[0].environment;
    expect(env).not.toBe("staging");
    for (const p of PAGES) {
      await page.goto(p);
      await page.waitForLoadState("networkidle");
      const body = await page.locator("body").innerText();
      expect(body, `${p} viser «Staging»`).not.toMatch(/\bstaging\b/i);
      expect(await page.title(), `${p} titel`).not.toMatch(/staging/i);
    }
    await page.goto("/app");
    const badge = page.locator("header span.uppercase", { hasText: /^(Udvikling|Staging)$/ });
    if ((page.viewportSize()?.width ?? 0) >= 1280) await expect(badge).toHaveText(env === "prod" ? [] : ["Udvikling"]);
    else await expect(badge).toBeHidden(); // hidden xl:inline-flex
    await snap(page, info, ID, `${who}-app`);
  });
}
