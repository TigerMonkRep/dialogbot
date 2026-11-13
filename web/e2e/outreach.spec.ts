import { expect, test } from "@playwright/test";
import { freshOwner, shot } from "./helpers";

/** Admin · Kold e-mail (/app/operator/outreach): the go-live list, the campaign starter and a campaign's result.
 *  Runs against the real stack with OUTREACH_MODE=dry_run and AI_PROVIDER=fake (e2e.yml): nothing is ever sent.
 *  The rows use .example addresses, so the US row is sorted out on the MX lookup – what is shown here is the gate
 *  (blocked market, call list), which is the part that must never break. */
if (process.env.PW_CHROMIUM) test.use({ launchOptions: { executablePath: process.env.PW_CHROMIUM } });
const CSRF = { "x-requested-with": "dialogbot" };

test("operatør: tjekliste, hak et punkt af, kør en CSV-kampagne i tørkørsel", async ({ page }, info) => {
  await freshOwner(page, info);
  await page.goto("/app/operator/outreach");
  await expect(page.getByText("Admin er kun for Dialogbot-operatører.")).toBeVisible();   // a customer never sees it

  expect((await page.request.post("/api/backend/dev/operator/self", { headers: CSRF })).ok()).toBeTruthy();
  await page.goto("/app/operator/outreach");
  await expect(page.getByRole("heading", { name: "Kold e-mail", level: 1 })).toBeVisible();
  await expect(page.getByRole("link", { name: "Kold e-mail" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Inden du går live" })).toBeVisible();
  await expect(page.getByText("Demo-opkaldet kan ringe til de lande, du skriver til")).toBeVisible();
  test.skip(await page.getByText("Slukket", { exact: true }).isVisible(), "kræver OUTREACH_MODE=dry_run på API'et");
  await expect(page.getByText("Tørkørsel", { exact: true })).toBeVisible();

  // a manual point: tick it, see it done, put it back
  const legal = page.getByRole("listitem").filter({ hasText: "godkendt af en jurist" });
  if (await legal.getByRole("button", { name: "Fortryd" }).isVisible()) await legal.getByRole("button", { name: "Fortryd" }).click();
  await legal.getByRole("button", { name: "Det er gjort" }).click();
  await expect(legal.getByRole("button", { name: "Fortryd" })).toBeVisible();
  await legal.getByRole("button", { name: "Fortryd" }).click();
  await expect(legal.getByRole("button", { name: "Det er gjort" })).toBeVisible();

  // the market chooser only offers e-mail markets
  const land = page.getByLabel("Land");
  await expect(land.locator("option[value=DE]")).toHaveAttribute("disabled", "");
  await expect(land.locator("option[value=DK]")).toHaveAttribute("disabled", "");
  await expect(land.locator("option[value=US]")).not.toHaveAttribute("disabled", "");
  await land.selectOption("UK");
  await expect(page.getByText("Storbritannien: Kun selskaber")).toBeVisible();
  await shot(page, info, "outreach-oversigt");

  const tag = `${info.project.name}-${Date.now()}`.replace(/[^a-z0-9-]/gi, "").toLowerCase();
  await page.getByText("Har du selv en liste? Indsæt en CSV").click();
  await page.getByLabel("CSV med virksomheder").fill([
    "company_name,email,country,city,niche,registration_number",
    `Müller Sanitär GmbH,info@mueller-${tag}.example,DE,Hamburg,plumber,`,
    `Nordjysk VVS ApS,kontakt@vvs-${tag}.example,DK,Aalborg,plumber,25632710`,
    `Brightwater Plumbing LLC,office@brightwater-${tag}.example,US,Austin,plumber,`,
  ].join("\n"));
  await page.getByRole("button", { name: "Tjek listen og skriv e-mails" }).click();
  await page.waitForURL(/batch=csv-/);
  const detail = page.locator("#kampagne");
  await expect(detail.getByRole("listitem").filter({ hasText: "Müller Sanitär GmbH" }).getByText("Blokeret")).toBeVisible();
  await expect(detail.getByText(/opt-in market/)).toBeVisible();
  await expect(detail.getByRole("listitem").filter({ hasText: "Nordjysk VVS ApS" }).getByText("På ringelisten")).toBeVisible();
  await expect(detail.getByRole("listitem").filter({ hasText: "Brightwater Plumbing LLC" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ringeliste (Danmark)" })).toBeVisible();
  await shot(page, info, "outreach-kampagne");
});
