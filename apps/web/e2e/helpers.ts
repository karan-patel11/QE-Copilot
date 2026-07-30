import { expect, type Page } from "@playwright/test";

// A unique address per test run, so tests never contend over one account and a
// first sign-in exercises dev-mode provisioning end to end.
export function uniqueEmail(prefix = "e2e"): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

/** Sign in through the real login form and wait for the app shell to render. */
export async function signIn(page: Page, email = uniqueEmail()): Promise<string> {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByRole("button", { name: "Sign in" }).click();

  await expect(page.getByRole("navigation", { name: "Primary" })).toBeVisible();
  await expect(page.getByTestId("signed-in-as")).toHaveText(email);
  return email;
}
