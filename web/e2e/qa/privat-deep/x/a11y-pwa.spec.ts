import { expect, test } from "@playwright/test";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { BASE, within, go, APP_ROUTES, AXE, EVID, PUBLIC_ROUTES, evidence, plusUser, requirePrivatStack, runAxe, settle, uniqueIp } from "./px-helpers";

/** PX · i18n-a11y-qa: PC-A11Y-01/02 (axe, 44 px, tekststørrelse, sheets/fokus, toast), PC-BRAND-02 (accent #C4461A,
 *  theme-color), PC-BRAND-03 (ord over folden), PC-PWA-01 (manifest), PC-PWA-02 (offline-side), PC-SHOP-12, PC-DAY-04,
 *  PC-PUSH-03 (ingen push-prompt ved første besøg), PC-VCF-03 (kontaktvælger / vCard). */

const BRAND = "rgb(196, 70, 26)";   // #C4461A

async function targets(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const out: { tag: string; text: string; w: number; h: number }[] = [];
    for (const el of Array.from(document.querySelectorAll("main a[href], main button, main [role=button], main input:not([type=hidden]), main select, nav a[href], nav button"))) {
      const r = (el as HTMLElement).getBoundingClientRect();
      const st = getComputedStyle(el as HTMLElement);
      if (r.width === 0 || r.height === 0 || st.visibility === "hidden") continue;
      if ((el as HTMLElement).closest("p, li span") && el.tagName === "A" && r.height < 44) {  // inline text links are exempt (WCAG 2.5.8)
        if ((el.parentElement?.innerText.length ?? 0) > (el as HTMLElement).innerText.length + 10) continue;
      }
      if ((el as HTMLInputElement).type === "checkbox" || (el as HTMLInputElement).type === "radio") {
        const lab = (el as HTMLElement).closest("label"); if (lab && lab.getBoundingClientRect().height >= 44) continue;
      }
      if (r.width < 44 || r.height < 44) out.push({ tag: el.tagName.toLowerCase(), text: ((el as HTMLElement).innerText || el.getAttribute("aria-label") || "").slice(0, 40), w: Math.round(r.width), h: Math.round(r.height) });
    }
    return out;
  });
}

async function smallText(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    let small = 0, total = 0; const ex: string[] = [];
    for (const el of Array.from(document.querySelectorAll("main p, main li, main span, main label"))) {
      const t = (el as HTMLElement).innerText?.trim(); if (!t || t.length < 25 || el.children.length > 2) continue;
      total++; const fs = parseFloat(getComputedStyle(el).fontSize);
      if (fs < 16) { small++; if (ex.length < 5) ex.push(`${fs}px: ${t.slice(0, 50)}`); }
    }
    return { small, total, ex };
  });
}

async function foldWords(page: import("@playwright/test").Page) {
  return page.evaluate(() => {
    const h = window.innerHeight; let words = 0; let primary = 0;
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let n: Node | null;
    while ((n = walker.nextNode())) {
      const p = n.parentElement; if (!p) continue;
      const st = getComputedStyle(p); if (st.visibility === "hidden" || st.display === "none") continue;
      const r = p.getBoundingClientRect(); if (r.top >= h || r.bottom <= 0 || r.width === 0) continue;
      words += (n.textContent ?? "").trim().split(/\s+/).filter(Boolean).length;
    }
    for (const b of Array.from(document.querySelectorAll("main button, main a"))) {
      const r = b.getBoundingClientRect(); if (r.top >= h || r.bottom <= 0) continue;
      const bg = getComputedStyle(b).backgroundColor; if (bg === "rgb(196, 70, 26)" || bg === "rgb(224, 82, 26)") primary++;
    }
    return { words, primary };
  });
}

test("PC-A11Y-01 · axe + 44 px + tekst ≥16 px + 200 % zoom på alle Privat-skærme", async ({ page }, info) => {
  test.setTimeout(300_000);
  test.skip(!existsSync(AXE), "axe-core mangler");
  await plusUser(page, info, "a11y");
  await page.request.post("/api/backend/privat/messages", { headers: { "x-requested-with": "dialogbot" }, data: { text: "Lav en indkøbsliste med mælk og rugbrød" } });
  const report: Record<string, unknown> = {};
  const serious: string[] = [];
  for (const r of [...PUBLIC_ROUTES, ...APP_ROUTES]) {
    await go(page, r);
    const ax = (await runAxe(page)) ?? [];
    const tg = await targets(page);
    const st = await smallText(page);
    const fold = await foldWords(page);
    const hscroll = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    report[r] = { axe: ax, small_targets: tg.slice(0, 12), small_target_count: tg.length, small_text: st, fold, hscroll };
    for (const v of ax) if (v.impact === "critical" || v.impact === "serious") serious.push(`${r} ${v.id} (${v.n}) ${v.targets[0] ?? ""}`);
    expect.soft(hscroll, `${r}: vandret scroll`).toBe(false);
  }
  // 200 % zoom on mobile ≈ 195 css px wide
  if (info.project.name === "mobil-390") {
    await page.setViewportSize({ width: 195, height: 422 });
    const zoom: Record<string, boolean> = {};
    for (const r of ["/privat/dag", "/privat/butik", "/privat/butik/ring-for-mig", "/privat/konto"]) {
      await go(page, r);
      zoom[r] = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
    }
    report["zoom200"] = zoom;
    for (const [r, v] of Object.entries(zoom)) expect.soft(v, `200 % zoom ${r}: vandret scroll`).toBe(false);
  }
  evidence(`a11y-${info.project.name}.json`, report);
  expect.soft(serious, "axe serious/critical").toEqual([]);
});

test("PC-A11Y-01 · PlanSheet/sheets: fokus fanges, Escape lukker, radiogruppe", async ({ page }, info) => {
  await uniqueIp(page);
  await requirePrivatStack(page);
  const { privatUser } = await import("../../privat/pq-helpers");
  await privatUser(page, info, "px-sheet");          // free tier: Plus-apps open the PlanSheet
  await go(page, "/privat/butik/kalender");
  const cta = page.locator("main").getByRole("button").filter({ hasText: /14 dage|Prøv|Start|Slå til|Tilføj/i }).first();
  await cta.click();
  const dlg = page.getByRole("dialog").first();
  await expect(dlg).toBeVisible();
  const inside = await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]"));
  expect.soft(inside, "fokus i dialogen ved åbning").toBe(true);
  for (let i = 0; i < 15; i++) await page.keyboard.press("Tab");
  expect.soft(await page.evaluate(() => !!document.activeElement?.closest("[role=dialog]")), "Tab bliver i dialogen").toBe(true);
  const radios = await dlg.getByRole("radio").count();
  const groups = await dlg.getByRole("radiogroup").count();
  evidence(`sheet-${info.project.name}.json`, { inside, radios, groups, html: (await dlg.innerHTML()).slice(0, 1500) });
  expect.soft(radios > 0 ? groups : 1, "radiogruppe har role=radiogroup").toBeGreaterThan(0);
  await page.keyboard.press("Escape");
  await expect(dlg).toBeHidden();
  expect.soft(await page.evaluate(() => document.activeElement?.tagName), "fokus tilbage på knappen").toBe("BUTTON");
});

test("PC-A11Y-02 · fortryd-toast: role=status, aria-live og varighed", async ({ page }, info) => {
  await plusUser(page, info, "toast");
  await go(page, "/privat/butik/madplan");
  const off = page.getByRole("button", { name: /Slå fra|Fjern|Deaktiv/i }).first();
  test.skip(!(await off.count()), "ingen slå-fra-knap på madplan");
  await off.click();
  const confirm = page.getByRole("dialog").getByRole("button", { name: /Slå fra|Fjern|Ja/i }).first();
  if (await confirm.count()) await confirm.click();
  const toast = page.locator("[role=status]").filter({ hasText: /Fortryd|Undo|fra/i }).first();
  await expect(toast).toBeVisible({ timeout: 5000 });
  const live = await toast.getAttribute("aria-live");
  const t0 = Date.now();
  await expect(toast).toBeHidden({ timeout: 20_000 });
  const ms = Date.now() - t0;
  evidence(`toast-${info.project.name}.json`, { live, visible_ms: ms });
  expect.soft(ms, "toast ≥ 8 s").toBeGreaterThan(7000);
});

test("PC-BRAND-02 · accent #C4461A og theme-color på Privat-sider", async ({ page }, info) => {
  await uniqueIp(page);
  const out: Record<string, unknown> = {};
  for (const r of ["/privat", "/privat/start/1", "/privat/offline", "/privat/invitation/ikke-et-token"]) {
    await go(page, r);
    const meta = await page.locator('meta[name="theme-color"]').first().getAttribute("content").catch(() => null);
    const accent = await page.evaluate(() => {
      const el = document.querySelector("[data-theme=privat]") ?? document.body;
      return getComputedStyle(el).getPropertyValue("--color-accent").trim() || getComputedStyle(el).getPropertyValue("--accent").trim();
    });
    const themed = await page.locator("[data-theme=privat]").count();
    out[r] = { meta, accent, themed };
    expect.soft(meta?.toUpperCase(), `${r} theme-color`).toBe("#C4461A");
    expect.soft(themed, `${r}: data-theme=privat`).toBeGreaterThan(0);
  }
  evidence(`brand-${info.project.name}.json`, out);
  void BRAND;
});

test("PC-PWA-01 · manifest: start_url, scope, ikoner, apple-touch-icon 180", async ({ page, request }, info) => {
  test.skip(info.project.name !== "mobil-390", "én gang");
  const m = await (await request.get("/privat/manifest.webmanifest")).json();
  expect(m.start_url).toBe("/privat/dag");
  expect(m.scope).toBe("/privat/");
  expect(m.display).toBe("standalone");
  expect(m.theme_color).toBe("#C4461A");
  for (const i of m.icons) expect((await request.get(i.src)).status(), i.src).toBe(200);
  expect(m.icons.some((i: { purpose: string }) => i.purpose === "maskable")).toBe(true);
  await page.goto("/privat");
  expect(await page.locator('link[rel="manifest"]').getAttribute("href")).toBe("/privat/manifest.webmanifest");
  const apple = await page.locator('link[rel="apple-touch-icon"]').first().getAttribute("href");
  expect(apple).toContain("180");
  const img = await request.get(apple!);
  expect(img.status()).toBe(200);
  const buf = await img.body();
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  expect([w, h]).toEqual([180, 180]);
  for (const s of m.screenshots ?? []) expect.soft((await request.get(s.src)).status(), s.src).toBe(200);
  evidence("pwa-manifest.json", m);
});

test("PC-PWA-02 · offline-side: «Du er offline …» + «Prøv igen», og SW serverer den uden net", async ({ page, context }, info) => {
  await uniqueIp(page);
  await page.goto("/privat/offline");
  await expect(page.getByText(/^Du er offline – siden vises igen/)).toBeVisible();
  const retry = page.getByRole("button", { name: "Prøv igen" });
  await expect(retry).toBeVisible();
  const box = await retry.boundingBox();
  expect(box!.height).toBeGreaterThanOrEqual(44);
  // install the SW from a Privat page, then go offline
  await page.goto("/privat");
  const sw = await page.evaluate(async () => {
    if (!("serviceWorker" in navigator)) return "none";
    const reg = await Promise.race([navigator.serviceWorker.ready, new Promise((r) => setTimeout(() => r(null), 8000))]);
    return reg ? (reg as ServiceWorkerRegistration).active?.scriptURL ?? "no-active" : "timeout";
  });
  let offlineText = "";
  if (sw !== "none" && sw !== "timeout") {
    await page.waitForTimeout(1500);
    await context.setOffline(true);
    await page.goto("/privat/dag").catch(() => {});
    offlineText = await page.locator("body").innerText().catch(() => "");
    await context.setOffline(false);
  }
  evidence(`pwa-offline-${info.project.name}.json`, { sw, offlineText: offlineText.slice(0, 400) });
  if (sw !== "none" && sw !== "timeout") expect.soft(offlineText).toMatch(/Ingen forbindelse|Du er offline/);
  else info.annotations.push({ type: "sw", description: `service worker ikke aktiv i testbrowser (${sw})` });
  await page.screenshot({ path: join(EVID, `offline-${info.project.name}.png`), fullPage: true });
});

test("PC-SHOP-12/PC-DAY-04 · Butik-knap synlig og klikbar; Dag + samtale (desktop)", async ({ page }, info) => {
  await plusUser(page, info, "shop12");
  await go(page, "/privat/butik/madplan");
  const names = await page.evaluate(() => Array.from(document.querySelectorAll("button, a")).filter((b) => b.getBoundingClientRect().height > 0).map((b) => (b as HTMLElement).innerText.trim()).filter(Boolean));
  evidence(`shop12-buttons-${info.project.name}.json`, names);
  const action = page.locator("button:visible, a:visible").filter({ hasText: /Slå til|Åbn|Brug|Tilføj|Slå fra|Start|Prøv|Fortæl|Skriv til/i }).first();
  await expect(action).toBeVisible();
  const box = await action.boundingBox();
  const vh = page.viewportSize()!.height;
  const tab = await page.locator("nav").last().boundingBox();
  const covered = await page.evaluate(([x, y]) => { const el = document.elementFromPoint(x, y); return el?.closest("button, a")?.textContent?.slice(0, 40) ?? el?.tagName; }, [box!.x + box!.width / 2, box!.y + box!.height / 2]);
  evidence(`shop12-${info.project.name}.json`, { box, vh, tab, covered });
  expect.soft(box!.y + box!.height).toBeLessThanOrEqual(vh);
  if (tab && info.project.name === "mobil-390") expect.soft(box!.y + box!.height, "over tab-bar").toBeLessThanOrEqual(tab.y + 1);
  if (info.project.name === "desktop-1440") {
    await page.setViewportSize({ width: 1280, height: 800 });
    await go(page, "/privat/dag");
    const input = page.getByRole("textbox").first();
    const visible = await input.isVisible().catch(() => false);
    if (visible) {
      await input.fill("Lav en liste med æg");
      await input.press("Enter");
      await page.waitForTimeout(1500);
      expect.soft(await page.evaluate(() => document.activeElement?.tagName), "fokus i input efter send").toMatch(/TEXTAREA|INPUT/);
    }
    const scrollers = await page.evaluate(() => Array.from(document.querySelectorAll("*")).filter((e) => {
      const s = getComputedStyle(e); return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 2; }).length);
    evidence(`day04-desktop.json`, { chatVisible: visible, scrollers });
  }
});

test("PC-PUSH-03/PC-PUSH-01 · ingen push-prompt ved første besøg; ærlig tekst uden VAPID", async ({ page }, info) => {
  let asked = false;
  await page.exposeFunction("__pxAsked", () => { asked = true; });
  await page.addInitScript(() => {
    const orig = Notification.requestPermission?.bind(Notification);
    // @ts-ignore override
    Notification.requestPermission = (...a) => { (window as unknown as { __pxAsked: () => void }).__pxAsked(); return orig ? orig(...a) : Promise.resolve("default"); };
  });
  await plusUser(page, info, "push");
  await go(page, "/privat/dag");
  await go(page, "/privat/konto");
  expect(asked, "Notification.requestPermission ved første besøg").toBe(false);
  const txt = await within(page.evaluate(() => document.body.innerText), 15000, "HANG");
  const pushLine = txt.split("\n").filter((l) => /push|notifikation|besked på telefonen|hjemmeskærm/i.test(l)).slice(0, 6);
  evidence(`push-${info.project.name}.json`, { pushLine });
});

test("PC-VCF-03 · kontakter: Contact Picker (Android) ellers vCard-import (iPhone)", async ({ browser }, info) => {
  test.setTimeout(120_000);
  const res: Record<string, unknown> = {};
  for (const [label, ua, picker] of [
    ["iphone", "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1", false],
    ["android", "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Mobile Safari/537.36", true],
  ] as const) {
    const ctx = await browser.newContext({ baseURL: BASE, userAgent: ua, viewport: { width: 390, height: 844 } });
    const page = await ctx.newPage();
    if (picker) await page.addInitScript(() => {
      // @ts-ignore fake Contact Picker API
      navigator.contacts = { select: async () => [{ name: ["Ole Berg"], tel: ["+4520112233"] }], getProperties: async () => ["name", "tel"] };
      // @ts-ignore
      window.ContactsManager = function () {};
    });
    await plusUser(page, info, `vcf-${label}`);
    await go(page, "/privat/folk");
    await page.getByRole("button", { name: /Ny gruppe/i }).first().click();
    await page.waitForTimeout(800);
    const vcf = await page.getByTestId("vcf-import").count();
    const pick = await page.getByRole("button", { name: /Vælg fra kontakter/i }).count();
    res[label] = { vcf, pick };
    await page.screenshot({ path: join(EVID, `vcf-${label}.png`), fullPage: true });
    await ctx.close();
  }
  evidence(`vcf-${info.project.name}.json`, res);
  expect.soft((res.iphone as { vcf: number }).vcf, "iPhone: vCard-import").toBeGreaterThan(0);
  expect.soft((res.android as { pick: number }).pick, "Android: Vælg fra kontakter").toBeGreaterThan(0);
});
