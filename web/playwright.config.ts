import { defineConfig, devices } from "@playwright/test";

/** E2E journeys against a running stack: Next (BASE_URL, default :3000) → FastAPI + worker + PostgreSQL.
 *  Every journey runs at 1440 px (desktop reference) and 390 px (mobile reference). */
export default defineConfig({
  testDir: "./e2e",
  // e2e/qa/** is the QA scenario catalogue; CI runs it in its own sharded job (.github/workflows/e2e.yml qa-catalog),
  // so the journeys job sets PW_SKIP_QA=1. Locally: `npx playwright test e2e/qa`.
  // PW_QA_SKIP_PWA=1 leaves out e2e/qa/pwa, which needs PW_EXPERIMENTAL_SERVICE_WORKER_NETWORK_EVENTS=1 and runs in its
  // own step. That flag crashes Chromium now and then when the whole catalogue runs with it (see e2e.yml qa-catalog).
  testIgnore: [...(process.env.PW_SKIP_QA ? ["qa/**"] : []), ...(process.env.PW_QA_SKIP_PWA ? ["qa/pwa/**"] : [])],
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:3000",
    locale: "da-DK",
    timezoneId: "Europe/Copenhagen",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    // Own voice (journey 24) records from the microphone: Chromium's fake device supplies audio, no prompt.
    launchOptions: { args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
      `--use-file-for-fake-audio-capture=${__dirname}/e2e/fixtures/speech-like.wav`] },
    permissions: ["microphone"],
  },
  projects: [
    { name: "desktop-1440", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobil-390", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, isMobile: false, hasTouch: true } },
  ],
});
