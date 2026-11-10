import { expect, test } from "@playwright/test";
import { addon, api, chat, gotoPrivat, noHorizontalScroll, openFromShop, pbUser, shot, sql, type Persona } from "./pb-helpers";
import { needsPrivatStack } from "../../privat/pq-helpers";

/** pakker (PC-APP-PAKKER-01..05) is «Kommer snart» in the QA stack (no provider key). Proven here: it SAYS so, nothing can
 *  be switched on, nothing pretends to work (no tracking, no invented prices), and «Giv mig besked» is remembered. */
const KEY = "pakker";

test.describe(`${KEY} kommer snart (PB)`, () => {
  test.beforeEach(async ({ request }) => { test.skip(!(await needsPrivatStack(request)), "kræver Privat-stakken (:8400)"); });

  test("PC-APP-PAKKER-01 Butik: «Kommer snart»-mærke, «Hvad den gør», ingen Slå til og ingen prislinje", async ({ page }, info) => {
    await pbUser(page, info, `${KEY}-01`, "trial");
    const a = await addon(page, KEY);
    expect([a.status, a.enabled]).toEqual(["coming_soon", false]);
    await gotoPrivat(page, "/privat/butik");
    await expect(page.getByTestId(`app-row-${KEY}`)).toContainText("Kommer snart");
    await openFromShop(page, KEY);
    await expect(page.getByText(a.what, { exact: true })).toBeVisible();
    await expect(page.getByText("Appen er ikke klar endnu. Vi kan give dig besked, når den er.")).toBeVisible();
    await expect(page.getByTestId("enable-app")).toHaveCount(0);
    await expect(page.getByText(/prøveperiode · du kan slå den fra/)).toHaveCount(0);
    await noHorizontalScroll(page);
    await shot(page, info, "PC-APP-PAKKER-01", "soon");
  });

  test("PC-APP-PAKKER-02 Ingen persona kan slå den til (409 coming_soon); «Giv mig besked» huskes på kontoen", async ({ page }, info) => {
    for (const persona of ["none", "basis", "familie"] as Persona[]) {
      const { ws } = await pbUser(page, info, `${KEY}-02-${persona}`, persona);
      const r = await api(page, "POST", `/addons/${KEY}/enable`);
      expect(r.status()).toBe(409);
      expect((await r.json()).code).toBe("coming_soon");
      expect(sql(`select count(*) from private_addon_enabled where workspace_id='${ws}' and key='${KEY}'`)).toBe("0");
      await page.context().clearCookies();
    }
    await pbUser(page, info, `${KEY}-02-trial`, "trial");
    await gotoPrivat(page, `/privat/butik/${KEY}`);
    await page.getByTestId("notify-me").click();
    await expect(page.getByTestId("notify-me")).toContainText("Vi giver dig besked");
    await page.reload();
    await expect(page.getByTestId("notify-me")).toBeDisabled();
    expect((await addon(page, KEY)).notify_requested).toBe(true);
    await shot(page, info, "PC-APP-PAKKER-02", "notified");
  });

  test("PC-APP-PAKKER-03 Chat og app-side lover intet: ingen sporing, ingen opfundne priser; app-siden → butikken", async ({ page }, info) => {
    const { ws } = await pbUser(page, info, `${KEY}-03`, "trial");
    const out = await chat(page, "Følg pakken med nummer 00340434123456789012");
    const said = out.messages.filter((m) => m.role === "assistant").map((m) => m.text ?? "").join(" ");
    expect(said.replace("12.000 kr.", "")).not.toMatch(/følger nu|spor(er|es) nu|\d[\d.]*\s*kr\./i);
    expect(sql(`select count(*) from private_app_data where workspace_id='${ws}' and app_key='${KEY}'`)).toBe("0");
    await shot(page, info, "PC-APP-PAKKER-03", "chat");
    await gotoPrivat(page, `/privat/apps/${KEY}`);
    await expect(page).toHaveURL(new RegExp(`/privat/butik/${KEY}$`));
    await gotoPrivat(page, "/privat/pakker");
    await expect(page.getByText(/Kommer snart|ikke klar/i).first()).toBeVisible();
    await shot(page, info, "PC-APP-PAKKER-03", "own-route");
  });

  test("PC-APP-PAKKER-04/05 Endpoints er lukkede (403), og der er intet at slette", async ({ page }, info) => {
    await pbUser(page, info, `${KEY}-04`, "trial");
    const g = await api(page, "GET", "/parcels");
    expect(g.status()).toBe(403);
    expect((await g.json()).code).toBe("addon_disabled");
    const d = await api(page, "DELETE", `/addons/${KEY}/data`);
    expect([200, 409]).toContain(d.status());
    if (d.status() === 200) expect((await d.json()).deleted).toBe(0);
    expect((await api(page, "POST", `/addons/${KEY}/disable`)).status()).toBe(200);
    expect((await addon(page, KEY)).disabled_at, "intet «slået fra»-spor for en app, der aldrig var slået til").toBeFalsy();
  });
});
