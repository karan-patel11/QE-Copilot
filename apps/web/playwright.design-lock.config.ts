import { defineConfig, devices } from "@playwright/test";

// The design-lock guards run against a **dev** server, deliberately.
//
// /dev/tokens is the only surface rendering the dashed AI-action pill today, and
// middleware.ts returns a real 404 for /dev/* in a production build — which is
// correct, and means the default playwright.config.ts (which runs
// `next build && next start`) can never exercise guard (b). Rather than weaken
// that config so a design check can pass, the guards get their own.
//
// `reuseExistingServer` is on so this attaches to a dev server that is already
// up instead of starting a second one on the same port.
const PORT = Number(process.env.WEB_PORT ?? 3200);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  testMatch: /design-lock\.spec\.ts/,
  timeout: 60_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: "list",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: {
    command: `npm run dev -- --port ${PORT}`,
    url: `${BASE_URL}/dev/tokens`,
    timeout: 180_000,
    reuseExistingServer: true,
  },
});
