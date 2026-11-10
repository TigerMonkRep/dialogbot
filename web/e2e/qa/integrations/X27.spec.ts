import { expect, test } from "@playwright/test";
import { freshOwner, shot } from "../../helpers";

/* X27 (integrations-qa, bølge 2 / M2): Google-kalenderens OAuth-callback sender kunden tilbage til
 * /app/settings/integrationer?error=<kode>&connector=google_calendar. Afvist samtykke og manglende scope skal
 * forklares i ord – ikke vise den tekniske kode. Simuleret forbind-runde (fake-adaptere) skal lande grønt. */

for (const code of ["oauth_denied", "oauth_scope_missing", "oauth_state_expired", "oauth_invalid_grant"]) {
  test(`X27 · callback-fejl ${code} vises i ord`, async ({ page }, info) => {
    await freshOwner(page, info);
    await page.goto(`/app/settings/integrationer?error=${code}&connector=google_calendar`);
    const alert = page.getByText(/Google Kalender blev ikke forbundet/);
    await expect(alert).toBeVisible();
    await shot(page, info, `x27-callback-${code}`);
    await expect(alert).not.toContainText(code);
  });
}

