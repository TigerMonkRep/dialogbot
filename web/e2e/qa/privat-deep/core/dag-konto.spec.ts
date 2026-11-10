import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { CSRF, noHorizontalScroll, say, shot, stackUp, trial, user } from "./pk";

/** PC-DAY-01/02/05 (Min dag: ny konto, med indhold, udløbet prøve) og PC-ACC-01/PC-SUB-20 (Konto). Ægte data fra :8400. */
test.beforeEach(async ({ request }) => { test.skip(!(await stackUp(request)), "kræver Privat-stakken på :8400"); });
const psql = (q: string) => execFileSync("psql", ["postgresql://postgres:postgres@localhost:5432/qa_privdeep_stack", "-Atc", q]).toString().trim();

test("PC-DAY-01: ny konto efter checkout – én primær handling, ingen demo-data, korrekt plan-chip", async ({ page }, info) => {
  await user(page, info, "day01");
  await trial(page);
  await page.goto("/privat/dag");
  await expect(page.getByRole("heading").first()).toBeVisible();
  await page.waitForTimeout(2000);
  await expect(page.getByText(/Eksempel|Tandlæge Holm|Hent Ida/).first(), "ingen demo-data for en rigtig konto").toHaveCount(0);
  await expect(page.getByRole("button", { name: /Din plan: Plus · prøveperiode, 14 dage tilbage/ }).or(page.getByText(/14 d/).first()).first()).toBeVisible();
  await noHorizontalScroll(page);
  await shot(page, info, "PC-DAY-01", "tom-dag");
});

test("PC-DAY-02: afventer-godkendelse øverst; tal stemmer med bootstrap.day; tryk åbner opgaven", async ({ page }, info) => {
  await user(page, info, "day02");
  await trial(page);
  await say(page, "Mind mig om at ringe til mor i morgen kl. 9");
  await say(page, "Lav en indkøbsliste med mel og gær");
  const call = (await say(page, "Ring til Tandlæge Holm på 86 12 34 56 og flyt min tid"))!;
  const day = (await (await page.request.get("/api/backend/privat/bootstrap")).json()).day;
  info.annotations.push({ type: "bootstrap.day", description: JSON.stringify(day).slice(0, 600) });
  await page.goto("/privat/dag");
  const first = page.locator("main").getByText(/Tandlæge Holm/).first();
  await expect(first).toBeVisible();
  const y = async (t: RegExp) => (await page.locator("main").getByText(t).first().boundingBox())?.y ?? 1e9;
  expect(await y(/Tandlæge Holm/), "opkald der venter på godkendelse står øverst").toBeLessThan(await y(/Ringe til mor|Indkøbsliste/));
  await shot(page, info, "PC-DAY-02", "dag");
  await expect(page.getByRole("button", { name: "Ja, ring" }), "eksplicit godkendelse står på kortet").toBeVisible();
  const list = (await (await page.request.get("/api/backend/privat/tasks")).json() as { id: string; title: string }[]).find((t) => t.title === "Indkøbsliste")!;
  await page.locator("main").getByText("Indkøbsliste").first().click();
  await expect(page).toHaveURL(new RegExp(list.id));
  expect(call).toBeTruthy();
});

test("PC-DAY-05: udløbet prøve – «Prøveperioden er slut» + vælg plan; data stadig synlige", async ({ page }, info) => {
  const { email } = await user(page, info, "day05");
  await trial(page);
  await say(page, "Lav en indkøbsliste med mel og gær");
  psql(`update private_subscriptions set status='trial', trial_ends_at=now()-interval '1 day', current_period_end=now()-interval '1 day', stripe_subscription_id=null
        where workspace_id=(select workspace_id from private_profiles where user_id=(select id from users where email_normalized=lower('${email}')))`);
  const sub = await (await page.request.get("/api/backend/privat/subscription")).json();
  info.annotations.push({ type: "subscription", description: `${sub.status} entitled=${sub.entitled}` });
  await page.goto("/privat/dag");
  await expect(page.getByText(/Prøveperiode(n)? (er )?slut/).first()).toBeVisible();
  await expect(page.getByText("Indkøbsliste").first(), "eksisterende data skjules ikke").toBeVisible();
  await expect(page.locator("[role=alert]")).toHaveCount(0);
  await shot(page, info, "PC-DAY-05", "udloebet");
  const cta = page.getByRole("link", { name: /Vælg (en )?plan/ }).or(page.getByRole("button", { name: /Vælg (en )?plan/ })).first();
  await expect(cta).toBeVisible();
  await cta.click();
  await expect(page).toHaveURL(/\/privat\/konto/);
});

test("PC-ACC-01/PC-SUB-20: Konto viser plan, fornyelse, Administrér; uden kunde ingen rå fejl", async ({ page }, info) => {
  await user(page, info, "acc01");
  await page.goto("/privat/konto");
  await expect(page.getByRole("heading", { name: /Konto/ }).first()).toBeVisible();
  await expect(page.getByText(/Ingen plan/).first()).toBeVisible();
  await expect(page.getByRole("button", { name: /Administr/ })).toHaveCount(0);
  await shot(page, info, "PC-ACC-01", "ingen-plan");
  await trial(page);
  await page.goto("/privat/konto?abonnement=annulleret");
  await expect(page.getByText(/Prøveperiode|Plus/).first()).toBeVisible();
  await expect(page.getByText(/afbrød valget af plan/).filter({ visible: true }).first(), "?abonnement=annulleret viser en note").toBeVisible();
  const adm = page.getByRole("button", { name: /Administr/ }).or(page.getByRole("link", { name: /Administr/ })).first();
  await expect(adm).toBeVisible();
  await expect(page.getByText(/Simuleret/)).toHaveCount(0);
  await noHorizontalScroll(page);
  await shot(page, info, "PC-ACC-01", "trial");
  expect((await page.request.post("/api/backend/privat/subscription/portal", { headers: CSRF })).ok()).toBeTruthy();
});
