import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

// The three enforcement guards from docs/design/design-tokens.md §9 (closes C-14).
//
// Each guard is written twice: once against the real application, and once
// against an injected violation. The second half matters more than it looks —
// a guard that only ever runs where there is nothing to find passes vacuously
// forever, which is exactly how C-2 and C-3 happened. The non-vacuity tests
// prove the predicate actually rejects the thing it is supposed to reject.
//
// Scope, stated explicitly per the closeout brief:
//   (a) runs against every route that exists today. No highlight marks exist
//       yet — the Overview hero and empty-state marks are N7 page work — so the
//       real-application half currently confirms "none anywhere", and the
//       injected half is what proves the rule is enforceable.
//   (b) runs against /dev/tokens, the only surface rendering the dashed pill
//       today. This is the guard that was proven by a deleted one-off script in
//       N7-TOKENS-CLOSEOUT; it is a committed spec now.
//   (c) runs against /ci-failures. That page is still a placeholder, so the
//       hero-card exclusion is asserted now (and is meaningful — it would catch
//       someone applying the T6 treatment). The positive "renders a dense table"
//       half lands with the CI Failures page itself; see C-18.

const AI_ACTIONS = ["run-ai-analysis", "generate-tests", "run-triage", "regenerate"];

/** Every authenticated route in the app shell. */
const APP_ROUTES = [
  "/",
  "/ci-failures",
  "/test-generator",
  "/defect-triage",
  "/knowledge-base",
  "/evaluations",
  "/analytics",
  "/integrations",
  "/system-health",
  "/administration",
];

// --- the predicates, defined once so the real and injected halves share them ---

/** T2: a highlight mark is legal on Overview, or inside an empty state anywhere. */
async function illegalHighlightMarks(page: Page, pathname: string): Promise<number> {
  return page.evaluate((path) => {
    const marks = Array.from(document.querySelectorAll('[data-testid="highlight-mark"]'));
    if (path === "/") return 0;
    return marks.filter((mark) => !mark.closest('[data-testid="empty-state"]')).length;
  }, pathname);
}

/** T4: every dashed pill is an allowlisted AI action, and nothing else is dashed. */
async function dashedPillViolations(page: Page, allowlist: string[]): Promise<string[]> {
  return page.evaluate((allowed) => {
    const problems: string[] = [];
    const aiActions = Array.from(document.querySelectorAll('[data-variant="ai-action"]'));
    for (const el of aiActions) {
      const action = el.getAttribute("data-ai-action");
      if (!action || !allowed.includes(action)) {
        problems.push(`ai-action with disallowed label: ${action ?? "(missing)"}`);
      }
    }
    // A hand-rolled dashed element that never went through the component.
    const dashed = Array.from(document.querySelectorAll("*")).filter((el) =>
      Array.from(el.classList).some((c) => c.includes("border-dashed")),
    );
    for (const el of dashed) {
      if (el.getAttribute("data-variant") !== "ai-action") {
        problems.push(`dashed element that is not an ai-action: <${el.tagName.toLowerCase()}>`);
      }
    }
    return problems;
  }, allowlist);
}

/** T6: the hero-block card treatment appears on no current view. */
async function heroCardCount(page: Page): Promise<number> {
  return page.locator('[data-variant="hero-card"]').count();
}

// --- (a) highlighter marks -------------------------------------------------

test("guard (a): highlight marks appear only on Overview or inside an empty state", async ({
  page,
}) => {
  await signIn(page);

  for (const route of APP_ROUTES) {
    await page.goto(route);
    await expect
      .poll(() => illegalHighlightMarks(page, route), {
        message: `highlight mark outside Overview/empty-state on ${route}`,
      })
      .toBe(0);
  }
});

test("guard (a) is not vacuous: it rejects an injected mark on a functional route", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/system-health");

  // A mark with no empty-state ancestor — the exact thing T2 forbids.
  await page.evaluate(() => {
    const mark = document.createElement("mark");
    mark.setAttribute("data-testid", "highlight-mark");
    mark.textContent = "approved";
    document.body.appendChild(mark);
  });
  expect(await illegalHighlightMarks(page, "/system-health")).toBe(1);

  // The same mark inside an empty state is legal, so the rule is a scope rule
  // and not a blanket ban.
  await page.evaluate(() => {
    document.querySelector('[data-testid="highlight-mark"]')?.remove();
    const empty = document.createElement("div");
    empty.setAttribute("data-testid", "empty-state");
    const mark = document.createElement("mark");
    mark.setAttribute("data-testid", "highlight-mark");
    empty.appendChild(mark);
    document.body.appendChild(empty);
  });
  expect(await illegalHighlightMarks(page, "/system-health")).toBe(0);
});

// --- (b) dashed pill / AI-action allowlist ---------------------------------

test("guard (b): every dashed pill is an allowlisted AI action", async ({ page }) => {
  // /dev/tokens is the only surface rendering the dashed variant today, and it
  // renders outside the session gate.
  await page.goto("/dev/tokens");
  await expect(page.getByRole("heading", { name: "Design token preview" })).toBeVisible();

  const aiActions = page.locator('[data-variant="ai-action"]');
  await expect(aiActions).not.toHaveCount(0); // the guard must have something to check

  expect(await dashedPillViolations(page, AI_ACTIONS)).toEqual([]);

  const labels = await aiActions.evaluateAll((els) =>
    els.map((el) => el.getAttribute("data-ai-action")),
  );
  for (const label of labels) {
    expect(AI_ACTIONS).toContain(label);
  }
});

test("guard (b) is not vacuous: it rejects a non-allowlisted label and a stray dashed element", async ({
  page,
}) => {
  await page.goto("/dev/tokens");

  await page.evaluate(() => {
    const bad = document.createElement("button");
    bad.setAttribute("data-variant", "ai-action");
    bad.setAttribute("data-ai-action", "export-csv"); // not an AI action
    document.body.appendChild(bad);
  });
  expect(await dashedPillViolations(page, AI_ACTIONS)).toContain(
    "ai-action with disallowed label: export-csv",
  );

  await page.evaluate(() => {
    document.querySelector('[data-ai-action="export-csv"]')?.remove();
    const stray = document.createElement("div");
    stray.className = "rounded-full border border-dashed"; // dashed, not an AI action
    document.body.appendChild(stray);
  });
  expect(await dashedPillViolations(page, AI_ACTIONS)).toContain(
    "dashed element that is not an ai-action: <div>",
  );
});

// --- (c) CI Failures is never the hero-card treatment ----------------------

test("guard (c): no view uses the T6 hero-card treatment", async ({ page }) => {
  await signIn(page);

  for (const route of APP_ROUTES) {
    await page.goto(route);
    expect(await heroCardCount(page), `hero-card treatment on ${route}`).toBe(0);
  }
});

test("guard (c) is not vacuous: it rejects an injected hero card on CI Failures", async ({
  page,
}) => {
  await signIn(page);
  await page.goto("/ci-failures");

  await page.evaluate(() => {
    const card = document.createElement("article");
    card.setAttribute("data-variant", "hero-card");
    document.body.appendChild(card);
  });
  expect(await heroCardCount(page)).toBe(1);
});
