import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

// T8: the full Phase 1 flow — sign in, read the Overview, cross to System
// Health — against a live API.

test("login to overview to system health", async ({ page }) => {
  await signIn(page);

  // Overview renders real numbers from the API, not placeholder copy.
  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  const stats = page.getByTestId("overview-stats");
  await expect(stats).toBeVisible();
  await expect(stats.getByText("Projects")).toBeVisible();
  await expect(stats.getByText("Workers online")).toBeVisible();
  await expect(page.getByText("Placeholder — coming in a later phase.")).toHaveCount(
    0,
  );

  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "System Health" })
    .click();

  await expect(page.getByRole("heading", { name: "System Health" })).toBeVisible();
  await expect(page.getByTestId("health-component-database")).toBeVisible();
});

test("overview shows an empty state for a brand-new organisation", async ({
  page,
}) => {
  // A freshly provisioned user has no projects, which must read as "empty",
  // not as an error and not as a permanent spinner.
  await signIn(page);

  await expect(page.getByRole("heading", { name: "Overview" })).toBeVisible();
  await expect(page.getByTestId("loading-state")).toHaveCount(0);
  await expect(page.getByTestId("error-state")).toHaveCount(0);
  await expect(page.getByTestId("empty-state").first()).toContainText("No ");
});

test("administration lists the signed-in user", async ({ page }) => {
  const email = await signIn(page);

  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "Administration" })
    .click();

  await expect(
    page.getByRole("heading", { name: "Administration" }),
  ).toBeVisible();
  // A dev-provisioned engineer cannot read users, so the page must say so
  // rather than surfacing a raw 403.
  await expect(
    page.getByText("Your role does not include permission to view users."),
  ).toBeVisible();
  await expect(page.getByText(email)).toBeVisible();
});
