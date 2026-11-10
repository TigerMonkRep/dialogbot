import { expect, test, type Page } from "@playwright/test";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import PRICES from "../../../src/lib/prices.json";
import { PREVIEW_CODE } from "../../helpers";

/** QA X24 (i18n-a11y-qa): every locale × the six entry pages in a real browser.
 *  Locale selection (src/proxy.ts, src/i18n/config.ts): marketing pages ("/", "/erhverv", "/proev", "/priser") carry the
 *  language in the path (/<locale>/…, also stored in the dlg_lang cookie); /privat, /start and /privat/start are not
 *  prefixed and read the dlg_lang cookie (else Accept-Language, else da).
 *  Asserts: <html lang>, no "Danish" language claim on non-Danish pages, an own-language claim where the page makes one,
 *  no Danish prose leaking into en/de/es/fr/it/sv/no, and prices in the market currency formatted per locale.
 *  Optional axe-core (AXE_PATH=/home/claude/axe/node_modules/axe-core/axe.min.js) – serious/critical violations recorded.
 *  Evidence: qa/evidence/X24/browser-<project>.json */

const LOCALES = ["da", "en", "de", "es", "fr", "it", "no", "sv"] as const;
type L = (typeof LOCALES)[number];
const HTML_LANG: Record<L, string> = { da: "da", en: "en", de: "de", es: "es", fr: "fr", it: "it", no: "nb", sv: "sv" };
const ROUTES = ["/", "/erhverv", "/privat", "/proev", "/start", "/privat/start"] as const;
const PREFIXED = new Set(["/", "/erhverv", "/proev", "/priser"]);
const BASE = process.env.BASE_URL ?? "http://localhost:3000";
const EVIDENCE = join(__dirname, "../../../../qa/evidence/X24");
const AXE = process.env.AXE_PATH ?? "/home/claude/axe/node_modules/axe-core/axe.min.js";

// "Danish" as a language claim, in every language. Allowed contexts (legal: Danish law/VAT/authority, "Danish
// company", "Danish number") are not language claims and are stripped first.
const DANISH_CLAIM = /(på dansk|in danish|auf dänisch|en danés|en danois|in danese|på danska|dansktal\w*|danish[- ]speaking|dänischsprachig\w*|svarer på dansk|dansk stemme|danish voice|dänische stimme|voz danesa|voix danoise|voce danese|dansk röst)/i;
const OWN_CLAIM: Record<L, RegExp> = {
  da: /på dansk/i, en: /in English/i, de: /auf Deutsch/i, es: /en español/i, fr: /en français/i,
  it: /in italiano/i, no: /på norsk/i, sv: /på svenska/i,
};
const OTHER_CLAIMS = (l: L) => LOCALES.filter((x) => x !== l && !(l === "no" && x === "da") && !(l === "da" && x === "no")).map((x) => OWN_CLAIM[x]);
// Proper nouns/institutions that legitimately stay Danish.
const ALLOW = /(Skattestyrelsen|forskudsopgørelse\w*|Datatilsynet|markedsføringsloven|bogføringsloven|Aarhus|Fürster|Simonsen|B-indkomst|Cykelkælderen|Nørgaard( Tømrer)?|Trøjborg|Fjordgulv|København|Frederiksberg|Østerbro|Vesterbro|Nørrebro|Søren|Mette|Jørgen|Bjørn|Højbjerg|Århus|Brøndby|Køge|Ølstykke|Næstved|Dansk|Peter|Camilla|DDMMÅÅ)/g;
const DA_STRONG = /(?<![\p{L}])(og|ikke|jeres|vores|også|eller|hvis|bliver|sådan|hvad|hvordan|når|efter|før|til|på|af|jer|skal|din|dig|du|kan|med|der)(?![\p{L}])/giu;
const DA_ONLY_NO = /(?<![\p{L}])(jeres|virksomhed\w*|nogle|nogen|efter|sådan|bliver|gør|meget|spørgsmål|opkald\w*|hvad|tilbage|sidste|tilmeld\w*)(?![\p{L}])/iu;

function danishLines(l: L, text: string): string[] {
  if (l === "da") return [];
  const out: string[] = [];
  for (const raw of text.split(/\n+/)) {
    const line = raw.trim();
    if (line.length < 3) continue;
    const t = line.replace(ALLOW, "");
    if (l === "no") { if (DA_ONLY_NO.test(t)) out.push(line); continue; }
    if (l === "sv") { if (/[æø]/i.test(t) || /(?<![\p{L}])(jeres|vores|ikke|også|virksomhed\w*|opkald)(?![\p{L}])/iu.test(t)) out.push(line); continue; }
    const strong = new Set([...t.matchAll(DA_STRONG)].map((m) => m[1].toLowerCase()));
    if (/[æøå]/i.test(t) || strong.size >= 3) out.push(line);
  }
  return [...new Set(out)].slice(0, 40);
}

// ---------------------------------------------------------------- price expectations (same rules as lib/markets.ts)
type Cur = "DKK" | "SEK" | "NOK" | "EUR";
const P = PRICES as unknown as { localeCurrency: Record<string, Cur>; erhverv: Record<Cur, Record<string, number>>; privat: Record<Cur, Record<string, { monthly: number }>> };
const house = (s: string, lang: string) => (lang === "da" ? s.replace(/[  ]/g, " ") : s);
const money = (minor: number, cur: Cur, l: L) => {
  const lang = HTML_LANG[l]; const d = minor % 100 ? 2 : 0;
  return house(new Intl.NumberFormat(lang, { style: "currency", currency: cur, currencyDisplay: "symbol", minimumFractionDigits: d, maximumFractionDigits: d }).format(minor / 100), lang);
};
const amount = (minor: number, l: L) => {
  const lang = HTML_LANG[l]; const d = minor % 100 ? 2 : 0;
  return house(new Intl.NumberFormat(lang, { minimumFractionDigits: d, maximumFractionDigits: d }).format(minor / 100), lang);
};
const norm = (s: string) => s.replace(/[  ]/g, " ").replace(/\s+/g, " ");
// Currency marks that must NOT appear on a market's pages (EUR pages must not show kroner, kroner pages no €).
const WRONG_CUR: Record<Cur, RegExp> = {
  // ("kr." at the end of a Swedish/Norwegian sentence is a full stop, not the Danish "kr." – not checked.)
  DKK: /€|\bEUR\b|\bSEK\b|\bNOK\b/, SEK: /€|\bEUR\b|\bDKK\b|\bNOK\b/, NOK: /€|\bEUR\b|\bDKK\b|\bSEK\b/,
  EUR: /\d\s?kr\.?(?![\p{L}])|\bDKK\b|\bSEK\b|\bNOK\b/u,
};

async function unlock(page: Page) {
  const r = await page.request.post("/api/preview/unlock", { headers: { "x-requested-with": "dialogbot" }, data: { code: PREVIEW_CODE } });
  expect(r.ok(), "preview-kode accepteret").toBeTruthy();
}

// The funnel limits drafts per visitor IP (app/modules/funnel/limits.py: 20 creates/hour); every QA agent shares
// 127.0.0.1, so each visit gets its own documentation-range address (lib/visitor-ip.ts reads x-real-ip).
let ipSeq = Math.floor(Math.random() * 200);
const freshIp = () => `198.51.${100 + (++ipSeq % 100)}.${1 + Math.floor(Math.random() * 250)}`;

async function open(page: Page, l: L, route: string, ip = freshIp()) {
  await page.setExtraHTTPHeaders({ "x-real-ip": ip });
  await page.context().clearCookies();
  await unlock(page);
  await page.context().addCookies([{ name: "dlg_lang", value: l, url: BASE }]);
  const url = PREFIXED.has(route) ? (route === "/" ? `/${l}` : `/${l}${route}`) : route;
  const resp = await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle").catch(() => {});
  return { url, status: resp?.status() ?? 0, final: new URL(page.url()).pathname };
}

type Row = Record<string, unknown>;
const save = (name: string, rows: Row[]) => { mkdirSync(join(EVIDENCE, "browser"), { recursive: true }); writeFileSync(join(EVIDENCE, "browser", `${name}.json`), JSON.stringify(rows, null, 2)); };



for (const l of LOCALES) {
  test(`X24 · ${l}: sprog, sprogpåstande og dansk-lækage på de 6 indgangssider`, async ({ page }, info) => {
    test.setTimeout(240_000);
    const results: Row[] = [];
    for (const route of ROUTES) {
      const nav = await open(page, l, route);
      const htmlLang = await page.locator("html").getAttribute("lang");
      const title = await page.title();
      const desc = (await page.locator('meta[name="description"]').first().getAttribute("content").catch(() => null)) ?? "";
      const text = await page.evaluate(() => document.body.innerText);
      // Attributes the user meets too (placeholders, aria-labels, alt, button titles).
      const attrs = await page.evaluate(() => [...document.querySelectorAll("[placeholder],[aria-label],img[alt],[title]")]
        .flatMap((e) => ["placeholder", "aria-label", "alt", "title"].map((a) => e.getAttribute(a)).filter(Boolean) as string[]).join("\n"));
      const all = `${title}\n${desc}\n${text}\n${attrs}`;
      const claims = all.split(/\n+/).filter((s) => l !== "da" && l !== "no" && DANISH_CLAIM.test(s)).slice(0, 10);
      const noClaims = l === "no" ? all.split(/\n+/).filter((s) => /på dansk|dansk stemme|svarer på dansk/i.test(s)).slice(0, 10) : [];
      const foreignClaims = all.split(/\n+/).filter((s) => OTHER_CLAIMS(l).some((re) => re.test(s))).slice(0, 10);
      const own = OWN_CLAIM[l].test(all);
      const leaks = danishLines(l, all);
      const row = { project: info.project.name, locale: l, route, ...nav, htmlLang, title, desc: desc.slice(0, 160), ownClaim: own,
        danishClaims: [...claims, ...noClaims], foreignClaims, danishLeaks: leaks };
      results.push(row);
      await page.screenshot({ path: join(EVIDENCE, "shots", `${info.project.name}-${l}${route.replace(/\//g, "_") || "_root"}.png`), fullPage: false });

      expect.soft(nav.status, `${l} ${route}: HTTP`).toBeLessThan(400);
      expect.soft(nav.final, `${l} ${route}: ikke sendt til /preview`).not.toMatch(/^\/preview/);
      expect.soft(htmlLang, `${l} ${route}: <html lang>`).toBe(HTML_LANG[l]);
      expect.soft(row.danishClaims, `${l} ${route}: "dansk/Danish" som sprogpåstand på en ${l}-side`).toEqual([]);
      expect.soft(foreignClaims, `${l} ${route}: påstand om et andet sprog end sidens`).toEqual([]);
      expect.soft(leaks, `${l} ${route}: danske tekster på en ${l}-side`).toEqual([]);
      save(`${info.project.name}-lang-${l}`, results);
      if (route === "/") expect.soft(own, `${l} /: indgangssiden siger "${OWN_CLAIM[l].source}"`).toBeTruthy();
    }
  });
}

for (const l of LOCALES) {
  test(`X24 · ${l}: priser i markedets valuta og locale-format (/priser, /erhverv, /privat)`, async ({ page }, info) => {
    const results: Row[] = [];
    const cur = P.localeCurrency[l];
    const e = P.erhverv[cur];
    const privat = P.privat[cur];
    const expected = {
      erhvervMonthlyMoney: money(e.monthly, cur, l), erhvervMonthlyAmount: amount(e.monthly, l),
      callMoney: money(e.call, cur, l), privatBasis: money(privat.basis.monthly, cur, l), privatBasisAmount: amount(privat.basis.monthly, l),
    };
    for (const route of ["/priser", "/erhverv", "/privat"]) {
      await open(page, l, route);
      const text = norm(await page.evaluate(() => document.body.innerText));
      const wrong = (text.match(new RegExp(WRONG_CUR[cur].source, "gu")) ?? []).slice(0, 5);
      const ctx = wrong.length ? [...text.matchAll(new RegExp(`.{0,50}(${WRONG_CUR[cur].source}).{0,30}`, "gu"))].map((m) => m[0]).slice(0, 5) : [];
      const hasErhverv = text.includes(norm(expected.erhvervMonthlyMoney)) || text.includes(norm(expected.erhvervMonthlyAmount));
      const hasPrivat = text.includes(norm(expected.privatBasis)) || text.includes(norm(expected.privatBasisAmount));
      // Danish number style (2.495) on a page whose locale writes 2,495 / 2 495 – or the reverse.
      const daStyle = amount(e.monthly, "da"); // "2.495"
      const foreignDaStyle = l !== "da" && cur === "DKK" && text.includes(daStyle);
      results.push({ project: info.project.name, kind: "price", locale: l, route, currency: cur, expected, hasErhverv, hasPrivat, wrongCurrency: ctx, foreignDaStyle });
      save(`${info.project.name}-price-${l}`, results);
      expect.soft(ctx, `${l} ${route}: forkert valuta for ${cur}-markedet`).toEqual([]);
      if (route !== "/privat") expect.soft(hasErhverv, `${l} ${route}: erhvervspris skrevet som ${expected.erhvervMonthlyMoney} / ${expected.erhvervMonthlyAmount}`).toBeTruthy();
      else expect.soft(hasPrivat, `${l} /privat: privatpris skrevet som ${expected.privatBasis}`).toBeTruthy();
    }
  });
}

test("X24 · funnel-fejl (429 rate_limited) vises på sidens sprog, ikke dansk", async ({ page }) => {
  const ip = freshIp();
  // Exhaust this one documentation IP's create bucket (20/hour) – touches only rows for 198.51.x.x.
  for (let i = 0; i < 21; i++) {
    const r = await page.request.post("/api/backend/funnel/drafts", { headers: { "x-requested-with": "dialogbot", "x-real-ip": ip, "content-type": "application/json" }, data: { kind: "erhverv" } });
    if (r.status() === 429) break;
  }
  for (const l of ["en", "de", "sv"] as L[]) {
    await open(page, l, "/start", ip);
    const alert = page.getByRole("alert").first();
    await expect(alert).toBeVisible();
    const msg = (await alert.innerText()).trim();
    save(`funnel-429-${l}`, [{ locale: l, ip, message: msg }]);
    expect.soft(danishLines(l, msg), `${l} /start: 429-fejlen er dansk: «${msg}»`).toEqual([]);
  }
});

for (const l of ["en", "de"] as L[]) {
  test(`X24 · ${l}: /start trin 1–3 (tal fra backend) uden dansk`, async ({ page }) => {
    await open(page, l, "/start");
    await page.locator("main button, main [role=radio], main [role=checkbox]").first().click();
    await page.waitForURL(/\/start\/2/);
    await page.locator("main input").first().fill("QA Carpentry Ltd");
    await page.keyboard.press("Escape");
    await page.locator("main button[type=submit]").click();
    await page.waitForURL(/\/start\/3/);
    await page.locator("main button[aria-pressed], main [role=checkbox], main button").first().click();
    await page.waitForTimeout(1500);
    const text = await page.evaluate(() => document.body.innerText);
    const leaks = danishLines(l, text);
    save(`funnel-steps-${l}`, [{ locale: l, url: page.url(), leaks }]);
    await page.screenshot({ path: join(EVIDENCE, "shots", `funnel-s3-${l}.png`), fullPage: true });
    expect.soft(leaks, `${l} /start/3: danske tekster`).toEqual([]);
  });
}

test("X24 · axe-core: alvorlige/kritiske overtrædelser på de 6 sider (da, en, de)", async ({ page }, info) => {
  test.skip(!existsSync(AXE), `axe-core ikke installeret (${AXE})`);
  test.setTimeout(240_000);
  const out: Row[] = [];
  for (const l of ["da", "en", "de"] as L[]) {
    for (const route of ROUTES) {
      await open(page, l, route);
      await page.addScriptTag({ path: AXE });
      const r = await page.evaluate(async () => {
        // @ts-expect-error axe injected
        const res = await window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } });
        return res.violations.filter((v: { impact: string }) => v.impact === "serious" || v.impact === "critical")
          .map((v: { id: string; impact: string; help: string; nodes: { target: string[]; failureSummary: string; html: string }[] }) => ({
            id: v.id, impact: v.impact, help: v.help, count: v.nodes.length,
            nodes: v.nodes.slice(0, 4).map((n) => ({ target: n.target.join(" "), html: n.html.slice(0, 160), why: n.failureSummary.slice(0, 200) })) }));
      });
      out.push({ project: info.project.name, locale: l, route, violations: r });
    }
  }
  writeFileSync(join(EVIDENCE, `axe-${info.project.name}.json`), JSON.stringify(out, null, 2));
  const flat = out.flatMap((o) => (o.violations as { id: string }[]).map((v) => `${o.locale} ${o.route}: ${v.id}`));
  expect.soft(flat, "axe serious/critical").toEqual([]);
});

test.beforeAll(() => { mkdirSync(join(EVIDENCE, "shots"), { recursive: true }); });
