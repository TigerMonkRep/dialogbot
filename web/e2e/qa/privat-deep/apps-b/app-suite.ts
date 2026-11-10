import { expect, test, type Page } from "@playwright/test";
import { needsPrivatStack } from "../../privat/pq-helpers";
import {
  addon, api, assertAbout, disableViaSheet, enableViaSheet, enabledRows, gotoPrivat, noHorizontalScroll, openFromShop,
  pbUser, shot, type Persona,
} from "./pb-helpers";

/** One app, scenarios PC-APP-<APP>-01..05, at 390 px (mobil-390) and 1440 px (desktop-1440). */
export type AppCfg = {
  key: string;
  sid: string;                         // PC-APP-<APP>
  plans: "free" | "all" | "plus";      // included_in: [] | basis+plus+familie | plus+familie
  /** 03: the chat sentence the (fake) assistant understands, and how the data is proven afterwards (API/DB). */
  seed?: string;
  proveSeed?: (page: Page, ws: string, email: string) => Promise<void>;
  /** 03: what the app's settings panel on /privat/apps/<key> shows after the seed (null: the app has no panel). */
  panelText?: string | RegExp | null;
  /** 04: remove one thing through the UI and prove it is gone (API). */
  removeViaUi?: (page: Page, ws: string, email: string) => Promise<void>;
  /** 05: a GET that needs the app (403 addon_disabled when it is off). */
  probe?: string;
  /** false: the app has no endpoint of its own (its things are tasks) – no 403 to prove. */
  probeGated?: boolean;
  deletable: boolean;
};

const priceLine: Record<Persona, RegExp> = {
  none: /Med i Plus og Familie|Prøv gratis|Start 14 dage/i, basis: /Vælg plan|Med i Plus og Familie/i,
  expired: /Vælg plan|Med i Plus og Familie/i, trial: /prøveperiode/i, familie: /Med i Familie/i,
};

export function appSuite(c: AppCfg) {
  test.describe(`${c.key} (PB)`, () => {
    test.beforeEach(async ({ request }) => { test.skip(!(await needsPrivatStack(request)), "kræver Privat-stakken (:8400)"); });

    test(`${c.sid}-01 Butik → ikon → «Hvad den gør» matcher API og prislinje pr. persona`, async ({ page }, info) => {
      for (const persona of ["trial", "none"] as Persona[]) {
        await pbUser(page, info, `${c.key}-01-${persona}`, persona);
        const a = await addon(page, c.key);
        const where = await openFromShop(page, c.key);
        if (where === "app") {
          // F-PB-04: a default-on app's icon opens its app page, which has no «Hvad den gør»
          await expect.soft(page.getByText(a.what, { exact: true }), "F-PB-04 «Hvad den gør» for en app, der er slået til").toBeVisible({ timeout: 5_000 });
          await shot(page, info, `${c.sid}-01`, `app-page-${persona}`);
          await page.context().clearCookies();
          continue;
        }
        await assertAbout(page, a);
        await noHorizontalScroll(page);
        if (c.plans === "free") await expect(page.getByText(/Gratis/).first()).toBeVisible();
        else if (persona === "trial") await expect(page.getByText(priceLine.trial).locator("visible=true").first()).toBeVisible();
        else await expect(page.getByTestId("needs-plan")).toBeVisible();
        await shot(page, info, `${c.sid}-01`, `about-${persona}`);
        await page.context().clearCookies();
      }
    });

    test(`${c.sid}-02 Installér pr. plan: uden plan / Basis / udløbet → plan-ark; prøve → én række, Trin 1 af N, reload`, async ({ page }, info) => {
      for (const persona of ["none", "basis", "expired"] as Persona[]) {
        const { ws } = await pbUser(page, info, `${c.key}-02-${persona}`, persona);
        const covered = c.plans === "free" || (c.plans === "all" && persona === "basis");
        const r = await api(page, "POST", `/addons/${c.key}/enable`);
        if (covered) { expect(r.status()).toBe(200); await page.context().clearCookies(); continue; }
        expect(r.status(), await r.text()).toBe(409);
        expect((await r.json()).code).toBe("needs_plan");
        await api(page, "POST", `/addons/${c.key}/disable`); // expired keeps defaults on – take it off to see the shop
        await gotoPrivat(page, `/privat/butik/${c.key}`);
        await page.getByTestId("needs-plan").click();
        const radios = page.getByRole("dialog").getByRole("radio");
        const names = (await radios.allInnerTexts()).map((x) => x.split("\n")[0].trim());
        expect(names.some((n) => n.startsWith("Plus"))).toBeTruthy();
        expect(names.some((n) => n.startsWith("Familie"))).toBeTruthy();
        expect(names.some((n) => n.startsWith("Basis")), `Basis i plan-arket (${persona})`).toBe(c.plans === "all");
        await shot(page, info, `${c.sid}-02`, `plansheet-${persona}`);
        expect(enabledRows(ws, c.key)).toBe(0);
        await page.context().clearCookies();
      }
      const { ws } = await pbUser(page, info, `${c.key}-02-trial`, "trial");
      const wasOn = (await addon(page, c.key)).enabled;
      await api(page, "POST", `/addons/${c.key}/disable`);
      await gotoPrivat(page, wasOn ? `/privat/apps/${c.key}` : `/privat/butik/${c.key}`); // switched off with data kept → its kept page
      const a = await addon(page, c.key);
      if (wasOn) { // kept page: «Slå til igen» → consent → (F-PB-03: the confirmation unmounts) → the app page
        await page.getByTestId("enable-again").click();
        await page.getByTestId("enable-confirm").dblclick();
        await expect(page.getByTestId("app-page")).toBeVisible({ timeout: 15_000 });
      } else await enableViaSheet(page, a);
      expect(enabledRows(ws, c.key), "dobbeltklik → én række").toBe(1);
      await shot(page, info, `${c.sid}-02`, "enabled-sheet");
      await page.reload();
      await expect(page).toHaveURL(new RegExp(`/privat/apps/${c.key}$`), { timeout: 15_000 });
      await expect(page.getByTestId("app-page")).toBeVisible();
      expect(enabledRows(ws, c.key)).toBe(1);
    });

    test(`${c.sid}-03 Første brug: Trin 1, eksempel-chip, «Spørg Peter» → kerneflow via chat → data i API/DB`, async ({ page }, info) => {
      const { ws, email } = await pbUser(page, info, `${c.key}-03`, "trial");
      await api(page, "POST", `/addons/${c.key}/disable`);
      await api(page, "POST", `/addons/${c.key}/enable`);
      const a = await addon(page, c.key);
      await gotoPrivat(page, `/privat/apps/${c.key}`);
      await expect(page.getByTestId("app-page")).toBeVisible();
      if ((a.steps ?? []).length && a.setup.done < a.setup.total) await expect(page.getByTestId("app-setup")).toContainText(`Trin ${a.setup.done + 1} af ${a.steps.length}`);
      await expect(page.getByRole("button", { name: "Spørg Peter" }).first()).toBeVisible();
      await noHorizontalScroll(page);
      await shot(page, info, `${c.sid}-03`, "empty");
      await page.getByRole("button", { name: "Spørg Peter" }).first().click(); // puts the app's example in the composer
      await expect(page.locator("#privat-ask")).toHaveValue(String(a.example).replace(/^«|»$/g, ""));
      if (c.proveSeed) await c.proveSeed(page, ws, email);
      if (c.panelText) {
        await gotoPrivat(page, `/privat/apps/${c.key}`);
        await expect(page.locator("section[aria-labelledby=settings-h]")).toContainText(c.panelText);
        await noHorizontalScroll(page);
        await shot(page, info, `${c.sid}-03`, "after");
      }
    });

    test(`${c.sid}-04 Ret og slet via UI; ukendt id; lange tekster og emoji uden layoutbrud`, async ({ page }, info) => {
      test.skip(!c.removeViaUi, "appen har ingen ret/slet-flade (se notes-PB)");
      const { ws, email } = await pbUser(page, info, `${c.key}-04`, "trial");
      await api(page, "POST", `/addons/${c.key}/enable`);
      await c.removeViaUi!(page, ws, email);
      await noHorizontalScroll(page);
      await shot(page, info, `${c.sid}-04`, "after-remove");
    });

    test(`${c.sid}-05 Slå fra → data gemt → 403 → slå til igen («enabledKept») → evt. «Slet data»`, async ({ page }, info) => {
      test.skip(!c.probe, "kommer snart");
      test.setTimeout(180_000);
      const { ws } = await pbUser(page, info, `${c.key}-05`, "trial");
      await api(page, "POST", `/addons/${c.key}/enable`);
      if (c.seed) await api(page, "POST", "/messages", { text: c.seed });
      const before = await (await api(page, "GET", c.probe!)).json();
      await disableViaSheet(page, c.key);
      await shot(page, info, `${c.sid}-05`, "toast");
      const a = await addon(page, c.key);
      expect(a.enabled).toBe(false);
      expect(a.disabled_at).toBeTruthy();
      if (c.probeGated !== false) {
        const off = await api(page, "GET", c.probe!);
        expect(off.status()).toBe(403);
        expect((await off.json()).code).toBe("addon_disabled");
      }
      await gotoPrivat(page, `/privat/apps/${c.key}`);
      await expect(page.getByTestId("app-kept")).toBeVisible();
      await expect(page.getByText("Dine data er gemt")).toBeVisible();
      await expect(page.getByRole("button", { name: "Slet data" })).toHaveCount(c.deletable ? 1 : 0);
      await shot(page, info, `${c.sid}-05`, "kept");
      await page.getByTestId("enable-again").click();
      await page.getByTestId("enable-confirm").click();
      // F-PB-03: the «slået til igen» sheet unmounts when the page flips to the enabled view – soft, so the rest runs
      await expect.soft(page.getByText("Alt, den havde gemt, er her igen."), "F-PB-03 enabledKept").toBeVisible({ timeout: 5_000 });
      await expect(page.getByTestId("app-page")).toBeVisible();
      if (c.probeGated !== false) expect(await (await api(page, "GET", c.probe!)).json()).toEqual(before);
      expect(enabledRows(ws, c.key)).toBe(1);
      if (!c.deletable) return;
      await disableViaSheet(page, c.key);
      await gotoPrivat(page, `/privat/apps/${c.key}`);
      await page.getByRole("button", { name: "Slet data" }).click();
      const del = page.waitForResponse((r) => r.url().includes(`/addons/${c.key}/data`) && r.request().method() === "DELETE");
      await page.getByRole("button", { name: "Ja, slet" }).click();
      const d = await del;
      expect(d.status()).toBe(200);
      expect((await d.json()).deleted).toBeGreaterThan(0);
      await expect(page).toHaveURL(/\/privat\/butik$/);
      await api(page, "POST", `/addons/${c.key}/enable`);
      expect((await addon(page, c.key)).setup.done).toBe(0);
    });
  });
}
