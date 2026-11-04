import { readFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";
import { parseVcf } from "../src/lib/privat/vcard";
import { normalizeDk, parseNumbers, platformOf, smsHref } from "../src/lib/privat/sms";

/** Dialogbot Privat in fake mode (the dev/build server runs with NEXT_PUBLIC_PRIVAT_FAKE=1; all data is simulated in the
 *  browser). Run: NEXT_PUBLIC_PRIVAT_FAKE=1 next dev, then BASE_URL=… npx playwright test e2e/privat.spec.ts --project=desktop-1440
 *  Each journey runs at 375 and 1440 px. */

const IOS_UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1";
const ANDROID_UA = "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Mobile Safari/537.36";
const FIX = join(__dirname, "fixtures", "vcf");
if (process.env.PW_CHROMIUM) test.use({ launchOptions: { executablePath: process.env.PW_CHROMIUM } });

// ---------------------------------------------------------------- unit tests (no browser)

test.describe("enheder", () => {
  test("vCard: iPhone-eksport med 3 kontakter, foldede linjer, mobil foretrækkes", () => {
    const cs = parseVcf(readFileSync(join(FIX, "iphone-3.vcf"), "utf8"));
    expect(cs.map((c) => c.name)).toEqual(["Anna Hansen", "Peter Jensen", "Mor Ørsted"]);
    expect(cs[0].phone).toBe("+4521222324");
    expect(cs[0].phones).toEqual(["+4521222324", "+4586123456"]);
    expect(cs[1].phone).toBe("31323334");
  });
  test("vCard 2.1: QUOTED-PRINTABLE og bløde linjeskift", () => {
    const [c] = parseVcf(readFileSync(join(FIX, "android-21.vcf"), "utf8"));
    expect(c.name).toBe("Bjørn Søren");
    expect(c.phone).toBe("+4551525354");
  });
  test("vCard 4.0: tel:-URI og kort uden nummer springes over", () => {
    const cs = parseVcf(readFileSync(join(FIX, "v4.vcf"), "utf8"));
    expect(cs).toHaveLength(1);
    expect(cs[0]).toMatchObject({ name: "Line Holm", phone: "+4561626364" });
  });
  test("SMS-links: iOS og Android", () => {
    const body = "Hej! Se den her: dialogbot.app/i/K7Q2M9XA – Mette";
    const enc = encodeURIComponent(body);
    expect(smsHref(body, [], "ios")).toBe(`sms:?&body=${enc}`);
    expect(smsHref(body, [], "android")).toBe(`sms:?body=${enc}`);
    expect(smsHref(body, ["+45 12 34 56 78", "+4587654321"], "ios")).toBe(`sms:+4512345678,+4587654321?&body=${enc}`);
    expect(smsHref(body, ["+4512345678", "+4587654321"], "android")).toBe(`sms:+4512345678;+4587654321?body=${enc}`);
    expect(platformOf(IOS_UA)).toBe("ios");
    expect(platformOf(ANDROID_UA)).toBe("android");
  });
  test("numre normaliseres til +45", () => {
    expect(normalizeDk("12 34 56 78")).toBe("+4512345678");
    expect(normalizeDk("0045 12345678")).toBe("+4512345678");
    expect(parseNumbers("12345678, 87 65 43 21\n12345678; hej")).toEqual({ ok: ["+4512345678", "+4587654321"], bad: ["hej"] });
  });
});

// The browser journeys need a web build with NEXT_PUBLIC_PRIVAT_FAKE=1 (the «privat» job in e2e.yml); the main journeys
// job builds against the real API and skips them. The unit tests above always run.
const needsFake = () => test.skip(process.env.NEXT_PUBLIC_PRIVAT_FAKE !== "1", "kræver et web-build med NEXT_PUBLIC_PRIVAT_FAKE=1");

// ---------------------------------------------------------------- helpers

async function open(page: Page, path = "/privat/dag", { login = true } = {}) {
  if (login) await page.addInitScript(() => sessionStorage.setItem("dialogbot-privat-fake-login", "1"));
  // sms:/whatsapp links must not navigate away in the test browser; the app's own click handlers still run.
  await page.addInitScript(() => document.addEventListener("click", (e) => {
    const a = (e.target as HTMLElement | null)?.closest?.("a[href^='sms:'], a[href^='https://wa.me']");
    if (a) e.preventDefault();
  }, true));
  await page.goto(path);
  await expect(page.getByTestId("balance-chip")).toBeVisible();
  await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
}

/** The visible composer (Min dag on a phone, Samtale otherwise). */
async function say(page: Page, text: string) {
  const input = page.locator("#privat-ask-day:visible, #privat-ask:visible").first();
  await input.fill(text);
  await input.press("Enter");
  await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
}

/** «Hvor skal jeg lede?» – answered with a postcode (no geolocation without a tap). */
async function where(page: Page) {
  const ask = chat(page).getByTestId("location-ask");
  await ask.getByRole("button", { name: "Skriv by eller postnummer" }).click();
  await ask.getByLabel("By eller postnummer").fill("8000");
  await ask.getByRole("button", { name: "Gem" }).click();
  await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false");
  await expect(chat(page).getByTestId("business-results")).toBeVisible();
}

/** The plan badge in the header carries the numbers as data attributes (the visible text depends on the plan). */
const chip = (page: Page) => page.getByTestId("balance-chip");
const freeLeft = async (page: Page) => Number(await chip(page).getAttribute("data-free"));
const credits = async (page: Page) => Number(await chip(page).getAttribute("data-credits"));
const callsLeft = async (page: Page) => Number(await chip(page).getAttribute("data-calls-left"));
async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
}
/** Phone: the bottom tabs (Min dag · Opgaver · Butikken · Folk · Konto). Desktop: the header's pill navigation and the
 *  plan badge. The conversation has no tab of its own any more – it opens when you send from Min dag, or by URL. */
async function gotoTab(page: Page, name: "Opgaver" | "Konto" | "Samtale" | "Min dag" | "Butikken") {
  if (name === "Samtale") { await page.goto("/privat/samtale"); await expect(page.locator("[data-busy]")).toHaveAttribute("data-busy", "false"); return; }
  const desk = (page.viewportSize()?.width ?? 0) >= 1280;
  if (!desk) { await page.getByRole("navigation", { name: "Hovedmenu" }).getByRole("link", { name }).click(); return; }
  if (name === "Opgaver") await page.getByRole("navigation", { name: "Sider" }).getByRole("button", { name: "Mine opgaver" }).click();
  if (name === "Butikken") await page.getByRole("navigation", { name: "Sider" }).getByRole("button", { name: "Butikken" }).click();
  if (name === "Min dag") await page.getByRole("navigation", { name: "Sider" }).getByRole("button", { name: "Min dag" }).click();
  if (name === "Konto") await page.getByTestId("balance-chip").click();
}
/** Live card in the conversation for the last task. */
const chat = (page: Page) => page.getByRole("region", { name: "Samtale" });

for (const width of [375, 1440]) {
  test.describe(`${width}px`, () => {
    needsFake();
    test.use({ viewport: { width, height: width > 1000 ? 900 : 812 } });

    test("liste: oprettes, tilføj æbler → én liste med 3 punkter, gratis-tæller uændret (prøveperiode = ubegrænset)", async ({ page }) => {
      await open(page, "/privat/dag", { login: false });
      await expect.poll(() => freeLeft(page)).toBe(2);
      await expect(page.getByTestId("day-chat-card")).toBeVisible();
      await expect(page.getByTestId("your-turn")).toBeVisible();
      await expect(page.getByTestId("room-card")).toBeVisible();
      await say(page, "Lav en indkøbsliste med mælk og rugbrød");
      const sheet = page.getByRole("dialog", { name: "Gem din opgave" });
      await expect(sheet).toBeVisible();
      await expect(sheet.getByRole("link", { name: "Opret privat konto" })).toHaveAttribute("href", /\/signup\?next=/);
      await sheet.getByRole("button", { name: /Fortsæt som testbruger/ }).click();
      await expect(chat(page).getByRole("heading", { name: "Indkøbsliste" })).toBeVisible();
      // Lists and reminders are unlimited with the trial: the free counter does not move.
      await expect.poll(() => freeLeft(page)).toBe(2);
      await say(page, "Tilføj æbler");
      const card = chat(page).getByRole("heading", { name: "Indkøbsliste" }).locator("xpath=ancestor::div[contains(@class,'rounded-[18px]')][1]");
      await expect(card.getByRole("button", { name: "Æbler" })).toBeVisible();
      await expect(card.locator("button[aria-pressed]")).toHaveCount(3);
      await expect.poll(() => freeLeft(page)).toBe(2);
      await gotoTab(page, "Opgaver");
      await expect(page.getByRole("region", { name: "Mine opgaver" }).getByText("Indkøbsliste", { exact: true })).toHaveCount(1);
      await noOverflow(page);
    });

    test("påmindelse kl. 16 → flyt til kl. 17: én påmindelse med før/efter", async ({ page }) => {
      await open(page);
      await say(page, "Mind mig om at hente pakken i morgen kl. 16");
      await expect(chat(page).getByRole("heading", { name: "Hente pakken" })).toBeVisible();
      await expect(chat(page).getByText("I morgen kl. 16.00", { exact: true }).first()).toBeVisible();
      await say(page, "Flyt den til kl. 17");
      await expect(chat(page).getByText("Påmindelsen er flyttet")).toBeVisible();
      await expect(chat(page).getByText("I morgen kl. 16.00", { exact: true }).last()).toHaveClass(/line-through/);
      await expect(chat(page).getByText("I morgen kl. 17.00", { exact: true }).last()).toBeVisible();
      await gotoTab(page, "Opgaver");
      const tasks = page.getByRole("region", { name: "Mine opgaver" });
      await expect(tasks.getByText("Hente pakken", { exact: true })).toHaveCount(1);
      await expect(tasks.getByText(/Påmindelse i morgen kl\. 17\.00/)).toBeVisible();
    });

    test("opkald: Cykelmageren → bekræft nummer → godkend → svarer → bekræftet (tæller på planen, ikke credits)", async ({ page }) => {
      await open(page);
      await say(page, "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15");
      await where(page);
      await chat(page).getByRole("button", { name: /Cykelmageren/ }).click();
      await expect(chat(page).getByRole("heading", { name: "Skal jeg ringe til Cykelmageren?" })).toBeVisible();
      await chat(page).getByRole("button", { name: "Godkend opkald" }).click();
      await chat(page).getByLabel("Mobilnummer").fill("12 34 56 78");
      await chat(page).getByRole("button", { name: "Send kode" }).click();
      await chat(page).getByLabel("Kode fra SMS").fill("123456");
      await chat(page).getByRole("button", { name: "Bekræft", exact: true }).click();
      await expect(chat(page).getByText("Ringer til Cykelmageren …")).toBeVisible();
      // The trial's Plus quota pays: credits untouched, the call counts when it is answered.
      await expect(chat(page).getByText("1 af 10 opkald i Plus")).toBeVisible();
      await expect.poll(() => credits(page)).toBe(3);
      await expect.poll(() => callsLeft(page)).toBe(10);
      await chat(page).getByRole("button", { name: "Værkstedet svarer" }).click();
      await expect(chat(page).getByRole("heading", { name: "Torsdag kl. 15.30 er bekræftet" })).toBeVisible();
      await expect(chat(page).getByText("Bekræftet af værkstedet")).toBeVisible();
      await expect(chat(page).getByText(/450 kr\. for et almindeligt eftersyn/)).toBeVisible();
      await expect(chat(page).getByText("1 af 10 opkald i Plus · 2 min. 10 sek.")).toBeVisible();
      await expect.poll(() => callsLeft(page)).toBe(9);
      await expect.poll(() => credits(page)).toBe(3);
      await noOverflow(page);
    });

    test("opkald uden svar → tæller ikke på planen", async ({ page }) => {
      await open(page);
      await say(page, "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15");
      await where(page);
      await chat(page).getByRole("button", { name: /Cykelmageren/ }).click();
      await chat(page).getByRole("button", { name: "Godkend opkald" }).click();
      await chat(page).getByLabel("Mobilnummer").fill("12345678");
      await chat(page).getByRole("button", { name: "Send kode" }).click();
      await chat(page).getByLabel("Kode fra SMS").fill("123456");
      await chat(page).getByRole("button", { name: "Bekræft", exact: true }).click();
      await expect.poll(() => callsLeft(page)).toBe(10);
      await chat(page).getByRole("button", { name: "Ingen svarer" }).click();
      await expect(chat(page).getByRole("heading", { name: "Ingen tog telefonen – opkaldet tæller ikke" })).toBeVisible();
      await expect.poll(() => callsLeft(page)).toBe(10);
      await expect.poll(() => credits(page)).toBe(3);
    });

    test("«Hvad venter på mig?» linker til opgaven (uden login)", async ({ page }) => {
      await open(page, "/privat/dag", { login: false });
      await say(page, "Hvad venter på mig?");
      await expect(chat(page).getByText("Én ting venter på dit svar:")).toBeVisible();
      await chat(page).getByRole("button", { name: /Vælg tid hos Tandlæge Holm/ }).click();
      await expect(page).toHaveURL(/\/privat\/opgaver\/e1$/);
      await expect(page.getByRole("heading", { name: "Vælg tid hos Tandlæge Holm", level: 2 })).toBeVisible();
    });

    test("uden plan: 10/10 brugt → ny opgave bliver udkast → brug 1 credit → aktiv", async ({ page }) => {
      await open(page, "/privat/konto");
      await page.getByRole("button", { name: "Afslut prøveperioden" }).click();
      await expect(page.getByTestId("subscription-card")).toContainText("Prøveperiode slut");
      await page.getByRole("button", { name: "Sæt forbrug til 10/10" }).click();
      await expect.poll(() => freeLeft(page)).toBe(0);
      await gotoTab(page, "Samtale");
      await say(page, "Lav en liste med kaffe og te");
      const sheet = page.getByRole("dialog", { name: "Månedens 10 gratis opgaver er brugt" });
      await expect(sheet).toBeVisible();
      await expect(sheet.getByRole("button", { name: /Se et sponsorindslag/ })).toBeVisible();
      await expect(sheet.getByRole("button", { name: "Vælg plan" })).toBeVisible();
      await sheet.getByRole("button", { name: "Brug 1 credit · du har 3" }).click();
      await expect(sheet).toBeHidden();
      await expect(chat(page).getByText("Opgaven er aktiv nu.", { exact: false })).toBeVisible();
      await expect(chat(page).getByRole("button", { name: "Kaffe" })).toBeVisible();
      await expect.poll(() => credits(page)).toBe(2);
    });

    test("butikken: slå Ring for mig fra → chip væk, kort i chatten → slå til → opkald virker", async ({ page }) => {
      await open(page, "/privat/tilfoejelser");
      await expect(page).toHaveURL(/\/privat\/butik$/);
      await page.getByRole("button", { name: "Åbn Ring for mig" }).click();
      await page.getByRole("button", { name: "Slå fra: Ring for mig" }).click();
      await page.getByRole("dialog", { name: "Slå Ring for mig fra?" }).getByRole("button", { name: "Slå fra" }).click();
      await page.getByRole("button", { name: "Åbn Ring for mig" }).click();
      await expect(page.getByRole("button", { name: "Installér: Ring for mig" })).toBeVisible();
      await page.getByRole("dialog").getByRole("button", { name: "Luk" }).click();
      await page.goto("/privat/dag");
      await expect(page.locator("button:visible", { hasText: "Lav en liste" })).toHaveCount(1);
      await expect(page.getByRole("button", { name: "Ring for mig", exact: true })).toHaveCount(0);
      await say(page, "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15");
      await expect(chat(page).getByRole("heading", { name: "Ring for mig er ikke slået til" })).toBeVisible();
      await chat(page).getByRole("button", { name: "Slå til", exact: true }).click();
      await chat(page).getByRole("button", { name: "Send beskeden igen" }).click();
      await where(page);
      await chat(page).getByRole("button", { name: /Cykelmageren/ }).click();
      await expect(chat(page).getByRole("heading", { name: "Skal jeg ringe til Cykelmageren?" })).toBeVisible();
      await expect(page.locator("button", { hasText: /^Ring for mig$/ }).first()).toBeAttached();
    });

    test("delt indkøbsliste: den andens tilføjelse vises med navn", async ({ page }) => {
      await open(page);
      await say(page, "Lav en indkøbsliste med mælk");
      await chat(page).getByRole("button", { name: "Del", exact: true }).click();
      const sheet = page.getByRole("dialog", { name: "Del «Indkøbsliste»" });
      await sheet.getByLabel(/Fælles liste/).check();
      await sheet.getByRole("button", { name: "Lav invitationslink" }).click();
      await expect(sheet.getByTestId("share-link")).toHaveText(/localhost:\d+\/i\/[A-HJ-NP-Z2-9]{8}/);
      await sheet.getByRole("button", { name: "Luk" }).click();
      await chat(page).getByRole("button", { name: /Anna tilføjer noget/ }).click();
      await expect(chat(page).getByText("Anna tilføjede kaffe")).toBeVisible();
      await expect(chat(page).getByText("Delt via Dialogbot")).toBeVisible();
    });

    test("ønskeliste: ejeren ser aldrig reservationer; et medlem kan reservere og fortryde", async ({ page }) => {
      await open(page);
      await say(page, "Lav en ønskeliste med cykelhjelm og bog");
      await chat(page).getByRole("button", { name: "Del", exact: true }).click();
      const sheet = page.getByRole("dialog", { name: "Del «Ønskeliste»" });
      await expect(sheet.getByLabel(/Ønskeliste/)).toBeChecked();
      await sheet.getByRole("button", { name: "Lav invitationslink" }).click();
      await sheet.getByRole("button", { name: "Luk" }).click();
      await chat(page).getByRole("button", { name: /Anna reserverer et ønske/ }).click();
      await expect(chat(page).getByText("Du kan ikke se, hvad der er reserveret – så overraskelsen holder.")).toBeVisible();
      await expect(chat(page).getByText("Reserveret", { exact: true })).toHaveCount(0);
      await expect(chat(page).getByRole("button", { name: "Jeg køber den" })).toHaveCount(0);
      // As a member of someone else's wishlist.
      await page.goto("/privat/opgaver/s1");
      const detail = page.getByRole("region", { name: "Opgave" }).or(page.locator("[aria-label='Opgave']")).first();
      await expect(detail.getByText("Reserveret", { exact: true })).toBeVisible();
      await detail.getByRole("button", { name: "Jeg køber den" }).first().click();
      await expect(detail.getByText("Du køber den")).toBeVisible();
      await detail.getByRole("button", { name: "Fortryd" }).click();
      await expect(detail.getByText("Du køber den")).toHaveCount(0);
      await expect(detail.getByRole("button", { name: "Jeg køber den" })).toHaveCount(2);
    });

    test("invitation: værdien først, Dialogbot-kortet, accept → listen med banner", async ({ page }) => {
      await page.goto("/privat/invitation/sommerfest");
      await expect(page.getByRole("heading", { name: "Sommerfest – fælles indkøb" })).toBeVisible();
      await expect(page.getByText("Anna har delt en liste med dig")).toBeVisible();
      await expect(page.getByText("2 punkter")).toBeVisible();
      await expect(page.getByText("Anna bruger Dialogbot")).toBeVisible();
      await expect(page.getByText("Få din egen: 10 gratis opgaver hver måned")).toBeVisible();
      await expect(page.getByText("Grillkul")).toHaveCount(0);
      await noOverflow(page);
      await page.getByRole("button", { name: "Åbn listen" }).click();
      await expect(page).toHaveURL(/\/privat\/opgaver\/s2\?velkommen=1/);
      await expect(page.getByRole("button", { name: "Prøv selv: Hvad skal jeg klare for dig?" })).toBeVisible();
      await expect(page.getByText("Grillkul").first()).toBeVisible();
    });

    test("belønning: vennens første egne opgave giver +3 i invitererens bevægelser", async ({ page }) => {
      await open(page);
      await say(page, "Lav en indkøbsliste med mælk");
      await chat(page).getByRole("button", { name: "Del", exact: true }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Lav invitationslink" }).click();
      await page.getByRole("dialog").getByRole("button", { name: "Luk" }).click();
      // Each simulated step saves to sessionStorage after a short delay: wait until it is saved, or the next step (and the
      // reload) runs too early – the bonus then never lands (seen in CI).
      const saved = (key: "annaJoined" | "annaRewarded") => expect.poll(() => page.evaluate(
        (k) => JSON.parse(sessionStorage.getItem("dialogbot-privat-fake") ?? "{}")?.ref?.[k] === true, key)).toBe(true);
      await chat(page).getByRole("button", { name: /Anna tilføjer noget/ }).click();
      await saved("annaJoined");
      await chat(page).getByRole("button", { name: /Anna laver sin første egen opgave/ }).click();
      await saved("annaRewarded");
      await page.goto("/privat/konto");
      await expect(page.getByTestId("ledger").getByText("Invitationsbonus: Anna lavede sin første opgave")).toBeVisible();
      await expect.poll(() => credits(page)).toBe(6);
    });

    test("grupper: forslag + indsatte numre → del ønskeliste → 3 i appen / 2 SMS → kø → Med", async ({ page }) => {
      await open(page, "/privat/folk");
      await page.getByRole("button", { name: "Ny gruppe" }).click();
      await page.getByLabel("Gruppens navn").fill("Familien");
      for (const n of ["Anna", "Jonas", "Peter"]) await page.getByRole("button", { name: new RegExp(`^${n}`) }).click();
      await page.getByLabel("Indsæt flere numre").fill("12 34 56 78, 87654321");
      await page.getByRole("button", { name: "Tilføj 2 numre" }).click();
      await expect(page.getByTestId("group-members").locator("li")).toHaveCount(5);
      await page.getByRole("button", { name: "Gem gruppen", exact: true }).click();
      await expect(page.getByText("Familien · 5 personer")).toBeVisible();

      await page.goto("/privat/samtale");
      await say(page, "Lav en ønskeliste med cykelhjelm");
      await chat(page).getByRole("button", { name: "Del", exact: true }).click();
      const sheet = page.getByRole("dialog");
      await sheet.getByLabel(/Familien · 5 personer/).check();
      await expect(sheet.getByTestId("group-summary")).toContainText("3 har Dialogbot og bliver tilføjet med det samme");
      await expect(sheet.getByTestId("group-summary")).toContainText("2 får en SMS fra dig");
      await sheet.getByRole("button", { name: "En ad gangen" }).click();
      const next = sheet.getByTestId("queue-next");
      await expect(next).toHaveText(/Næste: \+45 12 34 56 78 \(1 af 2\)/);
      await expect(next).toHaveAttribute("href", /^sms:\+4512345678\?body=Hej!%20Jeg%20har%20lavet%20en%20%C3%B8nskeliste/);
      await next.click();
      await expect(next).toHaveText(/Sendt\? Næste: \+45 87 65 43 21 \(2 af 2\)/);
      await expect(next).toHaveAttribute("href", /^sms:\+4587654321\?body=/);
      await next.click();
      await expect(sheet.getByText("Alle 2 er inviteret.")).toBeVisible();
      await sheet.getByRole("button", { name: "Færdig" }).click();
      await gotoTab(page, "Opgaver");
      await page.getByRole("region", { name: "Mine opgaver" }).getByText("Ønskeliste", { exact: true }).last().click();
      const status = page.getByTestId("people-status");
      await expect(status.getByText("Med", { exact: true })).toHaveCount(3);
      await expect(status.getByText("Ikke åbnet endnu")).toHaveCount(2);
      await status.getByRole("button", { name: /Næste person reagerer/ }).click();
      await expect(status.getByText("Har åbnet")).toHaveCount(1);
      await status.getByRole("button", { name: /Næste person reagerer/ }).click();
      await expect(status.getByText("Med", { exact: true })).toHaveCount(4);
    });

    test("chat: «Del ønskelisten med familien» foreslår at lave gruppen", async ({ page }) => {
      await open(page);
      await say(page, "Lav en ønskeliste med bog");
      await say(page, "Del ønskelisten med familien");
      await expect(chat(page).getByText("Skal jeg lave gruppen Familien med Anna, Jonas og Peter?", { exact: false })).toBeVisible();
      await chat(page).getByRole("button", { name: /Ja, lav gruppen/ }).click();
      await expect(chat(page).getByRole("button", { name: "Del med gruppen" })).toBeVisible();
      await chat(page).getByRole("button", { name: "Del med gruppen" }).click();
      await expect(page.getByRole("dialog").getByLabel(/Familien · 3 personer/)).toBeChecked();
      await expect(page.getByRole("dialog").getByTestId("group-summary")).toContainText("3 har Dialogbot");
    });

    test(".vcf: 3 kontakter i filen, vælg 2 → kun 2 gemmes", async ({ page }) => {
      await open(page, "/privat/folk");
      await page.getByRole("button", { name: "Ny gruppe" }).click();
      await page.getByLabel("Gruppens navn").fill("Venner");
      await expect(page.getByText("Filen bliver på din telefon.", { exact: false })).toBeVisible();
      await page.getByTestId("vcf-input").setInputFiles(join(FIX, "iphone-3.vcf"));
      await expect(page.getByText("Vælg personer (3 i filen)")).toBeVisible();
      await page.getByRole("checkbox", { name: /Anna Hansen/ }).check();
      await page.getByRole("checkbox", { name: /Mor Ørsted/ }).check();
      await page.getByRole("button", { name: "Tilføj 2 valgte" }).click();
      await page.getByRole("button", { name: "Gem gruppen", exact: true }).click();
      await expect(page.getByText("Venner · 2 personer")).toBeVisible();
      const saved = await page.evaluate(() => JSON.parse(sessionStorage.getItem("dialogbot-privat-fake")!).groups[0].members.map((m: { phone_e164: string }) => m.phone_e164));
      expect(saved).toEqual(["+4521222324", "+4541424344"]);
    });

    test("gruppelink /g/[kode]: skriv navn → medlemmet dukker op i ejerens gruppe", async ({ page }) => {
      await open(page, "/privat/folk");
      await page.getByRole("button", { name: "Ny gruppe" }).click();
      await page.getByLabel("Gruppens navn").fill("Familien");
      await page.getByRole("button", { name: /^Anna/ }).click();
      await page.getByRole("button", { name: "Gem gruppen og lav link" }).click();
      const url = (await page.getByTestId("join-url").innerText()).trim();
      const code = url.split("/g/")[1];
      expect(code).toMatch(/^[A-HJ-NP-Z2-9]{8}$/);
      await page.goto(`/g/${code}`);
      await expect(page.getByRole("heading", { name: "Mette inviterer dig med i Familien på Dialogbot" })).toBeVisible();
      await expect(page.getByText("Mette bruger Dialogbot")).toBeVisible();
      await noOverflow(page);
      await page.getByLabel("Skriv dit navn").fill("Lise");
      await page.getByRole("button", { name: "Kom med" }).click();
      await expect(page.getByText("Du er med i Familien")).toBeVisible();
      await page.goto("/privat/folk");
      await expect(page.getByText("Familien · 2 personer")).toBeVisible();
    });

    test("virksomhedssøgning: by først, resultater med åbningstid og ★, lukket → ring når de åbner", async ({ page }) => {
      await open(page);
      await say(page, "Ring til cykelværkstedet og aftal aflevering torsdag efter kl. 15");
      await expect(chat(page).getByTestId("location-ask").getByRole("button", { name: "Brug min position" })).toBeVisible();
      await where(page);
      const res = chat(page).getByTestId("business-results");
      await expect(res).toContainText("Nørregade 12, 8000 Aarhus C · 600 m");
      await expect(res).toContainText("Åben nu · ★ 4,7 (213)");
      await expect(res).toContainText("Lukket – åbner tors. kl. 8.00");
      await expect(res).toContainText("86 12 34 56");
      await expect(res.getByText("Demodata – fiktive virksomheder, ikke fra Google")).toBeVisible();
      await res.getByRole("button", { name: /Østbyens Cykler/ }).click();
      await expect(chat(page).getByText("Lukket nu – jeg ringer, når de åbner tors. kl. 8.00")).toBeVisible();
      await expect(chat(page).getByRole("button", { name: "Godkend – ring når de åbner" })).toBeVisible();
      await page.goto("/privat/konto");
      await expect(page.locator("[data-testid=city-row]:visible")).toContainText("8000 Aarhus C");
    });

    test("intet nummer → «Hvad er deres nummer?»; mobilnummer kræver «Det er en virksomhed»", async ({ page }) => {
      await open(page);
      await say(page, "Ring til cykelværkstedet torsdag efter kl. 15");
      await where(page);
      await chat(page).getByRole("button", { name: /Cykelhjørnet/ }).click();
      const approve = chat(page).getByRole("button", { name: "Godkend opkald" });
      await expect(approve).toBeDisabled();
      await chat(page).getByLabel("Hvad er deres nummer?").fill("28 91 44 12");
      await chat(page).getByRole("button", { name: "Brug nummeret" }).click();
      await expect(chat(page).getByText("Tak. Jeg bruger 28 91 44 12.")).toBeVisible();
      const box = chat(page).getByRole("checkbox", { name: /Det er en virksomhed/ });
      await expect(box).toBeVisible();
      await expect(approve).toBeDisabled();
      await box.check();
      await expect(approve).toBeEnabled();
    });

    test("butikken: app-ark med «Hvad den gør», trin og «Start opsætningen»; uden plan → «Med i Plus»", async ({ page }) => {
      await open(page, "/privat/butik");
      await expect(page.getByRole("heading", { name: "Installeret" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Alle apps" })).toBeVisible();
      await page.getByRole("button", { name: "Åbn Fødselsdage" }).click();
      const sheet = page.getByRole("dialog", { name: "Fødselsdage" });
      await expect(sheet.getByText("Hvad den gør")).toBeVisible();
      await expect(sheet.getByText("«Mormor fylder 80 den 3. marts.»")).toBeVisible();
      await sheet.getByRole("button", { name: "Installér: Fødselsdage" }).click();
      await expect(sheet.getByTestId("addon-setup")).toContainText("Opsætning · 3 trin");
      await sheet.getByRole("button", { name: "Start opsætningen: Fødselsdage" }).click();
      await expect(sheet).toBeHidden();
      await page.getByRole("button", { name: "Åbn Fødselsdage" }).click();
      await expect(page.getByRole("dialog").getByRole("button", { name: "Åbn: Fødselsdage" })).toBeVisible();
      await page.getByRole("dialog").getByRole("button", { name: "Luk" }).click();
      // Kommer snart is disabled; without rights the plan offer replaces the button.
      await page.getByRole("button", { name: "Åbn Pakker" }).click();
      await expect(page.getByRole("dialog").getByRole("button", { name: "Kommer snart: Pakker" })).toBeDisabled();
      await page.getByRole("dialog").getByRole("button", { name: "Luk" }).click();
      await page.goto("/privat/konto");
      await page.getByRole("button", { name: "Afslut prøveperioden" }).click();
      await page.goto("/privat/butik");
      await page.getByRole("button", { name: "Åbn Kalender" }).click();
      await expect(page.getByRole("dialog").getByTestId("needs-plan")).toContainText("Med i Plus");
      await page.getByRole("dialog").getByRole("button", { name: "Vælg plan" }).click();
      await expect(page).toHaveURL(/\/privat\/konto/);
    });

    test("abonnement: Vælg plan → Plus (årligt) → retur fra betaling → «Dit abonnement er aktivt»", async ({ page }) => {
      await open(page, "/privat/konto");
      const card = page.getByTestId("subscription-card");
      await expect(card).toContainText("Prøveperiode");
      await card.getByRole("button", { name: "Vælg plan" }).click();
      const picker = page.getByTestId("plan-picker");
      await picker.getByRole("button", { name: "Årligt · spar 20 %" }).click();
      await expect(picker.getByTestId("plan-plus")).toContainText("Anbefalet");
      await expect(picker.getByTestId("plan-plus")).toContainText("79 kr./md.");
      await picker.getByTestId("plan-plus").getByRole("button", { name: "Vælg Plus" }).click();
      await expect(page).toHaveURL(/\/privat\/konto$/);
      await expect(page.getByTestId("account-note")).toHaveText("Dit abonnement er aktivt.");
      await expect(chip(page)).toHaveAttribute("data-plan", "plus");
      await expect(card).toContainText("Plus");
      await expect(card.getByRole("button", { name: "Administrér abonnement" })).toBeVisible();
      await expect(page.getByTestId("ledger")).toContainText("Plus valgt · 948 kr./år");
    });

    test("ingen vandret scroll på hovedsiderne", async ({ page }) => {
      await open(page);
      for (const p of ["/privat", "/privat/dag", "/privat/samtale", "/privat/opgaver", "/privat/opgaver/e2", "/privat/konto", "/privat/butik", "/privat/folk"]) {
        await page.goto(p);
        await page.waitForLoadState("networkidle");
        await noOverflow(page);
      }
    });
  });
}

for (const [label, ua, scheme] of [["iPhone", IOS_UA, "sms:?&body="], ["Android", ANDROID_UA, "sms:?body="]] as const) {
  test.describe(`del-ark på ${label}`, () => {
    needsFake();
    test.use({ viewport: { width: 375, height: 812 }, userAgent: ua });
    test(`SMS-link har ${scheme} og kontaktvælgeren er skjult uden API`, async ({ page }) => {
      await open(page);
      await say(page, "Lav en ønskeliste med cykelhjelm");
      await chat(page).getByRole("button", { name: "Del", exact: true }).click();
      const sheet = page.getByRole("dialog");
      await sheet.getByRole("button", { name: "Lav invitationslink" }).click();
      const href = await sheet.getByTestId("share-sms").getAttribute("href");
      expect(href!.startsWith(scheme)).toBeTruthy();
      const body = decodeURIComponent(href!.slice(scheme.length));
      expect(body).toMatch(/^Hej! Jeg har lavet en ønskeliste – se den og reservér her: localhost:\d+\/i\/[A-HJ-NP-Z2-9]{8} – Mette$/);
      expect(body.length).toBeLessThanOrEqual(160);
      await expect(sheet.getByTestId("share-contacts")).toHaveCount(0);
      await expect(sheet.getByRole("link", { name: "WhatsApp" })).toHaveAttribute("href", /^https:\/\/wa\.me\/\?text=/);
    });
  });
}

/** Notification + PushManager + service worker, mocked in the page (Chromium headless has no push service). */
async function mockPush(page: Page, opts: { standalone?: boolean } = {}) {
  await page.addInitScript((standalone) => {
    const w = window as unknown as Record<string, unknown>;
    let perm = "default";
    let sub: { endpoint: string; toJSON(): unknown; unsubscribe(): Promise<boolean> } | null = null;
    class FakeNotification { static get permission() { return perm; } static async requestPermission() { w.__asked = ((w.__asked as number) ?? 0) + 1; perm = "granted"; return perm; } }
    w.Notification = FakeNotification;
    w.PushManager = function PushManager() {};
    const reg = { scope: "/privat/", pushManager: {
      getSubscription: async () => sub,
      subscribe: async (o: { applicationServerKey: Uint8Array }) => {
        w.__keyLength = o.applicationServerKey.length;
        sub = { endpoint: "https://push.example/e2e", toJSON: () => ({ endpoint: "https://push.example/e2e", keys: { p256dh: "p256", auth: "auth" } }), unsubscribe: async () => { sub = null; return true; } };
        return sub;
      } } };
    Object.defineProperty(navigator, "serviceWorker", { configurable: true, value: { register: async () => reg, getRegistration: async () => reg } });
    if (standalone) Object.defineProperty(navigator, "standalone", { configurable: true, value: true });
  }, !!opts.standalone);
}

test.describe("push", () => {
  needsFake();
  test.use({ viewport: { width: 375, height: 812 } });
  test("Konto: slå til → abonnement sendes; test; slå fra", async ({ page }) => {
    await mockPush(page);
    await open(page, "/privat/konto");
    const box = page.getByTestId("push-account");
    await box.getByRole("button", { name: "Slå notifikationer til" }).click();
    await expect(box.getByText("Slået til på denne enhed")).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __keyLength: number }).__keyLength)).toBe(65);
    const subs = () => page.evaluate(() => JSON.parse(sessionStorage.getItem("dialogbot-privat-fake")!).push as string[]);
    expect(await subs()).toEqual(["https://push.example/e2e"]);
    await box.getByRole("button", { name: "Send en test" }).click();
    await expect(box.getByText("Testen er sendt til 1 enhed.")).toBeVisible();
    await box.getByRole("button", { name: "Slå fra" }).click();
    await expect(box.getByRole("button", { name: "Slå notifikationer til" })).toBeVisible();
    expect(await subs()).toEqual([]);
  });
  test("første påmindelse spørger; derefter ikke igen", async ({ page }) => {
    await mockPush(page);
    await open(page);
    await say(page, "Mind mig om at ringe til mor i morgen kl. 10");
    await chat(page).getByTestId("push-reminder").getByRole("button", { name: "Slå notifikationer til" }).click();
    await expect(chat(page).getByTestId("push-reminder").getByText("Slået til på denne enhed")).toBeVisible();
    expect(await page.evaluate(() => (window as unknown as { __asked: number }).__asked)).toBe(1);
  });
});

test.describe("push på iPhone", () => {
  needsFake();
  test.use({ viewport: { width: 375, height: 812 }, userAgent: IOS_UA });
  test("Safari uden hjemmeskærm viser vejledningen og spørger ikke", async ({ page }) => {
    await mockPush(page);
    await open(page, "/privat/konto");
    await expect(page.getByTestId("ios-guide")).toContainText("Tryk på Del nederst i Safari.");
    await expect(page.getByTestId("push-account").getByRole("button", { name: "Slå notifikationer til" })).toHaveCount(0);
  });
  test("fra hjemmeskærmen (standalone) kan den slås til", async ({ page }) => {
    await mockPush(page, { standalone: true });
    await open(page, "/privat/konto");
    await expect(page.getByTestId("ios-guide")).toHaveCount(0);
    await page.getByTestId("push-account").getByRole("button", { name: "Slå notifikationer til" }).click();
    await expect(page.getByTestId("push-account").getByText("Slået til på denne enhed")).toBeVisible();
  });
});
