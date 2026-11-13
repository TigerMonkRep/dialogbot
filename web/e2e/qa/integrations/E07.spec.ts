import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";

/* QA E07 (integrations-qa): booking communication templates – «Request receipt, confirmed appointment, reminder,
 * proposed change, rescheduled, cancelled and owner-attention variants; delivery failure.» DB-018: the preview is a
 * preview; nothing is sent. Page: /app/aftaler/beskeder (linked from «Aftaler»).
 * Since E07 auto-send (2026-11-13): the page says what goes out automatically and holds the SMS opt-in (off by default,
 * with the usage note); turning it on and off is saved and audited by the API. */
const EVID = "../qa/evidence/E07";
const LABELS = ["Anmodning modtaget", "Aftale bekræftet", "Påmindelse", "Forslag til ny tid", "Aftale flyttet", "Aftale aflyst",
  "Kræver din opmærksomhed", "Levering fejlede"];

test("E07 · alle 8 beskeder om aftaler kan ses på 8 sprog som SMS og e-mail – uden at noget sendes", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  const mailbox = async () => (await (await page.request.get("/api/backend/dev/mailbox")).json()).items.length as number;
  const before = await mailbox();

  await page.goto("/app/aftaler");
  await page.getByRole("link", { name: /Beskeder til kunden/ }).click();
  await expect(page).toHaveURL(/\/app\/aftaler\/beskeder/);
  await expect(page.getByRole("heading", { level: 1, name: "Beskeder om aftaler" })).toBeVisible();
  await expect(page.getByText("Kun forhåndsvisning: intet bliver sendt herfra.")).toBeVisible();
  const nav = page.getByRole("navigation", { name: "Vælg besked" });
  for (const l of LABELS) await expect(nav.getByRole("link", { name: new RegExp(l) })).toBeVisible();

  // 1) customer message: SMS in the business's name, ≤ 160 characters, and the e-mail rendered in a sandboxed frame
  const sms = page.getByTestId("sms-preview");
  await expect(sms).toContainText("Vi har modtaget din forespørgsel");
  await expect(sms).toContainText(/Vh E2E /);
  await expect(page.getByText(/\d+ tegn · 1 SMS · GSM-7/)).toBeVisible();
  const frame = page.frameLocator('iframe[title="Forhåndsvisning af e-mailen"]');
  await expect(frame.getByRole("heading", { name: "Vi har modtaget din forespørgsel" })).toBeVisible();
  await page.screenshot({ path: `${EVID}/${info.project.name}-da.png`, fullPage: true });

  // 2) every variant opens; the owner variants have no SMS and an e-mail from Dialogbot
  for (const l of LABELS) {
    await nav.getByRole("link", { name: new RegExp(l) }).click();
    await expect(nav.getByRole("link", { name: new RegExp(l) })).toHaveAttribute("aria-current", "page");
    await expect(page.getByTestId("email-subject")).not.toBeEmpty();
  }
  await expect(page.getByText("Sendes kun som e-mail til jer.")).toBeVisible();
  await expect(frame.getByText("En besked kunne ikke leveres")).toBeVisible();

  // 3) the eight languages
  const langs = page.getByRole("navigation", { name: "Sprog" });
  for (const [name, sign] of [["Deutsch", "Freundliche Grüße"], ["English", "Kind regards"], ["Español", "Saludos"], ["Français", "Cordialement"],
    ["Italiano", "Cordiali saluti"], ["Norsk", "Mvh"], ["Svenska", "Mvh"], ["Dansk", "Vh"]] as const) {
    await langs.getByRole("link", { name }).click();
    await expect(langs.getByRole("link", { name })).toHaveAttribute("aria-current", "true");
    await nav.getByRole("link", { name: /Aftale bekræftet/ }).click();
    await expect(nav.getByRole("link", { name: /Aftale bekræftet/ })).toHaveAttribute("aria-current", "page");
    await expect(sms).toContainText(sign);
  }
  await langs.getByRole("link", { name: "Deutsch" }).click();
  await expect(langs.getByRole("link", { name: "Deutsch" })).toHaveAttribute("aria-current", "true");
  await nav.getByRole("link", { name: /Aftale aflyst/ }).click();
  await expect(nav.getByRole("link", { name: /Aftale aflyst/ })).toHaveAttribute("aria-current", "page");
  await expect(sms).toContainText("wurde abgesagt");
  await expect(frame.getByText("Ihr Termin wurde abgesagt")).toBeVisible();
  await page.screenshot({ path: `${EVID}/${info.project.name}-de.png`, fullPage: true });

  // 4) what is sent automatically, and the SMS opt-in: off by default, says it counts in the usage, saved on change
  await langs.getByRole("link", { name: "Dansk" }).click();
  await expect(langs.getByRole("link", { name: "Dansk" })).toHaveAttribute("aria-current", "true");
  await expect(page.getByRole("heading", { level: 2, name: "Sådan sendes beskederne" })).toBeVisible();
  await expect(page.getByText(/E-mail til kunden: automatisk/)).toBeVisible();
  await expect(page.getByText(/Påmindelse: 24 timer før aftalen/)).toBeVisible();
  const smsSwitch = page.getByRole("switch", { name: "Send også beskederne som SMS" });
  await expect(smsSwitch).toHaveAttribute("aria-checked", "false");
  await expect(page.getByText(/Hver SMS tæller i jeres forbrug/)).toBeVisible();
  await expect(page.getByTestId("sms-state")).toHaveText("SMS er slået fra");
  await smsSwitch.click();
  await expect(smsSwitch).toHaveAttribute("aria-checked", "true");
  await expect(page.getByTestId("sms-state")).toHaveText("SMS er slået til");
  await page.reload();
  await expect(page.getByRole("switch", { name: "Send også beskederne som SMS" })).toHaveAttribute("aria-checked", "true");
  await page.screenshot({ path: `${EVID}/${info.project.name}-sending.png`, fullPage: true });
  await page.getByRole("switch", { name: "Send også beskederne som SMS" }).click();
  await expect(page.getByTestId("sms-state")).toHaveText("SMS er slået fra");

  // 5) the preview itself sent nothing: the API says so and the mail log is unchanged
  const preview = await (await page.request.get(`/api/backend/workspaces/${wsId}/bookings/messages?lang=sv`)).json();
  expect(preview.sends_nothing).toBe(true);
  expect(preview.items).toHaveLength(8);
  expect(preview.sending.sms_enabled).toBe(false);
  expect(await mailbox()).toBe(before);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBeTruthy();
});
