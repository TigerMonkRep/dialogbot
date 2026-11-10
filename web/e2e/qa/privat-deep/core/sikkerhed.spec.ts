import { expect, test } from "@playwright/test";
import { shot, stackUp, user } from "./pk";

/** PC-SEC-03: når Privat-API'et svarer 403 privat_not_enabled / 404 (lukket pilot, flag slået fra, deploy uden
 *  backend), falder web stille tilbage til in-browser-simuleringen. Brugeren må aldrig tro, at opkald, betaling eller
 *  invitationer er udført: «Simuleret» skal være synligt på hver skærm – også på mobil (390 px). */
test.beforeEach(async ({ request }) => { test.skip(!(await stackUp(request)), "kræver Privat-stakken på :8400"); });

test("PC-SEC-03: API slået fra → simulering skal være tydeligt mærket på alle skærme", async ({ page }, info) => {
  await user(page, info, "sec03", "Mette Hansen", false);
  await page.route("**/api/backend/privat/**", (r) => r.fulfill({ status: 403, contentType: "application/json",
    body: JSON.stringify({ code: "privat_not_enabled", message: "Dialogbot Privat er ikke slået til", field_errors: [] }) }));
  const seen: Record<string, boolean> = {};
  const lies: string[] = [];
  for (const path of ["/privat/dag", "/privat/opgaver", "/privat/samtale", "/privat/butik", "/privat/folk", "/privat/konto"]) {
    await page.goto(path);
    await page.waitForTimeout(2500);
    // Efter F-PK-03-rettelsen: en indlogget bruger får en ærlig fejl (errors.notEnabled/unavailable) i stedet for simuleringen.
    const sim = page.getByText(/Simuleret|simulering|eksempeldata|Demodata|ikke slået til|ikke åbnet|ikke tilgængelig/i);
    seen[path] = (await sim.count()) > 0 && (await sim.first().isVisible().catch(() => false));
    if (await page.getByText(/1 af 10 opkald|14 d$/).count()) lies.push(path);
    await shot(page, info, "PC-SEC-03", path.split("/").pop()!);
  }
  info.annotations.push({ type: "simuleret-synligt", description: JSON.stringify(seen) });
  expect(lies, "ingen falsk prøveperiode/opkaldskvote, når API'et er slået fra").toEqual([]);
  expect(seen, "«Simuleret»/eksempeldata skal være synligt på hver Privat-skærm, når API'et er slået fra").toEqual(
    Object.fromEntries(Object.keys(seen).map((k) => [k, true])));
});
