import { expect, test } from "@playwright/test";

// Smoke test: the shell loads, the brand renders, and every nav route is present
// and navigable.
test("app shell loads with all navigation routes", async ({ page }) => {
  await page.goto("/");

  await expect(page).toHaveTitle(/QE Copilot/);
  await expect(page.getByText("QE Copilot")).toBeVisible();

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

  // Navigate to a feature route and confirm its heading renders.
  await nav.getByRole("link", { name: "Test Generator" }).click();
  await expect(
    page.getByRole("heading", { name: "Test Generator" }),
  ).toBeVisible();
});
