import { expect, type APIRequestContext, type Page, type TestInfo } from "@playwright/test";

export const DEMO_PASSWORD = process.env.SEED_DEMO_PASSWORD ?? "DemoPass-2026x";
export const PREVIEW_CODE = process.env.PREVIEW_ACCESS_CODES?.split(",")[0] ?? "E2E-PREVIEW-2026";
/** A stand-in for a customer's own website on another origin (see serve()). */
export const CUSTOMER_SITE = "http://localhost:4000";
export const SEEDED = { owner: "owner@fjordgulv.example", admin: "admin@fjordgulv.example", staff: "staff@fjordgulv.example", reader: "reader@fjordgulv.example" };
const CSRF = { "x-requested-with": "dialogbot" };

export const uniqueEmail = (tag: string, info: TestInfo) => `e2e-${tag}-${info.project.name}-${Date.now()}@example.com`;

/** Full-page screenshot kept as a CI artifact (e2e-screens/<project>/<name>.png). */
export async function shot(page: Page, info: TestInfo, name: string) {
  await page.evaluate(() => document.fonts.ready);
  const path = `e2e-screens/${info.project.name}/${name}.png`;
  await page.screenshot({ path, fullPage: true });
  await info.attach(name, { path, contentType: "image/png" });
}

export async function login(page: Page, email: string, password = DEMO_PASSWORD) {
  await page.goto("/login");
  await page.getByLabel("E-mail").fill(email);
  await page.getByLabel("Adgangskode", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Log ind" }).click();
  await page.waitForURL((u) => !u.pathname.startsWith("/login"));
}

/** Newest simulated mail for the logged-in user whose subject matches; retries while the worker delivers. */
export async function latestMailLink(request: APIRequestContext, pattern: RegExp): Promise<string> {
  let link: string | undefined;
  await expect.poll(async () => {
    const r = await request.get("/api/backend/dev/mailbox");
    if (!r.ok()) return undefined;
    const body = (await r.json()) as { items: { body_text: string }[] };
    for (const m of body.items) { const hit = m.body_text.match(pattern); if (hit) { link = hit[0]; return link; } }
    return undefined;
  }, { timeout: 30_000, intervals: [500, 1000, 2000] }).toBeTruthy();
  return link!;
}

/** Registers, logs in (sets the httpOnly cookie in this page's context), verifies e-mail and creates a workspace. */
export async function freshOwner(page: Page, info: TestInfo, intent = "reception") {
  const email = uniqueEmail("owner", info);
  const r = await page.request.post("/api/backend/auth/register", { headers: CSRF, data: { email, password: DEMO_PASSWORD, display_name: "E2E Ejer", signup_intent: intent } });
  expect(r.status()).toBe(201);
  expect((await page.request.post("/api/auth/login", { headers: CSRF, data: { email, password: DEMO_PASSWORD } })).ok()).toBeTruthy();
  const token = (await latestMailLink(page.request, /token=[\w-]+/)).split("=")[1];
  expect((await page.request.post("/api/backend/auth/verify-email", { headers: CSRF, data: { token } })).ok()).toBeTruthy();
  const ws = await (await page.request.post("/api/backend/workspaces", { headers: CSRF, data: { name: `E2E ${info.project.name} ${Date.now()}`, product_intent: intent } })).json();
  await page.request.post("/api/auth/workspace", { headers: CSRF, data: { workspace_id: ws.id } });
  return { email, wsId: ws.id as string };
}

/** Minimal static web server for a fake customer website on another origin. */
export async function serve(port: number, body: string): Promise<import("node:http").Server> {
  const { createServer } = await import("node:http");
  const server = createServer((_req, res) => { res.writeHead(200, { "content-type": "text/html; charset=utf-8" }); res.end(body); });
  await new Promise<void>((resolve) => server.listen(port, "127.0.0.1", resolve));
  return server;
}
