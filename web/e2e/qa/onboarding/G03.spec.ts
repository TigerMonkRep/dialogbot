import { expect, test } from "@playwright/test";
import { freshOwner } from "../../helpers";
import { api, snap } from "./e2b";

/* QA G03 (E2B) – /app/setup/tasks/:taskId. Krav: "Reusable guided wrapper around canonical editors; example, explanation,
 * preview, save, skip and return." Byggevejledningen: trin 1–3 er selve editorerne; «Jeg gør resten senere» = spring/return. */
const ID = "G03";

test("G03 · opgave-URL fra API'et kan åbnes; «Jeg gør resten senere» returnerer til I dag og husker valget", async ({ page }, info) => {
  const { wsId } = await freshOwner(page, info);
  await page.context().clearCookies({ name: "db_setup_later" });
  const plan = (await api(page).get(`/workspaces/${wsId}/setup/plan`)).body;
  const key = (plan?.tasks ?? [])[0]?.key ?? "business.profile";
  const res = await page.goto(`/app/setup/tasks/${key}`);
  await snap(page, ID, info, "task-url");
  test.info().annotations.push({ type: "route", description: `${res?.status()} → ${page.url()}` });
  expect.soft(res?.status() ?? 0, `/app/setup/tasks/${key} svarer ${res?.status()}`).toBeLessThan(400);
  // skip & return in the byggevejledning
  await page.goto("/opsaetning/1");
  const later = page.getByRole("link", { name: "Jeg gør resten senere" });
  await snap(page, ID, info, "trin1-senere-link");
  await expect(later, "«Jeg gør resten senere» er skjult på mobil i trin 1 – ingen vej ud af opsætningen").toBeVisible();
  await later.click();
  await expect(page).toHaveURL(/\/app(\?|$)/);
  await page.goto("/app");
  await expect(page).toHaveURL(/\/app$/);
  await expect(page.getByText(/Opsætningen er ikke færdig/)).toBeVisible();
  await snap(page, ID, info, "senere");
});
