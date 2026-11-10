import { expect, test } from "@playwright/test";
import { closeAll, CSRF, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W08 – widget failure/offline: «Connection failure, unavailable service, retry and business contact fallback.» */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W08 · serverfejl (500): dansk fejlbesked, Send virker igen, og næste forsøg lykkes", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  let fail = true;
  await v.context().route("**/conversations/*/messages", async (route) => {
    if (route.request().method() === "POST" && fail) return route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ code: "internal_error", message: "Der opstod en fejl. Prøv igen." }) });
    await route.fallback();
  });
  await chat.locator("textarea").fill("Hvad koster gulvafslibning?");
  await chat.locator("textarea").press("Enter");
  await expect(chat.locator("li.msg.system").last()).toHaveText("Der opstod en fejl. Prøv igen.");
  await expect(chat.locator("textarea")).toBeEditable();
  fail = false;
  await chat.locator("textarea").fill("Hvad koster gulvafslibning?");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("[fake] svar på: Hvad koster gulvafslibning?")).toBeVisible();
  await close();
});

test("W08 · forbindelsen er væk: den besøgende får en dansk besked og kan prøve igen uden at skrive beskeden forfra", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-08-W08: S2 new – Mister den besøgende forbindelsen, viser widgetten browserens rå fejl «Failed to fetch» …");
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await v.context().route("**/conversations**", (route) => route.abort("internetdisconnected"));
  await chat.locator("textarea").fill("Hvornår kan I komme forbi?");
  await chat.locator("textarea").press("Enter");
  const msg = chat.locator("li.msg.system").last();
  await expect(msg).toBeVisible();
  await v.screenshot({ path: `${EVID("W08")}/${info.project.name}-offline.png` });
  // frame.js:207 shows err.message – for a network error that is the browser's own «Failed to fetch» (English, technical)
  await expect(msg).not.toHaveText(/Failed to fetch|NetworkError|Load failed/);
  await expect(msg).toHaveText(/Prøv igen|forbindelse/i);
  // retry without retyping: the text is kept in the field or a «Prøv igen» action is offered
  const kept = await chat.locator("textarea").inputValue();
  const retry = await chat.getByRole("button", { name: /Prøv igen/ }).count();
  expect(kept === "Hvornår kan I komme forbi?" || retry > 0).toBeTruthy();
  await close();
});

test("W08 · chatten bliver utilgængelig midt i samtalen: besked + virksomhedens kontaktoplysninger som udvej", async ({ page, browser }, info) => {
  test.fail(true, "F-E2D-09-W08: S3 new – Når chatten bliver utilgængelig, siger widgetten «Kontakt virksomheden direkte» uden at sige …");
  w = await widgetWorkspace(page, info);
  // the business's phone number (canonical demo data) in the profile
  const prof = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/profile`)).json();
  const pr = await page.request.put(`/api/backend/workspaces/${w.wsId}/profile`, { headers: CSRF, data: { ...prof, phone: "+45 70 20 30 40", expected_version: prof.version } });
  expect(pr.ok(), await pr.text()).toBeTruthy();
  const { v, chat, close } = await visitor(browser, page);
  await chat.locator("textarea").fill("Hej");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("[fake] svar på: Hej")).toBeVisible();
  const wc = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/webchat`)).json();
  await page.request.put(`/api/backend/workspaces/${w.wsId}/webchat`, { headers: CSRF, data: { expected_version: wc.version, enabled: false, allowed_origins: wc.allowed_origins, greeting: "" } });
  await chat.locator("textarea").fill("Er I der stadig?");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("Chatten er ikke tilgængelig lige nu. Kontakt virksomheden direkte.")).toBeVisible();
  await expect(chat.locator("textarea")).toBeDisabled();
  await v.screenshot({ path: `${EVID("W08")}/${info.project.name}-utilgaengelig.png` });
  // «business contact fallback»: tell the visitor HOW to contact the business directly
  await expect(chat.locator("ol.log")).toContainText(/70 ?20 ?30 ?40/);
  await close();
});
