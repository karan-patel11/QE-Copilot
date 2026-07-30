import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

// These specs drive the real stack: the app calls a running API, which reads
// Postgres and Redis. Bring it up with `docker compose up -d` first.

test("unauthenticated visitors are sent to the login page", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Primary" })).toHaveCount(0);
});

test("app shell loads with all navigation routes after signing in", async ({
  page,
}) => {
  await signIn(page);

  await expect(page).toHaveTitle(/QE Copilot/);

  const nav = page.getByRole("navigation", { name: "Primary" });
  for (const label of [
    "Overview",
    "CI Failures",
    "Test Generator",
    "Defect Triage",
    "Knowledge Base",
    "Evaluations",
    "Analytics",
    "Integrations",
    "System Health",
    "Administration",
  ]) {
    await expect(nav.getByRole("link", { name: label })).toBeVisible();
  }

  // Every placeholder route stays reachable behind the gate.
  await nav.getByRole("link", { name: "Test Generator" }).click();
  await expect(
    page.getByRole("heading", { name: "Test Generator" }),
  ).toBeVisible();
});

test("signing out returns the user to the login page", async ({ page }) => {
  await signIn(page);

  await page.getByRole("button", { name: "Sign out" }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("button", { name: "Sign in" })).toBeVisible();
});
