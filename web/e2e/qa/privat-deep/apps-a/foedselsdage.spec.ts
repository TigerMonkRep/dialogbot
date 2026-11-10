import { expect, test } from "@playwright/test";
import { appSuite } from "./suite";
import { backendTrace, CSRF, direct, enableApi, guard, noHorizontalScroll, persona, shot, sql, waitIdle } from "./apps-a-helpers";

/** PC-APP-FOEDSELSDAGE-01..05 (+ PC-APP-05 in the UI) against :3400 → :8400. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "foedselsdage", sc: "PC-APP-FOEDSELSDAGE", plan: true,
  say: "Mors fødselsdag er den 14. marts – mind mig om det en uge før",
  shows: /Mor/,
  read: "/privat/birthdays", holds: (b: any) => (b.items ?? []).length > 0,
  dbCount: (ws) => Number(sql(`select count(*) from private_birthdays where workspace_id='${ws}'`)[0]),
});

test.describe("foedselsdage – ret og slet", () => {
  guard();
  test("PC-APP-FOEDSELSDAGE-04 samme navn retter, «Fjern», emoji og lange navne uden layoutbrud; PC-APP-05 ugyldig dato", async ({ page }, info) => {
    const trace = backendTrace(page);
    const { ws } = await persona(page, info, "fd-04", "trial");
    await enableApi(page, "foedselsdage");
    for (const text of ["Mors fødselsdag er den 14. marts", "Mors fødselsdag er den 15. marts"]) {
      await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text } });
    }
    const long = "🎂 Mormor Åse-Margrethe Kristiansen-Østergaard fra Vestervig 👵🏻";
    expect((await page.request.post("/api/backend/privat/birthdays", { headers: CSRF, data: { name: long, date: "29. februar" } })).status()).toBe(200);
    const bad = await page.request.post("/api/backend/privat/birthdays", { headers: CSRF, data: { name: "X", date: "31. april" } });
    expect(bad.status()).toBe(422);
    const items = (await direct<{ items: { name: string; day: number; next_date: string }[] }>(page, "/privat/birthdays")).body.items;
    expect(items.filter((b) => b.name === "Mor").map((b) => b.day)).toEqual([15]);
    expect(items.find((b) => b.name === long)?.next_date).toBe("2027-02-28");
    await page.goto("/privat/apps/foedselsdage");
    await waitIdle(page);
    await expect(page.getByText(long).first()).toBeVisible();
    await noHorizontalScroll(page);
    await shot(page, info, "PC-APP-FOEDSELSDAGE-04", "long-emoji");
    await page.getByRole("button", { name: "Fjern: Mor", exact: true }).click();
    await expect(page.getByRole("button", { name: "Fjern: Mor", exact: true })).toHaveCount(0, { timeout: 10_000 });
    expect(Number(sql(`select count(*) from private_birthdays where workspace_id='${ws}' and name='Mor'`)[0])).toBe(0);
    trace.assertReal();
  });
});
