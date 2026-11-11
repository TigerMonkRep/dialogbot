import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* S10 – /app/settings/suppression: «Do-not-call entries, provenance, channel/purpose scope and approved correction
 * route.» (DB-015). Not built: no route, no workspace suppression list in the UI. */
test("S10 · spærrelisten findes (fravalg med kilde, kanal/formål og rettelsesvej)", async ({ page }, info) => {
  test.fail(true, "S10: not-implemented – spærreliste /app/settings/suppression (DB-015)");
  await freshOwner(page, info);
  const r = await page.request.get("/app/settings/suppression", { maxRedirects: 5 });
  test.info().annotations.push({ type: "status", description: `/app/settings/suppression → ${r.status()}` });
  expect(r.status()).toBe(200);
});
