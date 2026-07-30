import { defineConfig, devices } from "@playwright/test";

// Chromium is pre-installed in CI/dev images at PLAYWRIGHT_BROWSERS_PATH; the
// pinned @playwright/test version matches that browser build, so no download.
const PORT = Number(process.env.PORT ?? 3100);
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: "./e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "list" : "line",
  use: {
    baseURL: BASE_URL,
    trace: "on-first-retry",
  },
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
  ],
  webServer: {
    command: `npm run build && npm run start -- --port ${PORT}`,
    url: BASE_URL,
    timeout: 180_000,
    reuseExistingServer: !process.env.CI,
  },
});
