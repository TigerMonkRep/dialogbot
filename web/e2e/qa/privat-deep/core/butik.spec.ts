import { readFileSync } from "node:fs";
import { expect, test } from "@playwright/test";
import { API, CSRF, noHorizontalScroll, shot, stackUp, trial, user } from "./pk";

/** PC-SHOP-01/02/03/05/10 – Butikken: hvert ikon → «Hvad den gør» → egen installér-flow; ukendte nøgler; gammel URL;
 *  statisk web-katalog = backend-katalog; Ring for mig fra → afhængige går fra, Fortryd slår dem til igen. */
test.beforeEach(async ({ request }) => { test.skip(!(await stackUp(request)), "kræver Privat-stakken på :8400"); });

type Addon = { key: string; name: string; tagline: string; enabled: boolean; status: string; requires: string[] };

test("PC-SHOP-02: web-kataloget (addons-catalog.json) har samme nøgler og navne som backend", async ({ page }, info) => {
  await user(page, info, "shop02");
  const back = (await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[];
  const web = JSON.parse(readFileSync("src/lib/privat/addons-catalog.json", "utf8")) as unknown;
  const list = (Array.isArray(web) ? web : Object.values(web as Record<string, unknown>)) as { key: string; name?: string }[];
  const webKeys = list.map((x) => x.key).sort();
  expect(webKeys, "nye apps i backend skal også i addons-catalog.json").toEqual(back.map((a) => a.key).sort());
  for (const a of back) {
    const w = list.find((x) => x.key === a.key);
    if (w?.name) expect(w.name, a.key).toBe(a.name);
  }
});

test("PC-SHOP-01: hvert ikon åbner «Hvad den gør» og sin egen installér-knap", async ({ page }, info) => {
  test.setTimeout(240_000);
  await user(page, info, "shop01");
  await trial(page);
  const cat = (await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[];
  expect(cat).toHaveLength(21);
  await page.goto("/privat/butik");
  await expect(page.getByRole("heading", { name: "Butikken" }).first()).toBeVisible();
  await noHorizontalScroll(page);
  await shot(page, info, "PC-SHOP-01", "butik");
  for (const a of cat) {
    await page.goto(`/privat/butik/${a.key}`);
    await expect(page.getByText(a.name).first(), a.key).toBeVisible();
    // Ikke installeret: butikssiden med «Hvad den gør». Installeret: appens egen side (Mine apps) med «Slå fra».
    if (!a.enabled) await expect(page.getByText("Hvad den gør").first(), a.key).toBeVisible();
    const action = a.status === "coming_soon" ? page.getByText(/Kommer snart|Giv mig besked/).first()
      : a.enabled ? page.getByRole("button", { name: /Slå fra|Åbn/ }).or(page.getByRole("link", { name: /Åbn/ })).first()
      : page.getByRole("button", { name: /Installér|Slå .*til/ }).first();
    await expect(action, `${a.key}: egen installér-/åbn-handling`).toBeVisible();
    await noHorizontalScroll(page);
  }
  await page.goto("/privat/butik/madplan");
  await shot(page, info, "PC-SHOP-01", "madplan-detalje");
});

test("PC-SHOP-03/10: ukendt nøgle viser venlig tilstand; /privat/tilfoejelser → /privat/butik", async ({ page }, info) => {
  await user(page, info, "shop03");
  for (const k of ["findes-ikke", "MADPLAN", "mad%20plan"]) {
    const errors: string[] = [];
    page.on("pageerror", (e) => errors.push(e.message));
    const r = await page.goto(`/privat/butik/${k}`);
    expect(r?.status() ?? 200, k).toBeLessThan(500);
    await expect(page.getByRole("link", { name: /Butikken|Tilbage/ }).first(), `${k}: tilbage-link`).toBeVisible();
    expect(errors, k).toEqual([]);
  }
  await shot(page, info, "PC-SHOP-03", "ukendt-app");
  const r = await page.request.get("/privat/tilfoejelser", { maxRedirects: 0 });
  expect(r.status()).toBe(308);
  expect(r.headers()["location"]).toMatch(/\/privat\/butik$/);
  expect((await page.request.post(`/api/backend/privat/addons/findes-ikke/enable`, { headers: CSRF })).status()).toBe(404);
});

test("PC-SHOP-05: Ring for mig fra → afhængige apps fra; Fortryd slår alle til igen", async ({ page }, info) => {
  await user(page, info, "shop05");
  await trial(page);
  const deps = ["bil-og-syn", "laege-og-tandlaege", "abonnementer", "haandvaerker", "kaeledyr"];
  for (const k of deps) expect((await page.request.post(`/api/backend/privat/addons/${k}/enable`, { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/privat/butik/ring-for-mig");
  await page.getByRole("button", { name: /Slå fra/ }).first().click();
  const sheet = page.getByRole("dialog");
  await expect(sheet).toBeVisible();
  await shot(page, info, "PC-SHOP-05", "disable-sheet");
  const names = ((await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[]).filter((a) => deps.includes(a.key)).map((a) => a.name);
  for (const n of names) await expect(sheet.getByText(n, { exact: false }).first(), `DisableSheet nævner ${n}`).toBeVisible();
  await sheet.getByRole("button", { name: /Slå .* fra/ }).last().click();
  const st = async () => Object.fromEntries(((await (await page.request.get("/api/backend/privat/addons")).json()) as Addon[]).map((a) => [a.key, a.enabled]));
  await expect.poll(async () => (await st())["ring-for-mig"]).toBe(false);
  const s1 = await st();
  for (const k of deps) expect(s1[k], k).toBe(false);
  await page.getByRole("button", { name: "Fortryd" }).click();
  await expect.poll(async () => (await st())["ring-for-mig"]).toBe(true);
  await page.waitForTimeout(3000);
  const s2 = await st();
  await shot(page, info, "PC-SHOP-05", "after-undo");
  expect(Object.fromEntries(deps.map((k) => [k, s2[k]])), "Fortryd slår alle afhængige til igen").toEqual(Object.fromEntries(deps.map((k) => [k, true])));
});
