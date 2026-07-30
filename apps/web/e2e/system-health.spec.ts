import { expect, test } from "@playwright/test";

import { signIn } from "./helpers";

// T7: the System Health page renders live data fetched from the API.

test("system health renders every component with a live status", async ({
  page,
}) => {
  await signIn(page);

  await page
    .getByRole("navigation", { name: "Primary" })
    .getByRole("link", { name: "System Health" })
    .click();

  await expect(page.getByRole("heading", { name: "System Health" })).toBeVisible();

  for (const component of [
    "api",
    "database",
    "redis",
    "queue",
    "workers",
    "scheduler",
  ]) {
    const card = page.getByTestId(`health-component-${component}`);
    await expect(card).toBeVisible();
    await expect(card.getByTestId("status-badge")).toHaveAttribute(
      "data-status",
      /healthy|degraded|unhealthy/,
    );
  }

  // Values are measured, not placeholders: the database card carries a latency.
  await expect(page.getByTestId("health-component-database")).toContainText("ms");
  await expect(
    page.getByTestId("health-component-api").getByText(/Uptime/i),
  ).toBeVisible();
});

test("the page reports a real overall status and a check timestamp", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/system-health");

  await expect(page.getByRole("heading", { name: "System Health" })).toBeVisible();
  await expect(page.getByText(/Checked at /)).toBeVisible();

  const overall = page.getByTestId("status-badge").first();
  await expect(overall).toHaveAttribute("data-status", /healthy|degraded/);
});
