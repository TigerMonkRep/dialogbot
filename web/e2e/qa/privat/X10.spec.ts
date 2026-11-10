import path from "node:path";
import { expect, test, type Browser, type TestInfo } from "@playwright/test";
import { CSRF, needsPrivatStack, privatUser, say, startTrial, waitIdle } from "./pq-helpers";
import { shot } from "./p2-helpers";

/** X10 (P1): Delte lister, invitationer fra brugerens EGET nummer, kontaktimport på iPhone (.vcf). Dialogbot sender
 *  aldrig invitationer selv: «Send som SMS» åbner brugerens egen Beskeder-app (sms:-link) med teksten udfyldt. The
 *  API side (no outbox row, no SMS, GSM-7 ≤ 160, the phone-number privacy probe): tests/qa/test_qa_privat_x10_x12.py. */

const IPHONE_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1";

test.beforeEach(async ({ request }) => {
  test.skip(!(await needsPrivatStack(request)), "kræver tests/qa/qa_privat_stack.py og next med API_BASE_URL til den");
});

async function iphone(browser: Browser, info: TestInfo) {
  const vp = info.project.name.includes("390") ? { width: 390, height: 844 } : { width: 1280, height: 900 };
  const ctx = await browser.newContext({ userAgent: IPHONE_UA, viewport: vp, hasTouch: true, locale: "da-DK", timezoneId: "Europe/Copenhagen" });
  return ctx.newPage();
}

test("iPhone: del en liste → «Send som SMS» åbner egen Beskeder-app med teksten; intet sendes af Dialogbot", async ({ browser }, info) => {
  const page = await iphone(browser, info);
  await privatUser(page, info, "x10-share", "Mette Hansen");
  await startTrial(page);
  const tid = (await say(page, "Lav en indkøbsliste med mælk og rugbrød"))!;
  await page.goto(`/privat/opgaver/${tid}`);
  await waitIdle(page);
  await page.getByRole("button", { name: /^Del/ }).first().click();
  await page.getByRole("button", { name: "Lav invitationslink" }).click();
  const sms = page.getByTestId("share-sms");
  await expect(sms).toBeVisible();
  const href = (await sms.getAttribute("href"))!;
  expect(href.startsWith("sms:?&body=")).toBe(true);      // iOS form, no recipient: the user picks them in Messages
  const body = decodeURIComponent(href.split("body=")[1]);
  const link = (await page.getByTestId("share-link").textContent())!.trim();
  expect(body).toContain(link);
  expect(link).toMatch(/\/i\/[A-Z2-9]{8}$/);
  expect(body).toMatch(/Mette$/);                          // signed with the user's own first name
  await expect(page.getByText("Dialogbot sender aldrig invitationer for dig")).toBeVisible();
  // F-P2-05-X10: the text the web composes uses «–» (not GSM-7) – the SMS goes out as UCS-2 (70 chars/segment) while
  // the counter promises 160. The API's own suggested_text avoids it.
  const nonGsm = [...body].filter((ch) => !/[A-Za-z0-9 @£$¥èéùìòÇØøÅåÆæßÉÄÖÑÜäöñüà!"#%&'()*+,\-./:;<=>?§¿_\n\r]/.test(ch));
  await shot(page, info, "X10", "share-sheet");
  expect(nonGsm, `tegn uden for GSM-7 i «${body}»`).toEqual([]);
  await page.context().close();
});

test("iPhone: Mine folk → importér .vcf fra Kontakter → vælg personer → gruppen gemmes med +45-numre", async ({ browser }, info) => {
  const page = await iphone(browser, info);
  await privatUser(page, info, "x10-vcf", "Mette Hansen");
  await startTrial(page);
  await page.goto("/privat/folk");
  await waitIdle(page);
  await page.getByRole("button", { name: "Ny gruppe" }).click();
  await page.getByLabel("Gruppens navn").fill("Familien");
  // On iPhone the .vcf import is offered (no Contact Picker), Android's picker is not
  await expect(page.getByTestId("vcf-import")).toBeVisible();
  await page.getByTestId("vcf-input").setInputFiles(path.join(__dirname, "fixtures", "iphone-contacts.vcf"));
  const picks = page.getByTestId("vcf-import").getByRole("checkbox");
  await expect(picks).toHaveCount(3); // the e-mail-only card is skipped
  await expect(page.getByTestId("vcf-import")).toContainText("Ole Berg");
  await expect(page.getByTestId("vcf-import")).toContainText("+45 20 11 22 33"); // mobile preferred over home
  await expect(page.getByTestId("vcf-import")).toContainText("Anne-Mette Sørensen");
  await expect(page.getByTestId("vcf-import")).toContainText("Ørum Åse"); // vCard 2.1 QUOTED-PRINTABLE N, given name first
  await shot(page, info, "X10", "vcf-pick");
  await picks.nth(0).check();
  await picks.nth(1).check();
  await page.getByRole("button", { name: /Tilføj 2 valgte/ }).click();
  await expect(page.getByTestId("group-members").locator("li")).toHaveCount(2);
  await page.locator("button:visible", { hasText: "Gem gruppen" }).first().click();
  await expect.poll(async () => (await (await page.request.get("/api/backend/privat/groups")).json()).length).toBe(1);
  const g = (await (await page.request.get("/api/backend/privat/groups")).json())[0];
  expect(g.members.map((m: { name: string; phone_e164: string }) => [m.name, m.phone_e164])).toEqual([
    ["Ole Berg", "+4520112233"], ["Anne-Mette Sørensen", "+4521112233"]]);
  await page.context().close();
});

test("del med gruppe én ad gangen: personlig tekst og nummer i sms:-linket, kø overlever skift til Beskeder", async ({ browser }, info) => {
  const page = await iphone(browser, info);
  await privatUser(page, info, "x10-queue", "Mette Hansen");
  await startTrial(page);
  const tid = (await say(page, "Lav en indkøbsliste med kaffe"))!;
  const r = await page.request.post("/api/backend/privat/groups", { headers: CSRF, data: { name: "Naboerne",
    members: [{ name: "Ole Berg", phone: "20112233" }, { name: "Anna Holm", phone: "21112233" }] } });
  expect(r.status()).toBe(201);
  await page.goto(`/privat/opgaver/${tid}`);
  await waitIdle(page);
  await page.getByRole("button", { name: /^Del/ }).first().click();
  await page.getByRole("radio", { name: /Naboerne/ }).check();
  await page.getByRole("button", { name: "En ad gangen" }).click();
  const next = page.getByTestId("queue-next");
  await expect(next).toBeVisible();
  const h1 = decodeURIComponent((await next.getAttribute("href"))!);
  expect(h1).toMatch(/^sms:\+4520112233\?&body=Hej Ole!/);
  await shot(page, info, "X10", "queue");
  // tapping opens Messages (we stop the navigation) and advances
  await page.route(/^sms:/, (route) => route.abort());
  await next.evaluate((a) => a.addEventListener("click", (e) => e.preventDefault(), { once: true }));
  await next.click();
  await expect(page.getByTestId("queue-next")).toHaveAttribute("href", /^sms:\+4521112233\?&body=Hej%20Anna!/);
  await page.reload();
  await waitIdle(page);
  const st = await (await page.request.get(`/api/backend/privat/tasks/${tid}/invite-status`)).json();
  expect(st.map((x: { status: string }) => x.status)).toEqual(["invited", "invited"]);
  await page.context().close();
});
