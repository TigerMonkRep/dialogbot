import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { within, go, APP_ROUTES, BASE, HTML_LANG, LOCALES, PUBLIC_ROUTES, evidence, plusUser, setLocale, settle, uniqueIp, type L } from "./px-helpers";

/** PX · i18n-a11y-qa: PC-I18N-01 (8 sprog, cookie dlg_lang ellers Accept-Language), PC-I18N-02 (danske backend-tekster
 *  i andre sprog), PC-I18N-03 (datoer/beløb pr. locale). Evidens: qa/evidence/PX/i18n-*.json */

const MSG = join(__dirname, "../../../../src/i18n/messages");
const DA_WORDS = /(?<![\p{L}])(og|ikke|også|hvis|bliver|hvad|hvordan|når|skal|jeg|opkald\w*|tilføjelse\w*|godkend\w*|virksomhed\w*|opgave\w*|påmindelse\w*|ønske\w*|fødselsdag\w*|indkøbsliste\w*)(?![\p{L}])/giu;
const ALLOW = /(Dialogbot|Peter|Mette Hansen|Mette|Aarhus|Cykelmageren|Privat|Søren|Ærø|Bjørk|Æblegård)/g;

function danishLines(l: L, text: string): string[] {
  if (l === "da" || l === "no") return [];   // norsk deler for mange ord med dansk til en ordtælling
  return text.split(/\n+/).map((s) => s.trim()).filter((s) => s.length > 12).filter((s) => {
    const clean = s.replace(ALLOW, "");
    const hits = clean.match(DA_WORDS) ?? [];
    return hits.length >= 2 || (/[æø]/i.test(clean) && hits.length >= 1);
  });
}

test("PC-I18N-01 · privat.json har alle nøgler i alle 8 sprog (ingen dansk fallback)", async ({}, info) => {
  test.skip(info.project.name !== "mobil-390", "kører én gang");
  const flat = (o: Record<string, unknown>, p = ""): Record<string, unknown> => Object.entries(o).reduce((acc, [k, v]) =>
    ({ ...acc, ...(v && typeof v === "object" && !Array.isArray(v) ? flat(v as Record<string, unknown>, `${p}${k}.`) : { [`${p}${k}`]: v }) }), {});
  const da = flat(JSON.parse(readFileSync(join(MSG, "da/privat.json"), "utf8")));
  const out: Record<string, string[]> = {};
  for (const l of LOCALES.filter((x) => x !== "da")) {
    const o = flat(JSON.parse(readFileSync(join(MSG, `${l}/privat.json`), "utf8")));
    out[l] = Object.keys(da).filter((k) => !(k in o));
  }
  evidence("i18n-keys.json", out);
  for (const l of Object.keys(out)) expect.soft(out[l], `${l}: manglende privat-nøgler`).toEqual([]);
});

test("PC-I18N-01 · offentlige Privat-sider følger cookie og Accept-Language", async ({ browser }, info) => {
  test.setTimeout(300_000);
  const report: Record<string, unknown> = {};
  for (const l of LOCALES) {
    // 1) cookie
    const ctx = await browser.newContext({ baseURL: BASE });
    const page = await ctx.newPage();
    await setLocale(page, l);
    for (const r of PUBLIC_ROUTES) {
      await go(page, r);
      const lang = await page.locator("html").getAttribute("lang");
      const leaks = danishLines(l, await page.locator("body").innerText());
      report[`cookie:${l}:${r}`] = { lang, leaks: leaks.slice(0, 8) };
      evidence(`i18n-public-${info.project.name}.json`, report);
      expect.soft(lang, `${l} ${r} html lang`).toBe(HTML_LANG[l]);
      expect.soft(leaks, `${l} ${r}: dansk tekst`).toEqual([]);
    }
    await ctx.close();
    // 2) Accept-Language uden cookie
    const ctx2 = await browser.newContext({ baseURL: BASE, locale: l === "no" ? "nb-NO" : l, extraHTTPHeaders: { "accept-language": `${l === "no" ? "nb" : l};q=1` } });
    const p2 = await ctx2.newPage();
    await go(p2, "/privat");
    report[`accept:${l}`] = await p2.locator("html").getAttribute("lang");
    expect.soft(report[`accept:${l}`], `Accept-Language ${l}`).toBe(HTML_LANG[l]);
    await ctx2.close();
  }
  evidence(`i18n-public-${info.project.name}.json`, report);
});

test("PC-I18N-01/02 · app-skærme på en/de: dansk UI-tekst vs. danske backend-tekster", async ({ page }, info) => {
  test.setTimeout(400_000);
  const report: Record<string, { lang: string | null; leaks: string[] }> = {};
  await plusUser(page, info, "i18n", "en");
  // make some backend content exist: a chat answer, a call proposal
  await page.request.post("/api/backend/privat/messages", { headers: { "x-requested-with": "dialogbot" }, data: { text: "Ring til cykelværkstedet og find en tid torsdag efter klokken tre" } });
  for (const l of ["en", "de"] as L[]) {
    await setLocale(page, l);
    for (const r of APP_ROUTES) {
      await go(page, r);
      const body = await within(page.evaluate(() => (document.querySelector("main") as HTMLElement | null)?.innerText ?? ""), 8000, "HANG");
      const leaks = danishLines(l, body);
      report[`${l}:${r}`] = { lang: await within(page.evaluate(() => document.documentElement.lang), 5000, "HANG"), leaks: leaks.slice(0, 10) };
      evidence(`i18n-app-${info.project.name}.json`, report);
      expect.soft(report[`${l}:${r}`].lang).toBe(HTML_LANG[l]);
    }
  }
  evidence(`i18n-app-${info.project.name}.json`, report);
  await go(page, "/privat/butik/ring-for-mig");
  await page.screenshot({ path: join(__dirname, "../../../../../qa/evidence/PX", `i18n-de-butik-rfm-${info.project.name}.png`), fullPage: true });
  // Known backend-only Danish (PC-I18N-02): recorded, not failed here – see the finding.
  const leaking = Object.entries(report).filter(([, v]) => v.leaks.length).map(([k, v]) => `${k}: ${v.leaks[0]}`);
  info.annotations.push({ type: "danish-backend-text", description: leaking.join(" | ").slice(0, 2000) });
  expect.soft(leaking.length, "skærme med dansk tekst i en/de (se evidens)").toBe(0);
});

test("PC-I18N-03 · datoer og beløb formateres pr. locale", async ({ page }) => {
  const out = await page.evaluate(() => {
    const d = new Date(Date.UTC(2026, 10, 12, 13, 0));
    const fmt = (l: string) => ({ money: new Intl.NumberFormat(l, { style: "currency", currency: "DKK" }).format(1234.5),
      wd: new Intl.DateTimeFormat(l, { weekday: "long", timeZone: "Europe/Copenhagen" }).format(d) });
    return { da: fmt("da-DK"), en: fmt("en-GB"), de: fmt("de-DE") };
  });
  expect(out.da.money).toMatch(/1\.234,50\s?kr\./);
  expect(out.da.wd).toBe("torsdag");
  expect(out.de.wd).toBe("Donnerstag");
  evidence("i18n-intl-baseline.json", out);
});
