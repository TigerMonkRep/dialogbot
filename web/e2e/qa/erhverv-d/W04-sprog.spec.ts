import { expect, test } from "@playwright/test";
import { serve } from "../../helpers";
import { noHorizontalScroll, smsCodeFor } from "../erhverv-p1a/p1a-helpers";
import { closeAll, EVID, forwardPublicApi, ownClientIp, SITE, SITE_PORT, uniquePhone, widgetWorkspace, type Widget } from "./d-helpers";

/* The chat widget in the visitor's language (Fürster 13/11: the widget follows the language like the rest of the
 * platform). The business's site is in English (<html lang="en">), the visitor's browser is German: the widget follows
 * the page – launcher, frame, «Be contacted» and W04's code step with the real (simulated) SMS code. */
let w: Widget | null = null;
test.afterEach(async () => { if (w) await closeAll(w.servers); w = null; });

test("W04 · widgetten på engelsk: launcher, kontaktformular, kodetrin og bekræftelse", async ({ page, browser }, info) => {
  w = await widgetWorkspace(page, info);
  await closeAll(w.servers); // the same site, now in English
  w.servers.push(await serve(SITE_PORT, `<!doctype html><html lang="en"><head><title>Fjord Floors</title></head><body><h1>Fjord Floors</h1>${w.embed}</body></html>`));
  const ctx = await browser.newContext({ viewport: page.viewportSize() ?? undefined, locale: "de-DE", timezoneId: "Europe/Copenhagen" });
  await forwardPublicApi(ctx);
  await ownClientIp(ctx);
  const v = await ctx.newPage();
  await v.goto(`${SITE}/`);
  await v.getByRole("button", { name: "Open chat" }).click();
  const chat = v.frameLocator('iframe[title="Chat with the business\'s digital assistant"]');
  await expect(chat.locator("header strong")).toHaveText("Digital assistant");
  await expect(chat.locator(".notice")).toContainText("You are writing with an AI assistant.");
  await expect(chat.locator("textarea")).toHaveAttribute("placeholder", "Write your message…");
  await chat.getByRole("button", { name: "Be contacted by a member of staff" }).click();
  const form = chat.locator("form.contact");
  await expect(form.getByLabel("When may we call?").locator("option").first()).toHaveText("No preference");
  await expect(form.getByLabel("When may we call?").locator("option").nth(1)).toHaveText(/As soon as possible/);
  const phone = uniquePhone();
  await form.getByLabel("Name").fill("Henry Williams");
  await form.getByLabel("Phone").fill(phone.display);
  await form.getByRole("button", { name: "Send" }).click();
  await expect(form.locator(".err")).toHaveText("Tick the box so the business may contact you.");
  await form.getByLabel("The business may contact me about my enquiry.").check();
  await form.getByRole("button", { name: "Send" }).click();
  const code = chat.locator(".code-step");
  await expect(code.locator("strong")).toHaveText("Confirm your number");
  await expect(code.locator(".hint")).toHaveText(`We have sent a 6-digit code to ${phone.e164.slice(3, 5)} •• •• ${phone.e164.slice(-2)}. It is valid for 10 minutes.`);
  await expect(code.getByRole("button", { name: /Send new code \(\d+ s\)/ })).toBeDisabled();
  await code.getByLabel("Code from text message").fill("12");
  await code.getByRole("button", { name: "Confirm" }).click();
  await expect(code.locator(".err")).toHaveText("Enter the 6 digits from the text message.");
  await code.getByLabel("Code from text message").fill(await smsCodeFor(phone.e164));
  await v.screenshot({ path: `${EVID("W04")}/${info.project.name}-engelsk-kodetrin.png` });
  await code.getByRole("button", { name: "Confirm" }).click();
  const ok = chat.locator("li.msg.system-ok").last();
  await expect(ok).toContainText("Thank you, Henry Williams! The business will contact you as soon as possible.");
  await expect(ok.getByRole("link", { name: "Cancel the call back or change your choices" })).toBeVisible();
  await noHorizontalScroll(v);
  await ctx.close();
});
