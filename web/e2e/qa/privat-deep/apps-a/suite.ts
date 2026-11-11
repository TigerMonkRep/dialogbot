import { expect, test, type Page } from "@playwright/test";
import {
  backendTrace, catalog, CSRF, direct, enableApi, guard, noHorizontalScroll, persona, sayInChat, shot, sql, strip, waitIdle,
  type Addon,
} from "./apps-a-helpers";

/** One app, the five PC-APP-<APP>-0x scenarios, in the browser (mobil-390 first, then desktop-1440). */
export type AppCfg = {
  key: string;
  sc: string;                 // scenario prefix, e.g. PC-APP-FEST
  plan: boolean;              // Plus/Familie app (else free)
  say: string;                // fake-model phrasing that puts something in the app
  shows: RegExp;              // what the app page shows afterwards
  read: string;               // the app's own read endpoint on :8400 (403 addon_disabled when off)
  holds: (body: any) => boolean;
  dbCount: (ws: string) => number;
  tasksTitle?: string;        // a list the app makes (its «Slet data» must take it too – F-PA-01)
  removable?: boolean;        // household card with «Fjern»
  skip?: Record<string, string>; // "03" → why this part cannot run here
};

const appData = (key: string) => (ws: string) =>
  Number(sql(`select count(*) from private_app_data where workspace_id='${ws}' and app_key='${key}'`)[0]);

export const household = (key: string) => ({ read: `/privat/apps/${key}/overview`, holds: (b: any) => (b.items ?? []).length > 0,
  dbCount: appData(key), removable: true });

export function appSuite(cfg: AppCfg) {
  test.describe(`${cfg.key}`, () => {
    guard();

    test(`${cfg.sc}-01 Butik → ikon → «Hvad den gør» med appens egne tekster og prislinje`, async ({ page }, info) => {
      const trace = backendTrace(page);
      await persona(page, info, `${cfg.key}-01`, "trial");
      await page.request.patch("/api/backend/privat/me/assistant", { headers: CSRF, data: { name: "Kim", pronoun: "hun" } });
      const a = (await catalog(page))[cfg.key];
      // Butikken lists the apps that are not on; an app that is on (Delte lister: on from sign-up) is under Mine apps
      await page.goto(a.enabled ? "/privat/apps" : "/privat/butik");
      await waitIdle(page);
      const row = page.locator(`[data-testid=app-row-${cfg.key}]:visible`).first();
      await expect(row).toBeVisible();
      if (a.enabled) { // a default app (Delte lister): the icon opens the app itself
        await row.click();
        await expect(page).toHaveURL(new RegExp(`/privat/apps/${cfg.key}$`));
        await page.goto(`/privat/butik/${cfg.key}`);
        await expect(page).toHaveURL(new RegExp(`/privat/apps/${cfg.key}$`), { timeout: 15_000 });
        trace.assertReal();
        return;
      }
      await row.click();
      await expect(page).toHaveURL(new RegExp(`/privat/butik/${cfg.key}$`));
      await waitIdle(page);
      await expect(page.getByRole("heading", { level: 1 })).toHaveText(a.name);
      await expect(page.getByText("Hvad den gør", { exact: true }).first()).toBeVisible();
      await expect(page.getByText(a.what.slice(0, 50)).first()).toBeVisible();
      expect(a.what + a.steps.join(" "), "assistentens navn i teksterne").not.toContain("Peter");
      // the example is not on the shop page (byggevejledning: less text) – it is on the app page (03)
      for (const s of a.steps) await expect(page.getByText(s.slice(0, 40)).first()).toBeVisible();
      await page.getByText("Den får lov til", { exact: true }).first().click();
      for (const p of a.permissions) await expect(page.getByText(p.slice(0, 40)).first()).toBeVisible();
      for (const n of a.needs) await expect(page.getByText(n.slice(0, 40)).first()).toBeVisible();
      const price = cfg.plan ? "Med i din Plus-prøveperiode" : "Gratis · du kan slå den fra";
      await expect(page.getByText(price).first()).toBeVisible();
      await expect(page.locator("[data-testid=enable-app]:visible").first()).toHaveText(`Slå ${a.name} til`);
      await noHorizontalScroll(page);
      await shot(page, info, `${cfg.sc}-01`, "shop-page");
      trace.assertReal();
    });

    test(`${cfg.sc}-02 installér: reload midt i arket, dobbelt-tryk, Trin 1 af N – og planvalg uden plan`, async ({ page }, info) => {
      const trace = backendTrace(page);
      const { ws } = await persona(page, info, `${cfg.key}-02`, "trial");
      if ((await catalog(page))[cfg.key].enabled) {   // default app: switch it off first, install from the kept page
        await page.request.post(`/api/backend/privat/addons/${cfg.key}/disable`, { headers: CSRF });
      }
      const start = async () => {
        const a = (await catalog(page))[cfg.key];
        await page.goto(a.disabled_at ? `/privat/apps/${cfg.key}` : `/privat/butik/${cfg.key}`);
        await waitIdle(page);
        await page.locator("[data-testid=enable-app]:visible, [data-testid=enable-again]:visible").first().click();
        await expect(page.getByTestId("enable-confirm")).toBeVisible();
        return a;
      };
      const a = await start();
      await expect(page.getByRole("dialog").getByText("Den får lov til").or(page.getByText("Den får lov til")).first()).toBeVisible();
      await shot(page, info, `${cfg.sc}-02`, "enable-sheet");
      await page.reload();                                             // reload in the middle of the sheet
      await waitIdle(page);
      expect((await catalog(page))[cfg.key].enabled, "reload slår ikke appen til").toBe(false);
      await expect(page.getByTestId("enable-confirm")).toHaveCount(0);
      await start();
      await page.getByTestId("enable-confirm").dblclick();             // a 60-year-old's double tap
      // from the kept page the page itself turns into the app page (the sheet goes with it)
      await expect(a.disabled_at ? page.getByTestId("app-page") : page.getByText(`${a.name} er slået til`)).toBeVisible({ timeout: 15_000 });
      const steps = a.steps.length;
      if (!a.disabled_at) {
        await expect(page.getByText(`Trin 1 af ${steps}`).first()).toBeVisible();
        await shot(page, info, `${cfg.sc}-02`, "enabled-sheet");
        await page.getByRole("button", { name: "Start trin 1" }).click();
        await expect(page).toHaveURL(new RegExp(`/privat/apps/${cfg.key}$`));
        await expect(page.getByTestId("app-setup")).toContainText(`Trin 1 af ${steps}`);
      }
      expect(Number(sql(`select count(*) from private_addon_enabled where workspace_id='${ws}' and key='${cfg.key}'`)[0])).toBe(1);
      trace.assertReal();

      // without a plan
      const p2 = await page.context().browser()!.newPage({ viewport: page.viewportSize()! });
      try {
        await persona(p2, info, `${cfg.key}-02b`, cfg.plan ? "basis" : "none");
        await p2.goto(`/privat/butik/${cfg.key}`);
        await waitIdle(p2);
        if (cfg.plan) {
          const r = await p2.request.post(`/api/backend/privat/addons/${cfg.key}/enable`, { headers: CSRF });
          expect(r.status()).toBe(409);
          expect((await r.json()).code).toBe("needs_plan");
          await expect(p2.getByText("Med i Plus og Familie.").first()).toBeVisible();
          await p2.locator("[data-testid=needs-plan]:visible").first().click();
          const radios = p2.getByRole("radiogroup").getByRole("radio");
          await expect(radios).toHaveCount(2);
          await expect(radios.nth(0)).toContainText("Plus");
          await expect(radios.nth(1)).toContainText("Familie");
          await shot(p2, info, `${cfg.sc}-02`, "plan-sheet-basis");
        } else if ((await catalog(p2))[cfg.key].enabled) {
          // a default app: on for an account without a plan from sign-up – nothing to install
          expect((await catalog(p2))[cfg.key].requires_plan).toBe(false);
        } else {
          await p2.locator("[data-testid=enable-app]:visible").first().click();
          await p2.getByTestId("enable-confirm").click();
          await expect(p2.getByText(`${a.name} er slået til`)).toBeVisible({ timeout: 15_000 });
          expect((await catalog(p2))[cfg.key].enabled).toBe(true);
        }
      } finally { await p2.close(); }
    });

    test(`${cfg.sc}-03 tom tilstand → «Spørg Peter» → kerneflow i samtalen → appen viser det (data på :8400 og i DB)`, async ({ page }, info) => {
      test.fixme(!!cfg.skip?.["03"], cfg.skip?.["03"] ?? "");
      const trace = backendTrace(page);
      const { ws } = await persona(page, info, `${cfg.key}-03`, "trial");
      const a0 = (await catalog(page))[cfg.key];
      if (!a0.enabled) await enableApi(page, cfg.key);
      else await page.request.put(`/api/backend/privat/addons/${cfg.key}/setup`, { headers: CSRF, data: { done: 0 } });
      const a = (await catalog(page))[cfg.key];
      expect(cfg.holds((await direct(page, cfg.read)).body), "tom ved start").toBe(false);
      await page.goto(`/privat/apps/${cfg.key}`);
      await waitIdle(page);
      await expect(page.getByTestId("app-setup")).toContainText(`Trin 1 af ${a.steps.length}`);
      // NB design-note 15: apps with a panel show the example only if their empty summary happens to quote it
      await shot(page, info, `${cfg.sc}-03`, "empty");
      await page.getByRole("button", { name: "Spørg Peter" }).first().click();
      await expect(page.locator("#privat-ask:visible").first()).toHaveValue(strip(a.example));
      await sayInChat(page, cfg.say);
      await shot(page, info, `${cfg.sc}-03`, "chat");
      const d = await direct(page, cfg.read);
      expect(d.status).toBe(200);
      expect(cfg.holds(d.body), `data på :8400 efter «${cfg.say}»: ${JSON.stringify(d.body).slice(0, 300)}`).toBe(true);
      expect(cfg.dbCount(ws), "række i databasen").toBeGreaterThan(0);
      await page.goto(`/privat/apps/${cfg.key}`);
      await waitIdle(page);
      await expect(page.getByText(cfg.shows).first()).toBeVisible({ timeout: 15_000 });
      await noHorizontalScroll(page);
      await shot(page, info, `${cfg.sc}-03`, "app-with-data");
      // nothing is ever dialled from an app flow
      const calls = await (await page.request.get(`${process.env.QA_PRIV_API ?? "http://localhost:8400"}/__qa/calls`)).json();
      expect((calls.dialled as { payload: { metadata: Record<string, string> } }[])
        .filter((c) => JSON.stringify(c).includes(ws))).toEqual([]);
      trace.assertReal();
    });

    if (cfg.removable) {
      test(`${cfg.sc}-04 «Fjern» på et punkt → væk i UI, API og DB; ukendt id → 404`, async ({ page }, info) => {
      test.fixme(!!cfg.skip?.["04"], cfg.skip?.["04"] ?? "");
        const trace = backendTrace(page);
        await persona(page, info, `${cfg.key}-04`, "trial");
        await enableApi(page, cfg.key);
        await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: cfg.say } });
        const before = (await direct<{ items: { id: string; text: string }[] }>(page, cfg.read)).body.items;
        expect(before.length).toBeGreaterThan(0);
        await page.goto(`/privat/apps/${cfg.key}`);
        await waitIdle(page);
        const card = page.getByTestId("household-panel").locator("div", { hasText: before[0].text.slice(0, 25) }).last();
        await card.getByRole("button", { name: "Fjern" }).click();
        await expect(page.getByTestId("household-panel").getByText(before[0].text, { exact: true })).toHaveCount(0, { timeout: 10_000 });
        const after = (await direct<{ items: { id: string }[] }>(page, cfg.read)).body.items;
        expect(after.map((i) => i.id)).not.toContain(before[0].id);
        const again = await page.request.delete(`/api/backend/privat/apps/${cfg.key}/items/${before[0].id}`, { headers: CSRF });
        expect(again.status()).toBe(404);
        await noHorizontalScroll(page);
        await shot(page, info, `${cfg.sc}-04`, "after-remove");
        trace.assertReal();
      });
    }

    test(`${cfg.sc}-05 slå fra → «Dine data er gemt» + 403 → slå til igen med data → slå fra → slet data`, async ({ page }, info) => {
      test.fixme(!!cfg.skip?.["05"], cfg.skip?.["05"] ?? "");
      const trace = backendTrace(page);
      const { ws } = await persona(page, info, `${cfg.key}-05`, "trial");
      if (!(await catalog(page))[cfg.key].enabled) await enableApi(page, cfg.key);
      await page.request.post("/api/backend/privat/messages", { headers: CSRF, data: { text: cfg.say } });
      expect(cfg.holds((await direct(page, cfg.read)).body)).toBe(true);
      const off = async () => {
        await page.goto(`/privat/apps/${cfg.key}`);
        await waitIdle(page);
        await page.locator("[data-testid=disable-app]:visible").first().click();
        await expect(page.getByText("Det bliver gemt")).toBeVisible();
        await page.getByTestId("disable-confirm").click();
        await expect(page).toHaveURL(/\/privat\/apps$/, { timeout: 15_000 });
        await expect(page.getByTestId("toast")).toContainText("Dine data er gemt");
      };
      await off();
      const a = (await catalog(page))[cfg.key];
      expect(a.enabled).toBe(false);
      expect(a.disabled_at).toBeTruthy();
      const blocked = await direct<{ code: string }>(page, cfg.read);
      expect([blocked.status, blocked.body.code]).toEqual([403, "addon_disabled"]);
      await page.goto(`/privat/apps/${cfg.key}`);
      await waitIdle(page);
      await expect(page.getByTestId("app-kept")).toContainText("Dine data er gemt");
      await shot(page, info, `${cfg.sc}-05`, "kept");
      await page.getByTestId("enable-again").click();
      await page.getByTestId("enable-confirm").click();
      await expect(page.getByText("Alt, den havde gemt, er her igen").or(page.getByTestId("app-page")).first()).toBeVisible({ timeout: 15_000 });
      expect(cfg.holds((await direct(page, cfg.read)).body), "data er tilbage").toBe(true);
      await page.goto(`/privat/apps/${cfg.key}`);
      await waitIdle(page);
      await expect(page.getByText(cfg.shows).first()).toBeVisible();

      await off();
      await page.goto(`/privat/apps/${cfg.key}`);
      await waitIdle(page);
      if (!a.data_deletable) {
        await expect(page.getByRole("button", { name: "Slet data" })).toHaveCount(0);
        trace.assertReal();
        return;
      }
      await page.getByRole("button", { name: "Slet data" }).click();
      await shot(page, info, `${cfg.sc}-05`, "delete-confirm");
      await page.getByRole("button", { name: "Ja, slet" }).click();
      await expect(page).toHaveURL(/\/privat\/butik$/, { timeout: 15_000 });
      expect(cfg.dbCount(ws), "rækkerne er væk").toBe(0);
      await enableApi(page, cfg.key);
      const back = (await catalog(page))[cfg.key];
      expect(back.setup.done).toBe(0);
      expect(cfg.holds((await direct(page, cfg.read)).body), "tom efter sletning").toBe(false);
      if (cfg.tasksTitle) {
        const left = sql(`select title from private_tasks where workspace_id='${ws}' and title=${"'" + cfg.tasksTitle + "'"} and status <> 'deleted'`);
        expect(left, `«Sletter alt, hvad appen har gemt» – listen «${cfg.tasksTitle}» (F-PA-01)`).toEqual([]);
      }
      trace.assertReal();
    });
  });
}

export async function openApp(page: Page, key: string) {
  await page.goto(`/privat/apps/${key}`);
  await waitIdle(page);
}
export type { Addon };
