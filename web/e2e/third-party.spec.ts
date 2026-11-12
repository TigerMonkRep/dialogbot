import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { PREVIEW_CODE, SEEDED, login } from "./helpers";

/* Fürster 12/11: «Travelpayouts skal kun være på Privat» + «når jeg åbner appen i en browser, åbner Travelpayouts en ny
 * fane med rejsetilbud». Root cause: the Travelpayouts «Drive» site script (emrldtp.cc) sat on /erhverv – where "/" sends
 * every returning Erhverv visitor – and its monetisation module hooks every click on the page and opens travel offers
 * in a new tab (window.open(url, "_blank"): «overtab»/«undertab»/«delayed_redirect»). Guard: no page may load a
 * Travelpayouts script, and no page may open a tab, popup or redirect itself when the visitor clicks around. On Privat,
 * Travelpayouts lives only in the booking links (with the marker) the person clicks themselves.
 *
 * Fürster 12/11 16:07 (option B): the site script comes back on ONE page, the public /privat landing, so the partner
 * account's verification still finds it – off unless NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY=1, and it must never open a tab,
 * popup or redirect. It runs in a sandboxed iframe (/privat/tp-verify, sandbox="allow-scripts" + CSP sandbox header),
 * never in our document (web/src/lib/travelpayouts.ts). The flag-on tests run against a second server started from the
 * same build with the flag (TP_VERIFY_BASE_URL); there the script is replaced by a malicious fake that tries
 * window.open, a target=_blank link, top.location and hooking our document on load and on every click.
 *
 * Runs in the journeys job (real stack, preview gate on, flag off) and in the privat job (NEXT_PUBLIC_PRIVAT_FAKE=1,
 * flag off on :3000 and on on :3001). The Travelpayouts hosts are blocked or faked here, so the test never depends on
 * their servers. */

const TP_HOST = /(^|\.)(emrldtp\.cc|travelpayouts\.com|tp\.media|tp\.st|aviasales\.[a-z]+|tp[okxm]\.(li|lu|lv|mx|ro|gr|lt))$/i;
const fake = process.env.NEXT_PUBLIC_PRIVAT_FAKE === "1";
/** A server started from the same build with NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY=1 (the privat job: :3001). */
const ON = process.env.TP_VERIFY_BASE_URL?.replace(/\/$/, "");

async function guard(context: BrowserContext) {
  const tp: string[] = [];
  const popups: string[] = [];
  await context.route(/.*/, (route) => {
    const url = route.request().url();
    let host = "";
    try { host = new URL(url).hostname; } catch { /* data:, blob: */ }
    if (TP_HOST.test(host)) { tp.push(url); return route.abort(); }
    return route.fallback();
  });
  context.on("page", (p) => popups.push(p.url() || "about:blank"));
  return { tp, popups };
}

/** Clicks on plain text (never a link or a button): Drive's popunder fires on any click anywhere on the page. */
async function clickAround(page: Page) {
  const before = page.url();
  for (const sel of ["h1", "main p", "footer"]) {
    const el = page.locator(sel).first();
    if (await el.count()) await el.click({ position: { x: 2, y: 2 }, force: true, noWaitAfter: true }).catch(() => {});
    await page.waitForTimeout(300);
  }
  await page.mouse.click(5, 300);
  await page.waitForTimeout(1500);
  expect(page.url(), "siden sendte sig selv videre efter et klik").toBe(before);
}

async function unlockPreview(page: Page) {
  // The preview gate is on in the journeys job only; in the fake build there is nothing to unlock.
  await page.request.post("/api/preview/unlock", { headers: { "x-requested-with": "dialogbot" }, data: { code: PREVIEW_CODE, next: "/" } }).catch(() => null);
}

const ERHVERV = ["/da", "/da/erhverv", "/da/priser", "/start/1", "/da/privatliv", "/da/vilkaar", "/login"];
const PRIVAT = ["/privat", "/privat/start/1"];
const FRAME = "iframe[data-travelpayouts-verify], iframe[src*='tp-verify'], script[src*='emrldtp'], script#travelpayouts-drive";

test.describe("ingen Travelpayouts-script, ingen nye faner", () => {
  for (const path of ERHVERV) {
    test(`Erhverv ${path}: intet Travelpayouts, ingen popup`, async ({ page, context }) => {
      const { tp, popups } = await guard(context);
      await unlockPreview(page);
      const r = await page.goto(path);
      expect(r?.status(), path).toBeLessThan(400);
      await clickAround(page);
      expect(tp, "requests til Travelpayouts").toEqual([]);
      expect(popups, "nye faner/popups").toEqual([]);
      expect(await page.locator(FRAME).count()).toBe(0);
    });
  }

  test("forsiden med husket Erhverv-dør («åbner appen i en browser»): intet Travelpayouts, ingen popup", async ({ page, context, baseURL }) => {
    test.skip(fake, "fake-buildet har preview-låsen uden koder (privat-jobbet); journeys-jobbet dækker den");
    const { tp, popups } = await guard(context);
    await unlockPreview(page);
    await context.addCookies([{ name: "db_aud", value: "erhverv", url: baseURL ?? "http://localhost:3000" }]);
    await page.goto("/");
    await expect(page).toHaveURL(/\/erhverv/);
    await clickAround(page);
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });

  test("Erhverv-appen /app (logget ind): intet Travelpayouts, ingen popup", async ({ page, context }) => {
    test.skip(fake, "kræver backend (journeys-jobbet)");
    const { tp, popups } = await guard(context);
    await login(page, SEEDED.owner);
    await page.goto("/app");
    await clickAround(page);
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });

  for (const path of PRIVAT) {
    test(`Privat ${path}: intet globalt Travelpayouts-script, ingen popup`, async ({ page, context }) => {
      const { tp, popups } = await guard(context);
      const r = await page.goto(path);
      expect(r?.status(), path).toBeLessThan(400);
      await clickAround(page);
      expect(tp).toEqual([]);
      expect(popups).toEqual([]);
    });
  }

  test("flaget slået fra: /privat har ingen verifikations-iframe, /privat/tp-verify er 404", async ({ page }) => {
    await page.goto("/privat");
    expect(await page.locator(FRAME).count()).toBe(0);
    expect((await page.request.get("/privat/tp-verify")).status()).toBe(404);
  });

  test("Privat-appen (Min dag, Butikken): intet Travelpayouts-script, ingen popup", async ({ page, context }) => {
    test.skip(!fake, "kræver et web-build med NEXT_PUBLIC_PRIVAT_FAKE=1");
    const { tp, popups } = await guard(context);
    await page.addInitScript(() => sessionStorage.setItem("dialogbot-privat-fake-login", "1"));
    for (const path of ["/privat/dag", "/privat/butik"]) {
      await page.goto(path);
      await clickAround(page);
    }
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });
});

/** Stand-in for the remote-controlled Drive script at its worst: on load and on every click it tries a new tab
 *  (window.open and a target=_blank link), to send the top page away (top.location) and to hook our document. Every
 *  attempt is logged as «[tp-fake] …» so the test sees that it really ran. */
const EVIL = `(function () {
  if (!/^http/.test(location.protocol)) { console.log("[tp-fake] not http"); }
  var log = function (m) { console.log("[tp-fake] " + m); };
  function attack(tag) {
    try { var w = window.open("https://evil.example/open-" + tag, "_blank"); log(tag + " open=" + (w ? "window" : "null")); } catch (e) { log(tag + " open threw"); }
    try { var a = document.createElement("a"); a.href = "https://evil.example/a-" + tag; a.target = "_blank"; document.body.appendChild(a); a.click(); log(tag + " link clicked"); } catch (e) { log(tag + " link threw"); }
    // (Unframed – the control test – the load-time redirect is left to the delayed one, so the page is still there to click.)
    if (tag !== "load" || window.top !== window) { try { window.top.location.href = "https://evil.example/top-" + tag; log(tag + " top.location set"); } catch (e) { log(tag + " top.location threw"); } }
    try { window.parent.document.addEventListener("click", function () { window.open("https://evil.example/parent"); }, true); log(tag + " parent hooked"); } catch (e) { log(tag + " parent blocked"); }
  }
  log("loaded " + location.href);
  attack("load");
  setTimeout(function () { try { window.top.location.href = "https://evil.example/delayed"; log("delayed redirect set"); } catch (e) { log("delayed redirect threw"); } }, 2500);
  document.addEventListener("click", function () { attack("click"); }, true);
})();`;

const EVIL_HOST = /(^|\.)evil\.example$/i;

/** Fakes every Travelpayouts request with EVIL and records where it came from; evil.example is aborted and recorded. */
async function fakeTravelpayouts(context: BrowserContext) {
  const tp: { url: string; frame: string }[] = [];
  const evil: string[] = [];
  const popups: string[] = [];
  await context.route(/.*/, (route) => {
    const req = route.request();
    let host = "";
    try { host = new URL(req.url()).hostname; } catch { /* data:, blob: */ }
    if (EVIL_HOST.test(host)) { evil.push(req.url()); return route.abort(); }
    if (TP_HOST.test(host)) {
      let frame = "";
      try { frame = req.frame().url(); } catch { /* service worker */ }
      tp.push({ url: req.url(), frame });
      return route.fulfill({ status: 200, contentType: "application/javascript", body: EVIL });
    }
    return route.fallback();
  });
  context.on("page", (p) => popups.push(p.url() || "about:blank"));
  return { tp, evil, popups };
}

test.describe("Travelpayouts-verifikation kun på /privat (NEXT_PUBLIC_TRAVELPAYOUTS_VERIFY=1)", () => {
  test.skip(!ON, "kræver en server med flaget slået til (TP_VERIFY_BASE_URL; privat-jobbet starter den på :3001)");

  test("kontrol: den falske Drive åbner faner, når den ikke er sandboxet", async ({ page, context }) => {
    // Proves the fake is really malicious and that the popup detection works – the guard tests below mean something.
    const { popups, evil } = await fakeTravelpayouts(context);
    await page.setContent(`<html><body><p style="font-size:40px">tekst</p><script src="https://emrldtp.cc/NTk2Mjc3.js?t=596277"></script></body></html>`);
    await page.locator("p").click({ noWaitAfter: true });
    await expect.poll(() => popups.length, { message: "klik åbnede en ny fane" }).toBeGreaterThan(0);
    await expect.poll(() => evil.some((u) => u.includes("/top-")), { message: "siden blev sendt videre" }).toBe(true);
  });

  test("/privat: scriptet kun i den sandboxede iframe; 10 klik giver nul nye sider og ingen navigation", async ({ page, context }) => {
    const { tp, evil, popups } = await fakeTravelpayouts(context);
    const fakeLog: string[] = [];
    page.on("console", (m) => { if (m.text().startsWith("[tp-fake]")) fakeLog.push(m.text()); });
    const frameDoc = page.waitForResponse((res) => res.url().endsWith("/privat/tp-verify"));
    const r = await page.goto(`${ON}/privat`);
    expect(r?.status()).toBe(200);
    const start = page.url();
    const mainNavigations: string[] = [];
    page.on("framenavigated", (f) => { if (f === page.mainFrame()) mainNavigations.push(f.url()); });
    const doc = await frameDoc;
    expect(doc.status()).toBe(200);
    expect(doc.headers()["content-security-policy"]).toMatch(/^sandbox allow-scripts;/);

    // Exactly one carrier: the sandboxed iframe – no Travelpayouts <script> in our own document.
    const frameEl = page.locator("iframe[data-travelpayouts-verify]");
    await expect(frameEl).toHaveCount(1);
    expect(await frameEl.getAttribute("sandbox")).toBe("allow-scripts");
    expect(await frameEl.getAttribute("src")).toBe("/privat/tp-verify");
    expect(await page.locator("script[src*='emrldtp']:not([type='text/plain']), script#travelpayouts-drive").count()).toBe(0);
    await expect(page.locator("script[type='text/plain'][data-travelpayouts-verify-marker]")).toHaveCount(1);
    await expect.poll(() => fakeLog.some((l) => l.includes("loaded") && l.includes("/privat/tp-verify")), { message: "den falske Drive kørte i iframen" }).toBe(true);

    // 10 clicks: five on plain text in the page, five real (trusted) clicks inside the iframe – which is made big and
    // visible for the test, so the fake gets the user activation a real popunder needs.
    for (const sel of ["h1", "main p", "main h2", "main article", "footer span"]) {
      await page.locator(sel).first().click({ position: { x: 2, y: 2 }, force: true, noWaitAfter: true });
      await page.waitForTimeout(250);
    }
    await frameEl.evaluate((el: HTMLIFrameElement) => { Object.assign(el.style, { left: "10px", top: "10px", width: "400px", height: "300px", position: "fixed", zIndex: "99999", pointerEvents: "auto" }); });
    for (let i = 0; i < 5; i++) {
      await page.mouse.click(60 + i * 60, 100 + i * 30);
      await page.waitForTimeout(250);
    }
    await page.waitForTimeout(3000); // past the fake's delayed redirect

    expect(fakeLog.filter((l) => l.includes("click open=")).length, "klik inde i iframen nåede den falske Drive").toBeGreaterThanOrEqual(5);
    expect(fakeLog.filter((l) => l.includes("open=window")), "window.open gav et vindue").toEqual([]);
    expect(fakeLog.filter((l) => l.includes("parent hooked")), "den falske Drive kom ind i vores dokument").toEqual([]);
    expect(popups, "nye faner/popups").toEqual([]);
    expect(evil, "requests til evil.example (faner eller navigation)").toEqual([]);
    expect(page.url(), "siden sendte sig selv videre").toBe(start);
    expect(mainNavigations.filter((u) => u !== start), "hovedrammen navigerede væk").toEqual([]);
    expect(tp.length).toBeGreaterThan(0);
    expect(tp.filter((t) => !t.frame.endsWith("/privat/tp-verify")), "Travelpayouts-request uden for den sandboxede iframe").toEqual([]);
  });

  test("/privat/tp-verify åbnet direkte (ikke som iframe) er 404 – intet script", async ({ page, context }) => {
    const { tp, popups } = await fakeTravelpayouts(context);
    const r = await page.goto(`${ON}/privat/tp-verify`);
    expect(r?.status()).toBe(404);
    await page.waitForTimeout(500);
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });

  for (const path of [...ERHVERV, "/privat/start/1", "/privat/vilkaar"]) {
    test(`flag til – ${path}: stadig intet Travelpayouts, ingen popup`, async ({ page, context }) => {
      const { tp, popups } = await guard(context);
      await unlockPreview(page);
      const r = await page.goto(`${ON}${path}`);
      expect(r?.status(), path).toBeLessThan(400);
      await clickAround(page);
      expect(tp, "requests til Travelpayouts").toEqual([]);
      expect(popups).toEqual([]);
      expect(await page.locator(FRAME).count()).toBe(0);
    });
  }

  test("flag til – Privat-appen (Min dag, Butikken): intet Travelpayouts, ingen popup", async ({ page, context }) => {
    test.skip(!fake, "kræver et web-build med NEXT_PUBLIC_PRIVAT_FAKE=1");
    const { tp, popups } = await guard(context);
    await page.addInitScript(() => sessionStorage.setItem("dialogbot-privat-fake-login", "1"));
    for (const path of ["/privat/dag", "/privat/butik"]) {
      await page.goto(`${ON}${path}`);
      await clickAround(page);
      expect(await page.locator(FRAME).count()).toBe(0);
    }
    expect(tp).toEqual([]);
    expect(popups).toEqual([]);
  });
});
