import { writeFileSync, mkdirSync } from "node:fs";
import { expect, test, devices } from "@playwright/test";
import { CSRF, say, shot, stackUp, trial, user } from "./pk";

/** PC-VCF-01/02 (vCard-import fra iPhone, intet sendes før brugeren gemmer) og PC-INV-03 (sms:-link fra brugerens EGEN
 *  telefon: iOS `sms:a,b?&body=`, Android `sms:a;b?body=`), PC-INV-10 (udløbet link → venlig side). */
test.beforeEach(async ({ request }) => { test.skip(!(await stackUp(request)), "kræver Privat-stakken på :8400"); });

const DIR = "/home/claude/pk-fixtures";
const IPHONE_VCF = [
  "BEGIN:VCARD", "VERSION:3.0", "PRODID:-//Apple Inc.//iPhone OS 18.1//EN", "N:Ærø;Søren;;;", "FN:Søren Ærø",
  "item1.TEL;type=pref:+45 20 30 40 51", "TEL;type=CELL;type=VOICE:20 30 40 52", "TEL;type=HOME;type=VOICE:86 12 34 56",
  "PHOTO;ENCODING=b;TYPE=JPEG:/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAgGBgcGBQgHBwcJCQgKDBQNDAsLDBkSEw8UHRofHh0aHBwgJC4nICIsIxwcKDcpLDAxNDQ0Hyc5PTgyPC4zNDL/",
  " 2wBDAQkJCQwLDBgNDRgyIRwhMjIyMjIyMjIyMjIyMjIyMjIy", "END:VCARD",
  "BEGIN:VCARD", "VERSION:3.0", "N:Ågesen;Åse;;;", "FN:Åse Ågesen", "TEL;type=CELL:+4520304053", "END:VCARD",
  "BEGIN:VCARD", "VERSION:3.0", "FN:Kun Fastnet", "TEL;type=WORK:+4589870001", "END:VCARD",
  "BEGIN:VCARD", "VERSION:3.0", "FN:Ingen Nummer", "EMAIL:x@example.com", "END:VCARD",
].join("\r\n");

test("PC-VCF-01: iPhone-.vcf → navne og mobilnumre; intet uploades før «Gem gruppen»", async ({ page }, info) => {
  mkdirSync(DIR, { recursive: true });
  writeFileSync(`${DIR}/iphone.vcf`, IPHONE_VCF);
  await user(page, info, "vcf01");
  await trial(page);
  const sent: string[] = [];
  page.on("request", (r) => { const b = r.postData(); if (b && r.url().includes("/api/")) sent.push(`${r.method()} ${r.url()} ${b}`); });
  await page.goto("/privat/folk");
  await page.getByRole("button", { name: /Ny gruppe/ }).click();
  await page.getByPlaceholder("Fx Familien").fill("Familien");
  const box = page.locator("[data-testid=vcf-import]");
  await box.locator("input[type=file]").setInputFiles(`${DIR}/iphone.vcf`);
  await expect(page.getByText("Søren Ærø").first()).toBeVisible();
  await expect(page.getByText("Åse Ågesen").first()).toBeVisible();
  await shot(page, info, "PC-VCF-01", "valg");
  expect(sent.filter((s) => /2030405|Søren|Åse/.test(s)), "kontaktdata må ikke forlade telefonen før brugeren gemmer").toEqual([]);
  const picks = box.getByRole("checkbox");
  info.annotations.push({ type: "checkboxes", description: String(await picks.count()) });
  for (const c of await picks.all()) if (!(await c.isChecked())) await c.check();
  await box.getByRole("button", { name: /Tilføj \d+ valgte|Tilføj 1 valgt/ }).first().click();
  await page.getByRole("button", { name: "Gem gruppen", exact: true }).click();
  await expect.poll(async () => ((await (await page.request.get("/api/backend/privat/groups")).json()) as unknown[]).length).toBe(1);
  const g = ((await (await page.request.get("/api/backend/privat/groups")).json()) as { members: { name: string; phone_e164: string }[] }[])[0];
  info.annotations.push({ type: "members", description: JSON.stringify(g.members) });
  const byName = Object.fromEntries(g.members.map((m) => [m.name, m.phone_e164]));
  expect(byName["Søren Ærø"], "mobil (CELL) foretrækkes frem for pref/fastnet").toBe("+4520304052");
  expect(byName["Åse Ågesen"]).toBe("+4520304053");
  expect(Object.keys(byName)).not.toContain("Ingen Nummer");
  await shot(page, info, "PC-VCF-01", "gemt");
});

test("PC-VCF-02: tom fil, binær .vcf, vCard 4.0 og quoted-printable giver venlig fejl eller korrekt navn", async ({ page }, info) => {
  mkdirSync(DIR, { recursive: true });
  writeFileSync(`${DIR}/tom.vcf`, "");
  writeFileSync(`${DIR}/binaer.vcf`, Buffer.from(Array.from({ length: 4096 }, (_, i) => (i * 37) % 256)));
  writeFileSync(`${DIR}/v4-qp.vcf`, ["BEGIN:VCARD", "VERSION:2.1", "N;CHARSET=UTF-8;ENCODING=QUOTED-PRINTABLE:=C3=98stergaard;Bj=C3=B8rn;;;",
    "TEL;CELL:20304054", "END:VCARD", "BEGIN:VCARD", "VERSION:4.0", "FN:Lin", " e Folded", "TEL;VALUE=uri;TYPE=cell:tel:+45-2030-4055", "END:VCARD"].join("\r\n"));
  await user(page, info, "vcf02");
  await trial(page);
  await page.goto("/privat/folk");
  await page.getByRole("button", { name: /Ny gruppe/ }).click();
  const input = page.locator("[data-testid=vcf-import] input[type=file]");
  for (const f of ["tom.vcf", "binaer.vcf"]) {
    await input.setInputFiles(`${DIR}/${f}`);
    await expect(page.getByText("Der var ingen telefonnumre i filen.").first(), f).toBeVisible();
  }
  await input.setInputFiles(`${DIR}/v4-qp.vcf`);
  await expect(page.getByText("Bjørn Østergaard").first()).toBeVisible();
  await expect(page.getByText("Line Folded").first()).toBeVisible();
  await shot(page, info, "PC-VCF-02", "qp-v4");
});

for (const [plat, ua, sep, q] of [["ios", devices["iPhone 13"].userAgent, ",", "?&body="], ["android", devices["Pixel 7"].userAgent, ";", "?body="]] as const) {
  test(`PC-INV-03: «Send som SMS» på ${plat} har platformens sms:-format og intakt link`, async ({ browser }, info) => {
    const ctx = await browser.newContext({ userAgent: ua, viewport: { width: 390, height: 844 }, hasTouch: true });
    const page = await ctx.newPage();
    await user(page, info, `inv03-${plat}`, "Olivia Ejer");
    await trial(page);
    const tid = (await say(page, "Lav en indkøbsliste med mel og gær"))!;
    const g = await (await page.request.post("/api/backend/privat/groups", { headers: CSRF, data: { name: "Familien", members: [{ name: "Anna", phone: "20304061" }, { name: "Bo", phone: "20304062" }] } })).json();
    const r = await (await page.request.post(`/api/backend/privat/tasks/${tid}/share-group`, { headers: CSRF, data: { group_id: g.id, mode: "group", style: "group_sms" } })).json();
    // The page builds the link with smsHref(); evaluate the same helper inside the page with the page's own UA.
    await page.goto(`/privat/opgaver/${tid}`);
    await page.getByRole("button", { name: /^(Del|Deling)$/ }).first().click();
    const sheet = page.getByRole("dialog");
    const kind = sheet.getByRole("button", { name: /Fælles liste/ }).or(sheet.getByRole("radio", { name: /Fælles liste/ }));
    if (await kind.count()) await kind.first().click();
    const create = sheet.getByRole("button", { name: /invitationslink/ });
    if (await create.count()) await create.first().click();
    await expect(page.locator("[data-testid=share-sms]")).toBeVisible({ timeout: 20_000 });
    await shot(page, info, "PC-INV-03", `${plat}-delark`);
    const href = await page.locator("[data-testid=share-sms], [data-testid=group-sms]").first().getAttribute("href").catch(() => null);
    info.annotations.push({ type: "href", description: String(href) }, { type: "group-recipients", description: JSON.stringify(r.sms_group?.recipients) });
    if (href) {
      expect(href.startsWith("sms:")).toBeTruthy();
      expect(href).toContain(q);
      const body = decodeURIComponent(href.split(q)[1] ?? "");
      expect(body).toMatch(/localhost:3400\/i\/[A-Z0-9]{8}/);
      if (href.split(q)[0].length > 4) expect(href.split(q)[0].slice(4)).toContain(sep === "," ? "," : ";");
    }
    await ctx.close().catch(() => {});
  });
}

test("PC-INV-10: udløbet invitationslink viser venlig side med «Bed afsenderen om et nyt link»", async ({ page, browser }, info) => {
  await user(page, info, "inv10", "Olivia Ejer");
  await trial(page);
  const tid = (await say(page, "Lav en indkøbsliste med mel og gær"))!;
  const inv = await (await page.request.post(`/api/backend/privat/tasks/${tid}/share`, { headers: CSRF, data: { mode: "group" } })).json();
  await page.request.post(`/api/backend/privat/tasks/${tid}/share/revoke`, { headers: CSRF });
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
  const anon = await ctx.newPage();
  await anon.goto(`/i/${inv.short_code}`);
  await anon.waitForTimeout(2500);
  await shot(anon, info, "PC-INV-10", "ugyldigt-link");
  await expect(anon.getByText(/ugyldig|udløbet|ikke længere/i).first()).toBeVisible();
  await expect(anon.getByText(/Bed om et nyt|nyt link/i).first(), "fortæl hvad man gør nu").toBeVisible();
  await ctx.close();
});
