import { expect, test } from "@playwright/test";
import { CSRF, campaignOwner, evid, newCampaign } from "./e2c-helpers";

/* C04 /app/campaigns/:id/mapping: "Contact fields, language, permission evidence and approved script-variable mapping."
   Built: automatic header mapping (8 UI languages), consent evidence per import (required for businesses too),
   {navn}/{virksomhed} in the opening. Not built: manual column mapping, contact language, variable mapping UI. */

test("C04 · samtykke er påkrævet – også for virksomheder – og gemmes pr. kontakt", async ({ page }, info) => {
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C04 ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await expect(page.getByText("markedsføringsloven § 10", { exact: false })).toBeVisible();
  await page.getByLabel("Eller indsæt listen").fill("Kontaktperson;Mobil;Virksomhed\nMette Hansen;20304050;Hansen Byg ApS");
  const submit = page.getByRole("button", { name: "Tilføj kontakter" });
  const consent = page.getByLabel("Hvor og hvornår har de sagt ja til at blive ringet op?");
  await consent.fill("ja");
  await expect(submit).toBeDisabled(); // < 5 chars
  // the API refuses too (not only the button)
  const r = await page.request.post(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts/import`, { headers: CSRF, data: { csv: "Bo;22334455", kind: "business", consent_source: "  ja " } });
  expect(r.status()).toBe(422);
  expect((await r.json()).field_errors[0].field).toBe("consent_source");
  await consent.fill("Bad om opkald på messen i Herning, marts 2026");
  await page.getByRole("radio", { name: "Privatpersoner" }).check();
  await submit.click();
  await expect(page.getByText("1 kontakter tilføjet")).toBeVisible();
  const [x] = (await (await page.request.get(`/api/backend/workspaces/${wsId}/campaigns/${c.id}/contacts`)).json()).items;
  // headers «Kontaktperson;Mobil;Virksomhed» are mapped without asking
  expect([x.name, x.phone, x.company, x.kind, x.consent_source]).toEqual(["Mette Hansen", "+4520304050", "Hansen Byg ApS", "consumer", "Bad om opkald på messen i Herning, marts 2026"]);
  await expect(page.getByText("Privat (samtykke)")).toHaveAttribute("title", "Bad om opkald på messen i Herning, marts 2026");
  await page.screenshot({ path: evid("C04", info, "samtykke"), fullPage: true });
});

test("C04 · krav: kolonne-mapping, kontaktens sprog og godkendt variabel-mapping (ikke bygget)", async ({ page }, info) => {
  test.info().annotations.push({ type: "not-implemented", description: "C04: no mapping step; no per-contact language; variables limited to {navn}/{virksomhed} with no mapping UI" });
  const { wsId } = await campaignOwner(page, info);
  const c = await newCampaign(page.request, wsId, `QA-E2C C04 mapping ${Date.now()}`);
  await page.goto(`/app/kampagner/${c.id}`);
  await page.screenshot({ path: evid("C04", info, "ingen-mapping"), fullPage: true });
  await expect(page.getByRole("combobox", { name: /kolonne|sprog/i })).toHaveCount(1, { timeout: 3_000 });
});
