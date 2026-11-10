import { expect, test } from "@playwright/test";
import { closeAll, CSRF, EVID, visitor, widgetWorkspace, type Widget } from "./d-helpers";

/* W02 – chat: «Greeting, language, typing, answer, follow-up questions, source uncertainty, human fallback and
 * completion.» AI_PROVIDER=fake answers «[fake] svar på: <spørgsmål>». */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W02 · hilsen, «Skriver…», svar, opfølgning med historik, AI-mærkning og reload af rammen bevarer samtalen", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const ws = await (await page.request.get(`/api/backend/workspaces/${w.wsId}`)).json();
  const { v, chat, close } = await visitor(browser, page);
  // greeting: the default one names the business
  await expect(chat.locator("li.msg.assistant").first()).toContainText(ws.name);
  // source uncertainty / honesty: the visitor is told it is an AI answering from approved information
  await expect(chat.locator("header")).toContainText("AI · svarer ud fra virksomhedens godkendte oplysninger");
  await expect(chat.getByText("Du skriver med en AI-assistent. Svar kan være ufuldstændige")).toBeVisible();
  // typing: hold the reply back and see «Skriver…» while waiting; Send is disabled (no double send)
  let release!: () => void;
  const gate = new Promise<void>((r) => { release = r; });
  await v.context().route("**/conversations/*/messages", async (route) => {
    if (route.request().method() === "POST") await gate;
    await route.fallback();
  });
  await chat.locator("textarea").fill("Hvad koster gulvafslibning?");
  await chat.locator("textarea").press("Enter");
  await expect(chat.locator("li.msg.typing")).toHaveText("Skriver…");
  await expect(chat.locator("form:not(.contact):not(.book) button[type=submit]")).toBeDisabled();
  release();
  await expect(chat.getByText("[fake] svar på: Hvad koster gulvafslibning?")).toBeVisible();
  await expect(chat.locator("li.msg.typing")).toHaveCount(0);
  // follow-up question in the same conversation
  await chat.locator("textarea").fill("Og hvor lang tid tager det?");
  await chat.locator("form:not(.contact):not(.book) button[type=submit]").click();
  await expect(chat.getByText("[fake] svar på: Og hvor lang tid tager det?")).toBeVisible();
  // the business sees one conversation with both questions and both answers
  const list = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/conversations`)).json();
  const items = list.items ?? list;
  expect(items.length).toBe(1);
  expect(items[0].visitor_message_count).toBe(2);
  // reload the customer's page: the conversation is still there (sessionStorage in the frame)
  await v.reload();
  await v.getByRole("button", { name: "Åbn chat" }).click();
  await expect(chat.getByText("[fake] svar på: Og hvor lang tid tager det?")).toBeVisible();
  await expect(chat.locator("li.msg.visitor")).toHaveCount(2);
  await v.screenshot({ path: `${EVID("W02")}/${info.project.name}-samtale.png` });
  await close();
});

test("W02 · menneskelig overtagelse: medarbejderens svar når frem i widgetten, og assistenten tier", async ({ page, browser }, info) => {
  test.setTimeout(120_000);
  w = await widgetWorkspace(page, info);
  const { v, chat, close } = await visitor(browser, page);
  await chat.locator("textarea").fill("Kan jeg tale med en person?");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("[fake] svar på: Kan jeg tale med en person?")).toBeVisible();
  const items = (await (await page.request.get(`/api/backend/workspaces/${w.wsId}/conversations`)).json()).items;
  const r = await page.request.post(`/api/backend/workspaces/${w.wsId}/conversations/${items[0].id}/reply`, { headers: CSRF, data: { text: "Hej, det er Mads fra Fjord Gulv." } });
  expect(r.status()).toBe(201);
  // polling every 5 s: the staff answer arrives, labelled as a colleague
  await expect(chat.locator("li.msg.staff")).toHaveText("Hej, det er Mads fra Fjord Gulv.", { timeout: 15_000 });
  await expect(chat.locator("li.msg.staff")).toHaveAttribute("data-label", "Medarbejder");
  await chat.locator("textarea").fill("Super, tak");
  await chat.locator("textarea").press("Enter");
  await expect(chat.getByText("En medarbejder svarer dig her i chatten.")).toBeVisible();
  await expect(chat.getByText("[fake] svar på: Super, tak")).toHaveCount(0);
  await v.screenshot({ path: `${EVID("W02")}/${info.project.name}-medarbejder.png` });
  await close();
});

test("W02 · sprog: arbejdsrum med engelsk slået til – en engelsk besøgende får widgetten på engelsk", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  const langs = await (await page.request.get(`/api/backend/workspaces/${w.wsId}/languages`)).json();
  const r = await page.request.put(`/api/backend/workspaces/${w.wsId}/languages`, { headers: CSRF, data: { interface_language: langs.interface_language, default_conversation_language: "da", report_language: langs.report_language, enabled_conversation_languages: ["da", "en"], expected_version: langs.version } });
  expect(r.ok(), await r.text()).toBeTruthy();
  const { newVisitorContext, SITE } = await import("./d-helpers");
  const ctx = await newVisitorContext(browser, page);
  await ctx.setExtraHTTPHeaders({ "accept-language": "en-GB,en;q=0.9" });
  const v = await ctx.newPage();
  await v.goto(`${SITE}/`);
  await v.getByRole("button", { name: /Åbn chat|Open chat/ }).click();
  const chat = v.frameLocator('iframe[title^="Chat"]');
  await expect(chat.locator("textarea")).toBeVisible();
  await v.screenshot({ path: `${EVID("W02")}/${info.project.name}-engelsk-besoegende.png` });
  // the chrome (header, notice, buttons, placeholder) follows an enabled language the visitor reads
  await expect(chat.locator("textarea")).not.toHaveAttribute("placeholder", "Skriv din besked…");
  await expect(chat.getByRole("button", { name: "Bliv kontaktet af en medarbejder" })).toHaveCount(0);
  await ctx.close();
});
