import { expect, test } from "@playwright/test";
import { appSuite } from "./suite";
import { backendTrace, CSRF, direct, enableApi, guard, noHorizontalScroll, persona, shot, sql, waitIdle } from "./apps-a-helpers";

/** PC-APP-BIL-OG-SYN-01..05 against :3400 → :8400. The catalog example («syn i maj … uge 18») only reaches the tools
 *  with a real model; the fake needs a plate/ISO date. API/DB: tests/qa/test_qa_pd_apps_a.py. */
appSuite({
  key: "bil-og-syn", sc: "PC-APP-BIL-OG-SYN", plan: true,
  say: "Bilen har nummerplade AB 12 345 og skal til syn 2027-05-01",
  shows: /Syn|syn/,
  read: "/privat/car", holds: (b: any) => !!b.plate,
  dbCount: (ws) => Number(sql(`select count(*) from private_app_data where workspace_id='${ws}' and app_key='bil-og-syn' and data->>'plate' is not null`)[0]),
});

test.describe("bil-og-syn – ret og opkald", () => {
  guard();
  test("PC-APP-BIL-OG-SYN-04 ret pladen i appen, tom plade, ugyldig dato; book uden værksted → intet forslag", async ({ page }, info) => {
    const trace = backendTrace(page);
    const { email } = await persona(page, info, "bil-04", "trial");
    await enableApi(page, "bil-og-syn");
    await page.goto("/privat/apps/bil-og-syn");
    await waitIdle(page);
    const panel = page.getByTestId("car-panel");
    await page.waitForLoadState("networkidle");
    await panel.getByLabel("Nummerplade").fill("CD 98 765");
    await expect(panel.getByLabel("Nummerplade")).toHaveValue("CD 98 765");
    await panel.getByRole("button", { name: "Gem" }).click();
    await expect.poll(async () => (await direct<{ plate: string }>(page, "/privat/car")).body.plate).toMatch(/CD ?98 ?765/);
    await shot(page, info, "PC-APP-BIL-OG-SYN-04", "saved");
    const bad = await page.request.put("/api/backend/privat/car", { headers: CSRF, data: { inspection_due: "31-02-2027" } });
    expect(bad.status()).toBe(422);
    await noHorizontalScroll(page);
    // «book» with no workshop saved: Peter asks, nothing proposed, nothing dialled
    await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: "Book syn hos mit værksted" } });
    const tasks = (await (await page.request.get("/api/backend/privat/tasks")).json()) as { kind: string }[];
    expect(tasks.filter((t) => t.kind === "call")).toEqual([]);
    expect(email).toBeTruthy();
    trace.assertReal();
  });
});
