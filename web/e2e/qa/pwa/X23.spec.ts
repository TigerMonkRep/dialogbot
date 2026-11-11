import { expect, test, type Page } from "@playwright/test";
import { freshOwner, shot } from "../../helpers";

/* X23 (i18n-a11y-qa, bølge 2 / M2): PWA – manifest pr. målgruppe (blå/orange ikoner, start_url, scope),
 * install-prompt aldrig ved første visning, offlineside, versionerede SW-caches, opdaterings-toast,
 * ingen cachede logged-in sider. Kører mod den fulde stak (localhost = secure context, så SW registreres). */

const CSRF = { "x-requested-with": "dialogbot" };

async function pixel(page: Page, src: string): Promise<[number, number, number]> {
  return page.evaluate(async (u) => {
    const img = new Image(); img.src = u; await img.decode();
    const c = document.createElement("canvas"); c.width = img.width; c.height = img.height;
    const g = c.getContext("2d")!; g.drawImage(img, 0, 0);
    const d = g.getImageData(Math.floor(img.width * 0.12), Math.floor(img.height * 0.12), 1, 1).data; // background of the mark
    return [d[0], d[1], d[2]] as [number, number, number];
  }, src);
}

test("X23 · manifest pr. målgruppe: start_url, scope, ikoner (blå Erhverv / orange Privat)", async ({ page, request }) => {
  test.fail(true, "F-M2-16-X23: S2 new – Erhvervs-manifestet har start_url `/app` uden for scope `/app/`: manifest-scopet bliver ugyldigt …");
  const erh = await (await request.get("/manifest.webmanifest")).json();
  const prv = await (await request.get("/privat/manifest.webmanifest")).json();
  expect([erh.id, erh.start_url, erh.scope, erh.display]).toEqual(["/app/", "/app", "/app/", "standalone"]);
  expect([prv.id, prv.start_url, prv.scope, prv.display]).toEqual(["/privat/", "/privat/dag", "/privat/", "standalone"]);
  // W3C manifest: start_url must be within scope (path prefix), else the scope is dropped and defaults to "/"
  expect(prv.start_url.startsWith(prv.scope)).toBeTruthy();
  const erhWithin = erh.start_url.startsWith(erh.scope);
  for (const m of [erh, prv]) {
    expect(m.icons.some((i: { purpose: string }) => i.purpose === "maskable")).toBeTruthy();
    for (const i of m.icons) {
      const r = await request.get(i.src);
      expect(r.status(), i.src).toBe(200);
      expect(r.headers()["content-type"]).toContain("image/png");
    }
  }
  await page.goto("/login");
  const blue = await pixel(page, erh.icons.find((i: { purpose: string }) => i.purpose === "maskable").src);
  const orange = await pixel(page, prv.icons.find((i: { purpose: string }) => i.purpose === "maskable").src);
  expect(blue[2], `Erhverv-ikon ${blue}`).toBeGreaterThan(blue[0]);   // blue dominates
  expect(orange[0], `Privat-ikon ${orange}`).toBeGreaterThan(orange[2]); // orange dominates
  // each audience's pages link their own manifest
  await page.goto("/login");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
  const privatHtml = await (await request.get("/privat/offline")).text();
  expect(privatHtml).toContain('rel="manifest" href="/privat/manifest.webmanifest"');
  expect(erhWithin, `Erhverv start_url ${erh.start_url} ligger uden for scope ${erh.scope}`).toBeTruthy();
});

test("X23 · install-prompt aldrig ved første visning", async ({ page }, info) => {
  await page.addInitScript(() => {
    (window as any).__prompted = 0;
    window.addEventListener("load", () => setTimeout(() => {
      const ev = new Event("beforeinstallprompt", { cancelable: true }) as any;
      ev.prompt = async () => { (window as any).__prompted++; };
      ev.userChoice = Promise.resolve({ outcome: "dismissed" });
      window.dispatchEvent(ev);
      (window as any).__defaultPrevented = ev.defaultPrevented;
    }, 300));
  });
  for (const path of ["/login", "/privat/offline", "/app/offline"]) {
    await page.goto(path);
    await page.waitForTimeout(1200);
    expect(await page.evaluate(() => (window as any).__prompted), path).toBe(0);
  }
  await expect(page.getByText(/Føj til hjemmeskærm|Download app|Installer/i)).toHaveCount(0);
  await shot(page, info, "x23-forste-visning");
});

test("X23 · offlineside og versioneret SW-cache", async ({ page, context }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/konto");
  const cacheNames = await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    for (let i = 0; i < 40 && !navigator.serviceWorker.controller; i++) await new Promise((r) => setTimeout(r, 250));
    for (let i = 0; i < 40 && !(await caches.keys()).length; i++) await new Promise((r) => setTimeout(r, 250));
    return caches.keys();
  });
  info.attach("cache-names.json", { body: JSON.stringify(cacheNames), contentType: "application/json" });
  expect(cacheNames.some((n) => /^dialogbot-erhverv-v.+/.test(n)), JSON.stringify(cacheNames)).toBeTruthy();
  const swSrc = await (await page.request.get("/sw-app.js")).text();
  const version = swSrc.match(/^const VERSION = "([^"]*)";$/m)?.[1];
  info.attach("sw-version.txt", { body: String(version), contentType: "text/plain" });
  await context.route("**/app/aldrig-besogt-*", (route) => route.abort("internetdisconnected"));
  await context.setOffline(true);
  await page.goto("/app/aldrig-besogt-" + Date.now()).catch(() => {});
  await shot(page, info, "x23-offline");
  await expect(page.locator("body")).toContainText(/forbindelse|offline/i);
  await context.setOffline(false);
});

test("X23 · ingen cachede logged-in sider efter log ud", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const name = `Hemmelig Kunde ${Date.now()}`;
  const r = await page.request.post(`/api/backend/workspaces/${wsId}/leads`, { headers: CSRF, data: { contact_name: name, need_summary: "Fortroligt behov" } });
  expect(r.status()).toBe(201);
  const leadId = (await r.json()).id as string;
  await page.goto("/app/konto");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    for (let i = 0; i < 40 && !navigator.serviceWorker.controller; i++) await new Promise((r) => setTimeout(r, 250));
  });
  await page.goto(`/app/leads/${leadId}`);
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.waitForTimeout(1000); // the SW's cache.put is fire-and-forget
  // log out with the app's own logout route, as the account page does
  expect((await page.request.post("/api/auth/logout", { headers: CSRF })).status()).toBeLessThan(400);
  await page.goto("/login");
  const left = await page.evaluate(async (needle) => {
    const out: { path: string; containsName: boolean }[] = [];
    for (const n of await caches.keys()) {
      const c = await caches.open(n);
      for (const req of await c.keys()) {
        const p = new URL(req.url).pathname;
        if (!p.startsWith("/app") || p === "/app/offline") continue;
        const txt = await (await c.match(req))!.text();
        out.push({ path: p, containsName: txt.includes(needle) });
      }
    }
    return out;
  }, name);
  info.attach("cached-app-pages-after-logout.json", { body: JSON.stringify(left, null, 1), contentType: "application/json" });
  await shot(page, info, "x23-efter-logud");
  expect(left, "logged-in HTML (med kundens navn) ligger stadig i SW-cachen efter log ud").toEqual([]);
});

test("X23 · installeret app starter offline på start_url /app", async ({ page, context }, info) => {
  test.fail(true, "F-M2-16-X23: S2 new – Erhvervs-manifestet har start_url `/app` uden for scope `/app/`: manifest-scopet bliver ugyldigt …");
  await freshOwner(page, info);
  await page.goto("/app/konto");
  await page.evaluate(async () => {
    await navigator.serviceWorker.ready;
    for (let i = 0; i < 40 && !navigator.serviceWorker.controller; i++) await new Promise((r) => setTimeout(r, 250));
    for (let i = 0; i < 40 && !(await (await caches.open((await caches.keys())[0] ?? "x")).match("/app/offline")); i++) await new Promise((r) => setTimeout(r, 250));
  });
  await page.goto("/app");
  const controlledAtStart = await page.evaluate(() => !!navigator.serviceWorker.controller);
  await context.setOffline(true);
  let failed = "";
  await page.goto("/app").catch((e) => { failed = String(e).slice(0, 120); });
  await shot(page, info, "x23-offline-start-url");
  await context.setOffline(false);
  info.attach("offline-start.json", { body: JSON.stringify({ controlledAtStart, failed }), contentType: "application/json" });
  expect(controlledAtStart, "siden /app (manifestets start_url) styres ikke af SW'en med scope /app/").toBe(true);
});
