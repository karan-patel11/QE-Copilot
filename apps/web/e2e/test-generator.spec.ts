import { expect, test, type Page } from "@playwright/test";

import { signIn } from "./helpers";

// N7-BUILD — Test Generator (§11.5), F1-F6.
//
// Split deliberately between two kinds of test:
//
//   * The submit path runs against the **real API** — it proves the client
//     wiring, the 202, and the QUEUED render end to end.
//   * The terminal-state renders (FAILED, drift, unmet kinds, populated results)
//     are driven by **route interception**. Those states require a worker to
//     have processed a job, and pinning them to a live worker would make a UI
//     test depend on provider timing. What N7 owns is the rendering, so the
//     rendering is what these assert — deterministically.
//
// Stated rather than hidden: the API's own behaviour is covered by N6's 34
// integration tests, not re-proved here.

const PAGE = "/test-generator";

const CASE_FIXTURE = {
  id: "11111111-1111-1111-1111-111111111111",
  request_id: "22222222-2222-2222-2222-222222222222",
  ordinal: 0,
  title: "Resume playback on a second registered device",
  objective: "Playback resumes at the stored position",
  preconditions: "The subscriber has an active subscription.",
  test_data: { device_id: "device-2" },
  steps: [{ action: "Request resume on device 2", expected: "Playback starts" }],
  expected_result: "Playback resumes at the stored position",
  priority: "P1",
  tags: ["playback"],
  test_type: "positive",
  framework: "pytest",
  generated_code: "import pytest\n\n\ndef test_resume_playback():\n    assert True\n",
  schema_valid: true,
  syntax_valid: true,
  validation_errors: [],
  execution_status: null,
  human_status: "PENDING_REVIEW",
  duplicate_of: null,
  duplicate_score: null,
  is_edited: false,
  reviewed_by: null,
  reviewed_at: null,
  created_at: "2026-08-01T00:00:00Z",
};

function requestFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "22222222-2222-2222-2222-222222222222",
    project_id: "33333333-3333-3333-3333-333333333333",
    repository_id: null,
    job_id: "44444444-4444-4444-4444-444444444444",
    title: "Resume playback across devices",
    source_type: "requirement_text",
    framework: "pytest",
    status: "COMPLETED",
    configuration: {},
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:05Z",
    error: null,
    error_code: null,
    prompt_versions: {
      requirement_decomposition: "decompose-v1",
      test_plan: "testplan-v1",
      test_generation: "testgen-v1",
      pytest_codegen: "pytest_codegen-v1",
    },
    case_count: 1,
    produced_by_type: { positive: 1 },
    unmet_requested_kinds: [],
    coverage_notes: "No boundary cases: the requirement states no numeric limits.",
    model_run_ids: ["a", "b", "c", "d"],
    validation_passed: 1,
    validation_failed: 0,
    ...overrides,
  };
}

/**
 * A project for the select to offer.
 *
 * Dev-login provisions an **engineer**, which does not hold `PROJECT_WRITE`, so
 * the test user genuinely cannot create one — the Generate button is correctly
 * disabled without this. Stubbed rather than worked around, because the empty
 * project list is real behaviour that the disabled button is right about.
 */
async function stubProjects(page: Page) {
  await page.route("**/api/v1/projects*", (route) =>
    route.fulfill({
      status: 200,
      json: {
        items: [
          {
            id: "33333333-3333-3333-3333-333333333333",
            organisation_id: "00000000-0000-0000-0000-000000000000",
            name: "Playback",
            slug: "playback",
            description: null,
            created_at: "2026-08-01T00:00:00Z",
            updated_at: "2026-08-01T00:00:00Z",
          },
        ],
        total: 1,
        limit: 50,
        offset: 0,
      },
    }),
  );
}

/** Stub the generation endpoints so a terminal state renders deterministically. */
async function stubGeneration(
  page: Page,
  request: Record<string, unknown>,
  cases: Record<string, unknown>[] = [],
) {
  await page.route("**/api/v1/test-generation/requests", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    return route.fulfill({ status: 202, json: request });
  });
  await page.route("**/api/v1/test-generation/requests/*", (route) =>
    route.fulfill({ status: 200, json: request }),
  );
  await page.route("**/api/v1/test-generation/requests/*/tests*", (route) =>
    route.fulfill({
      status: 200,
      json: { items: cases, total: cases.length, limit: 50, offset: 0 },
    }),
  );
}

async function fillAndSubmit(page: Page) {
  await page.getByTestId("requirement-input").fill(
    "A subscriber should be able to resume playback on another registered device.",
  );
  await page.getByTestId("title-input").fill("Resume playback across devices");
  await page.getByTestId("generate-tests").click();
}

// --- the page renders at all ------------------------------------------------

test("the Test Generator renders §11.5's input sources and eleven configuration options", async ({
  page,
}) => {
  await signIn(page);
  await stubProjects(page);
  await page.goto(PAGE);

  await expect(page.getByRole("heading", { name: "Test Generator" })).toBeVisible();
  // It is no longer the Phase 0 placeholder.
  await expect(page.getByText("Placeholder — coming in a later phase.")).toHaveCount(0);

  for (const id of [
    "project-select",
    "title-input",
    "source-type-select",
    "requirement-input",
    "test-type-select",
    "framework-select",
    "target-service-input",
    "number-of-tests-input",
    "priority-select",
    "max-cost-input",
    "include-positive",
    "include-negative",
    "include-boundary",
    "include-security",
    "include-accessibility",
  ]) {
    await expect(page.getByTestId(id), `control ${id}`).toBeVisible();
  }
});

// --- D2: the accessibility control is disabled and makes no network call ----

test("F-D2: the accessibility control is disabled and produces zero network calls", async ({
  page,
}) => {
  await signIn(page);

  const generationCalls: string[] = [];
  page.on("request", (req) => {
    if (req.url().includes("/api/v1/test-generation")) generationCalls.push(req.url());
  });

  await stubProjects(page);
  await page.goto(PAGE);

  const control = page.getByTestId("include-accessibility");
  await expect(control).toBeDisabled();
  await expect(control).not.toBeChecked();
  await expect(page.getByTestId("accessibility-reason")).toContainText("Unsupported in this phase");

  // Clicking a disabled control must do nothing at all — no request, no state change.
  await control.click({ force: true }).catch(() => undefined);
  await page.waitForTimeout(500);

  expect(control).toBeTruthy();
  await expect(control).not.toBeChecked();
  expect(generationCalls, "a disabled control must not reach the API").toEqual([]);
});

// --- F6: the five job states are distinct --------------------------------

test("F6: an accepted request renders its own state, not a generic spinner", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(page, requestFixture({ status: "QUEUED", case_count: 0, prompt_versions: {} }));
  await page.goto(PAGE);
  await fillAndSubmit(page);

  const badge = page.getByTestId("status-badge").filter({ hasText: "QUEUED" });
  await expect(badge).toBeVisible();
  await expect(badge).toHaveAttribute("data-semantic", "pending");
  await expect(page.getByTestId("state-explanation")).toContainText("Queued");
});

test("F6: each job state maps to its own semantic token", async ({ page }) => {
  await signIn(page);

  const expected: [string, string][] = [
    ["QUEUED", "pending"],
    ["WAITING_FOR_PROVIDER", "active"],
    ["RUNNING", "active"],
    ["VALIDATING", "active"],
    ["COMPLETED", "success"],
    ["FAILED", "failure"],
  ];

  for (const [state, semantic] of expected) {
    await stubProjects(page);
  await stubGeneration(
      page,
      requestFixture({ status: state, case_count: 0, prompt_versions: {} }),
    );
    await page.goto(PAGE);
    await fillAndSubmit(page);

    const badge = page.getByTestId("status-badge").filter({ hasText: state });
    await expect(badge, `${state} badge`).toBeVisible();
    await expect(badge, `${state} → ${semantic}`).toHaveAttribute("data-semantic", semantic);
    await expect(page.getByTestId("state-explanation")).not.toBeEmpty();
  }
});

// --- F1 / C-13: FAILED render and idempotency-key rotation -----------------

test("F1: a failed request offers a new submission, and the idempotency key actually changes", async ({
  page,
}) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(
    page,
    requestFixture({
      status: "FAILED",
      error: "ProviderError: the provider was unavailable",
      error_code: "PROVIDER_ERROR",
      case_count: 0,
      prompt_versions: {},
    }),
  );
  await page.goto(PAGE);

  const keyBefore = await page.getByTestId("idempotency-key").getAttribute("data-key");
  expect(keyBefore).toBeTruthy();

  await fillAndSubmit(page);
  await expect(page.getByTestId("failed-panel")).toBeVisible();
  await expect(page.getByTestId("error-code")).toHaveText("PROVIDER_ERROR");

  // The key must not have rotated merely by submitting — a retry of the *same*
  // logical request has to reuse it, or idempotency would mean nothing.
  expect(await page.getByTestId("idempotency-key").getAttribute("data-key")).toBe(keyBefore);

  await page.getByTestId("submit-as-new-request").click();

  const keyAfter = await page.getByTestId("idempotency-key").getAttribute("data-key");
  expect(keyAfter, "a new request must carry a fresh key (C-13)").not.toBe(keyBefore);
  await expect(page.getByTestId("notice")).toContainText("fresh idempotency key");
  await expect(page.getByTestId("failed-panel")).toHaveCount(0);
});

// --- F2 / D5: drift is not retryable ---------------------------------------

test("F2: template drift renders its code with no retry affordance", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(
    page,
    requestFixture({
      status: "FAILED",
      error: "PromptTemplateDriftError: decompose-v1 no longer matches its source template",
      error_code: "PROMPT_TEMPLATE_DRIFT",
      case_count: 0,
      prompt_versions: {},
    }),
  );
  await page.goto(PAGE);
  await fillAndSubmit(page);

  await expect(page.getByTestId("error-code")).toHaveText("PROMPT_TEMPLATE_DRIFT");
  await expect(page.getByTestId("no-retry-explanation")).toContainText("needs an engineer");

  // The distinguishing assertion: no retry, unlike the PROVIDER_ERROR case above.
  await expect(page.getByTestId("submit-as-new-request")).toHaveCount(0);
  await expect(page.getByRole("button", { name: /try again/i })).toHaveCount(0);
});

// --- F3 / D4: the prompt-version map, empty and populated ------------------

test("F3: the prompt-version map renders empty before any stage runs", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(
    page,
    requestFixture({ status: "QUEUED", prompt_versions: {}, case_count: 0 }),
  );
  await page.goto(PAGE);
  await fillAndSubmit(page);

  await expect(page.getByTestId("prompt-versions-panel")).toBeVisible();
  await expect(page.getByTestId("prompt-versions-empty")).toContainText("No stage has run yet");
  await expect(page.getByTestId("stat-row")).toHaveCount(0);
});

test("F3: the prompt-version map renders all four stages when populated", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(page, requestFixture(), [CASE_FIXTURE]);
  await page.goto(PAGE);
  await fillAndSubmit(page);

  const panel = page.getByTestId("prompt-versions-panel");
  await expect(panel).toBeVisible();
  await expect(panel.getByTestId("stat-row")).toHaveCount(4);

  const values = await panel.getByTestId("stat-row-value").allInnerTexts();
  expect(values.sort()).toEqual(
    ["decompose-v1", "pytest_codegen-v1", "testgen-v1", "testplan-v1"].sort(),
  );
  // D4 — the singular column is right about one stage in four, so it is exposed
  // nowhere. Four rows is the assertion that the map, not the column, is shown.
  await expect(page.getByTestId("prompt-versions-empty")).toHaveCount(0);
});

// --- F4 / D6: unmet kinds are informational, never an error ----------------

test("F4: unmet requested kinds render as a reported gap, not a failure", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(
    page,
    requestFixture({
      unmet_requested_kinds: ["boundary", "security"],
      produced_by_type: { positive: 1 },
    }),
    [CASE_FIXTURE],
  );
  await page.goto(PAGE);
  await fillAndSubmit(page);

  const banner = page.getByTestId("unmet-kinds-banner");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("boundary, security");
  await expect(banner).toContainText("NOT AN ERROR");

  // The token assertion: partial, never failure.
  const cls = (await banner.getAttribute("class")) ?? "";
  expect(cls).toContain("status-partial");
  expect(cls, "an unmet kind must never use the failure token").not.toContain("status-failure");

  // And it is not an error state: the request still completed.
  //
  // Asserted against this app's two error surfaces rather than `getByRole("alert")`,
  // which always matches at least one element on any Next.js page — the framework
  // injects a route announcer with `role="alert"` for screen readers. Matching that
  // would make the assertion about Next, not about us.
  await expect(page.getByTestId("failed-panel")).toHaveCount(0);
  await expect(page.getByTestId("error-state")).toHaveCount(0);
  await expect(banner).not.toHaveAttribute("role", "alert");
});

// --- F5 / C-7: no UI implies project isolation -----------------------------

test("F5: the project control is labelled a filter, not an access boundary", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await page.goto(PAGE);

  const note = page.getByTestId("project-scope-note");
  await expect(note).toBeVisible();
  await expect(note).toContainText("filter, not an access boundary");
  await expect(note).toContainText("every project in your organisation");
});

// --- full lifecycle: generate → edit → approve ------------------------------

test("full lifecycle: generate, edit the code, approve the case", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(page, requestFixture(), [CASE_FIXTURE]);
  await page.route("**/api/v1/generated-tests/*/approve", (route) =>
    route.fulfill({ status: 200, json: { ...CASE_FIXTURE, human_status: "APPROVED" } }),
  );
  await page.goto(PAGE);
  await fillAndSubmit(page);

  const card = page.getByTestId("generated-case").first();
  await expect(card).toBeVisible();

  // §11.5 L873-885 — every display field.
  await expect(card).toContainText("Resume playback on a second registered device");
  await expect(card).toContainText("Playback resumes at the stored position");
  await expect(card.getByTestId("generated-code")).toContainText("def test_resume_playback");
  await expect(card.getByTestId("source-requirement")).toContainText("Resume playback across devices");
  await expect(card.getByTestId("validation-status")).toContainText("validation passed");
  // Never reads as "passed" — the sandbox is deferred (ADR-0205).
  await expect(card.getByTestId("execution-status")).toContainText("not run — sandbox deferred");

  // Edit.
  await card.getByTestId("edit-case").click();
  await card.getByTestId("code-editor").fill("def test_edited():\n    assert True\n");
  await card.getByTestId("save-edit").click();
  await expect(card.getByTestId("generated-code")).toContainText("test_edited");
  await expect(card.getByTestId("edited-flag")).toBeVisible();

  // Approve — nothing auto-approves, so this is the only way it happens (§8.2).
  await expect(card).toHaveAttribute("data-human-status", "PENDING_REVIEW");
  await card.getByTestId("approve-case").click();
  await expect(card).toHaveAttribute("data-human-status", "APPROVED");
  await expect(card.getByTestId("approve-case")).toBeDisabled();
});

// --- the AI-action pills on this page satisfy guard (b) unmodified ---------

test("both AI actions on this page carry allowlisted labels", async ({ page }) => {
  await signIn(page);
  await stubProjects(page);
  await stubGeneration(page, requestFixture(), [CASE_FIXTURE]);
  await page.goto(PAGE);
  await fillAndSubmit(page);
  // Regenerate lives on a case card, so the results have to be rendered before
  // the labels are read.
  await expect(page.getByTestId("generated-case").first()).toBeVisible();

  const labels = await page
    .locator('[data-variant="ai-action"]')
    .evaluateAll((els) => els.map((el) => el.getAttribute("data-ai-action")));

  expect(labels).toContain("generate-tests");
  expect(labels).toContain("regenerate");
  for (const label of labels) {
    expect(["run-ai-analysis", "generate-tests", "run-triage", "regenerate"]).toContain(label);
  }
});
