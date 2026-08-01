"use client";

// Test Generator — §11.5, built on the N7-DESIGN v2 lock (T1-T8) and the N6 API.
//
// Carried-forward requirements are marked F1-F6 where they are implemented, so a
// reader can find each one without cross-referencing a brief.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { AiActionButton, PrimaryButton, SecondaryButton } from "@/components/Buttons";
import { Eyebrow, PageHeader, SectionHeader, TagPill } from "@/components/PageHeader";
import { EmptyState, ErrorState, LoadingState } from "@/components/RequestState";
import { StatPanel } from "@/components/StatPanel";
import { StatusBadge } from "@/components/StatusBadge";
import {
  ApiError,
  apiClient,
  type GeneratedTestCase,
  type Project,
  type SourceType,
  type TestGenerationRequest,
  type TestPriority,
  type TestType,
} from "@/lib/api-client";
import { useApi } from "@/lib/use-api";

const TERMINAL_STATES = new Set([
  "COMPLETED",
  "PARTIALLY_COMPLETED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
]);

// F6 — what each state means, in words. Colour is never the only signal (T3),
// and a single spinner would collapse five distinguishable states into one.
const STATE_EXPLANATION: Record<string, string> = {
  PENDING: "Accepted. Waiting to be queued.",
  QUEUED: "Queued. A worker will claim it shortly.",
  RUNNING: "Claimed by a worker. Preparing the pipeline.",
  WAITING_FOR_PROVIDER: "Calling the model — decomposition, plan, cases, code.",
  VALIDATING: "Running the static validation chain.",
  COMPLETED: "Finished. Every case is awaiting your review.",
  PARTIALLY_COMPLETED: "Finished with gaps. See the coverage notes.",
  FAILED: "Did not complete.",
  CANCELLED: "Cancelled before completion.",
  TIMED_OUT: "Exceeded the time budget.",
};

/** D5 — codes no retry can clear, so the UI must not offer one (F2). */
const NON_RETRYABLE = new Set(["PROMPT_TEMPLATE_DRIFT", "TEST_CONFIG_UNSUPPORTED"]);

const SOURCE_TYPES: { value: SourceType; label: string }[] = [
  { value: "requirement_text", label: "Product requirement" },
  { value: "user_story", label: "User story" },
  { value: "acceptance_criteria", label: "Acceptance criteria" },
];

const TEST_TYPES: TestType[] = [
  "unit",
  "integration",
  "positive",
  "negative",
  "boundary",
  "edge_case",
  "security",
];

const PRIORITIES: TestPriority[] = ["P0", "P1", "P2", "P3"];

/** A fresh idempotency key. Rotated on every new submission (F1 / C-13). */
function newIdempotencyKey(): string {
  return `tg-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="font-mono text-mono-xs uppercase text-ink-subtle">{label}</span>
      {children}
    </label>
  );
}

const INPUT =
  "rounded-md border border-rule-strong bg-surface px-3 py-2 font-display text-body-sm text-ink focus:border-ink focus:outline-none";

export default function TestGeneratorPage() {
  const loadProjects = useCallback(() => apiClient.projects(), []);
  const projects = useApi(loadProjects);

  const [projectId, setProjectId] = useState("");
  const [title, setTitle] = useState("");
  const [sourceType, setSourceType] = useState<SourceType>("requirement_text");
  const [requirement, setRequirement] = useState("");
  const [testType, setTestType] = useState<TestType>("unit");
  const [numberOfTests, setNumberOfTests] = useState(5);
  const [targetService, setTargetService] = useState("");
  const [priority, setPriority] = useState<TestPriority | "">("");
  const [maxCost, setMaxCost] = useState("");
  const [includePositive, setIncludePositive] = useState(true);
  const [includeNegative, setIncludeNegative] = useState(true);
  const [includeBoundary, setIncludeBoundary] = useState(true);
  const [includeSecurity, setIncludeSecurity] = useState(false);

  // F1 — the key for the *next* submission.
  const [idempotencyKey, setIdempotencyKey] = useState(newIdempotencyKey);

  const [request, setRequest] = useState<TestGenerationRequest | null>(null);
  const [cases, setCases] = useState<GeneratedTestCase[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [draftCode, setDraftCode] = useState("");

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (projects.data && projects.data.items.length > 0 && !projectId) {
      setProjectId(projects.data.items[0].id);
    }
  }, [projects.data, projectId]);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const loadCases = useCallback(async (id: string) => {
    const page = await apiClient.generationTests(id);
    setCases(page.items);
  }, []);

  // Poll the authoritative row (§13.2) until terminal, then load the cases.
  useEffect(() => {
    if (!request) {
      stopPolling();
      return;
    }
    // A request can arrive already terminal — a replayed idempotency key returns
    // a finished row, and so would revisiting one. Loading the cases only from
    // inside the polling tick would leave those renders permanently empty.
    if (TERMINAL_STATES.has(request.status)) {
      stopPolling();
      if (request.status === "COMPLETED" || request.status === "PARTIALLY_COMPLETED") {
        void loadCases(request.id);
      }
      return;
    }
    pollRef.current = setInterval(() => {
      void (async () => {
        try {
          const next = await apiClient.generationRequest(request.id);
          setRequest(next);
          if (next.status === "COMPLETED" || next.status === "PARTIALLY_COMPLETED") {
            await loadCases(next.id);
          }
        } catch {
          stopPolling();
        }
      })();
    }, 1000);
    return stopPolling;
  }, [request, stopPolling, loadCases]);

  const submit = useCallback(async () => {
    setSubmitting(true);
    setSubmitError(null);
    setNotice(null);
    try {
      const created = await apiClient.createGenerationRequest(
        {
          project_id: projectId,
          title: title || "Untitled requirement",
          source_type: sourceType,
          source_reference: requirement,
          framework: "pytest",
          configuration: {
            test_type: testType,
            framework: "pytest",
            target_service: targetService || null,
            number_of_tests: numberOfTests,
            include_positive_cases: includePositive,
            include_negative_cases: includeNegative,
            include_boundary_cases: includeBoundary,
            include_security_cases: includeSecurity,
            // Never true. The control is disabled and the API refuses it with a
            // 422 regardless (D2); sent explicitly so the stored configuration is
            // the full eleven keys (ADR-0208).
            include_accessibility_cases: false,
            desired_priority: priority || null,
            max_generation_cost_usd: maxCost ? Number(maxCost) : null,
          },
        },
        idempotencyKey,
      );
      setRequest(created);
      setCases([]);
    } catch (error) {
      setSubmitError(
        error instanceof ApiError ? error.message : "The request could not be submitted.",
      );
    } finally {
      setSubmitting(false);
    }
  }, [
    projectId,
    title,
    sourceType,
    requirement,
    testType,
    targetService,
    numberOfTests,
    includePositive,
    includeNegative,
    includeBoundary,
    includeSecurity,
    priority,
    maxCost,
    idempotencyKey,
  ]);

  /**
   * F1 / C-13 — the escape hatch from a failed request.
   *
   * An idempotency key is bound to the request row, so replaying the same key
   * returns the failed row forever. Resubmitting therefore has to rotate the
   * key; without that, "try again" would appear to work and change nothing.
   */
  const submitAsNewRequest = useCallback(() => {
    setIdempotencyKey(newIdempotencyKey());
    setRequest(null);
    setCases([]);
    setNotice("Started a new request with a fresh idempotency key.");
  }, []);

  const review = useCallback(async (id: string, decision: "approve" | "reject") => {
    const updated =
      decision === "approve" ? await apiClient.approveTest(id) : await apiClient.rejectTest(id);
    setCases((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));
  }, []);

  const regenerate = useCallback(async (id: string) => {
    // D3 — codegen only, this case only. Other cases keep their review state.
    await apiClient.regenerateTest(id);
    setNotice("Regeneration queued — code only, for this case (ADR-0212 D3).");
  }, []);

  const revalidate = useCallback(async (id: string) => {
    const result = await apiClient.validateTest(id);
    setCases((prev) =>
      prev.map((c) =>
        c.id === result.id
          ? {
              ...c,
              schema_valid: result.schema_valid,
              syntax_valid: result.syntax_valid,
              validation_errors: result.validation_errors,
            }
          : c,
      ),
    );
  }, []);

  const saveAs = useCallback((body: string, filename: string, type: string) => {
    const url = URL.createObjectURL(new Blob([body], { type }));
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }, []);

  const isFailed = request?.status === "FAILED";
  const nonRetryable = !!request?.error_code && NON_RETRYABLE.has(request.error_code);

  // F3 — D4's four-entry map, through StatPanel rather than a bespoke display.
  // The singular `prompt_version` column is exposed by no endpoint.
  const promptRows = useMemo(
    () =>
      Object.entries(request?.prompt_versions ?? {}).map(([stage, version]) => ({
        label: stage.replace(/_/g, " "),
        value: version,
      })),
    [request?.prompt_versions],
  );

  return (
    <section className="flex flex-col gap-8 pb-16">
      <PageHeader
        eyebrow="TEST GENERATOR"
        title="Test Generator"
        description="Turn a requirement into reviewable Pytest cases. Nothing is approved automatically."
      />

      <div className="grid gap-8 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
        {/* ---------------- Input sources ---------------- */}
        <div className="flex flex-col gap-4">
          <SectionHeader eyebrow="§11.5 L845-853" title="Input source" />

          {projects.loading ? <LoadingState label="projects" /> : null}
          {projects.error ? <ErrorState message={projects.error} onRetry={projects.reload} /> : null}

          <Field label="Project">
            <select
              data-testid="project-select"
              className={INPUT}
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              {(projects.data?.items ?? []).map((p: Project) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </Field>

          {/* F5 — C-7: project-level RBAC is not enforced. This control files the
              request under a project; it is not an access boundary, and the copy
              must not imply one. */}
          <p data-testid="project-scope-note" className="font-display text-body-sm text-ink-subtle">
            This filters which project the request is filed under. It is a filter, not
            an access boundary — every project in your organisation is visible to your
            role.
          </p>

          <Field label="Title">
            <input
              data-testid="title-input"
              className={INPUT}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Resume playback across devices"
            />
          </Field>

          <Field label="Source type">
            <select
              data-testid="source-type-select"
              className={INPUT}
              value={sourceType}
              onChange={(e) => setSourceType(e.target.value as SourceType)}
            >
              {SOURCE_TYPES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </Field>

          <Field label="Requirement">
            <textarea
              data-testid="requirement-input"
              className={`${INPUT} min-h-32`}
              value={requirement}
              onChange={(e) => setRequirement(e.target.value)}
              placeholder="A subscriber should be able to resume playback on another registered device."
            />
          </Field>
        </div>

        {/* ---------------- Test configuration ---------------- */}
        <div className="flex flex-col gap-4">
          <SectionHeader eyebrow="§11.5 L857-867" title="Test configuration" />

          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Test type">
              <select
                data-testid="test-type-select"
                className={INPUT}
                value={testType}
                onChange={(e) => setTestType(e.target.value as TestType)}
              >
                {TEST_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Framework">
              {/* §7.1 names four initial frameworks; §38 L2801 scopes this phase to
                  Pytest, so the control states the constraint rather than offering
                  options that would fail. */}
              <select data-testid="framework-select" className={INPUT} value="pytest" disabled>
                <option value="pytest">pytest</option>
              </select>
            </Field>

            <Field label="Target service">
              <input
                data-testid="target-service-input"
                className={INPUT}
                value={targetService}
                onChange={(e) => setTargetService(e.target.value)}
              />
            </Field>

            <Field label="Number of tests">
              <input
                data-testid="number-of-tests-input"
                type="number"
                min={1}
                max={20}
                className={INPUT}
                value={numberOfTests}
                onChange={(e) => setNumberOfTests(Number(e.target.value))}
              />
            </Field>

            <Field label="Desired priority">
              <select
                data-testid="priority-select"
                className={INPUT}
                value={priority}
                onChange={(e) => setPriority(e.target.value as TestPriority | "")}
              >
                <option value="">Any</option>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Max cost (USD)">
              <input
                data-testid="max-cost-input"
                className={INPUT}
                value={maxCost}
                onChange={(e) => setMaxCost(e.target.value)}
                placeholder="unbounded"
              />
            </Field>
          </div>

          <fieldset className="flex flex-col gap-2 border-t border-rule pt-4">
            <legend className="sr-only">Case kinds</legend>
            <Eyebrow>INCLUDE</Eyebrow>

            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                data-testid="include-positive"
                checked={includePositive}
                onChange={(e) => setIncludePositive(e.target.checked)}
              />
              <span className="font-display text-body-sm text-ink">positive cases</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                data-testid="include-negative"
                checked={includeNegative}
                onChange={(e) => setIncludeNegative(e.target.checked)}
              />
              <span className="font-display text-body-sm text-ink">negative cases</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                data-testid="include-boundary"
                checked={includeBoundary}
                onChange={(e) => setIncludeBoundary(e.target.checked)}
              />
              <span className="font-display text-body-sm text-ink">boundary cases</span>
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                data-testid="include-security"
                checked={includeSecurity}
                onChange={(e) => setIncludeSecurity(e.target.checked)}
              />
              <span className="font-display text-body-sm text-ink">security cases</span>
            </label>

            {/* D2 — the one option this phase refuses. Disabled at the control and
                never sent as true. Accepting it and returning ordinary tests would
                label them as covering accessibility when they do not (ADR-0208). */}
            <label className="flex items-start gap-2 opacity-70">
              <input
                type="checkbox"
                data-testid="include-accessibility"
                disabled
                checked={false}
                readOnly
              />
              <span className="font-display text-body-sm text-ink-subtle">
                accessibility cases
                <span
                  data-testid="accessibility-reason"
                  className="mt-0.5 block font-mono text-mono-xs uppercase text-ink-subtle"
                >
                  Unsupported in this phase — needs a rendered UI to assert against
                </span>
              </span>
            </label>
          </fieldset>

          <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-4">
            <AiActionButton
              action="generate-tests"
              data-testid="generate-tests"
              disabled={submitting || !projectId || !requirement.trim()}
              onClick={submit}
            >
              {submitting ? "Submitting…" : "Generate Tests"}
            </AiActionButton>
            <span
              data-testid="idempotency-key"
              data-key={idempotencyKey}
              className="font-mono text-mono-xs text-ink-subtle"
            >
              key {idempotencyKey}
            </span>
          </div>

          {submitError ? <ErrorState message={submitError} /> : null}
          {notice ? (
            <p data-testid="notice" className="font-display text-body-sm text-ink-muted">
              {notice}
            </p>
          ) : null}
        </div>
      </div>

      {/* ---------------- Request status ---------------- */}
      {request ? (
        <div className="flex flex-col gap-4">
          <SectionHeader
            eyebrow="REQUEST"
            title={request.title}
            actions={<StatusBadge status={request.status} />}
          />

          {/* F6 — every state named, never collapsed into one spinner. */}
          <p data-testid="state-explanation" className="font-display text-body text-ink-muted">
            {STATE_EXPLANATION[request.status] ?? request.status}
          </p>

          {isFailed ? (
            <div
              role="alert"
              data-testid="failed-panel"
              className="rounded-lg border border-status-failure bg-status-failure-surface p-6"
            >
              <p className="font-display text-display-md font-semibold text-status-failure-ink">
                This request failed
              </p>
              {request.error_code ? (
                <p
                  data-testid="error-code"
                  className="mt-2 inline-flex rounded-full bg-status-failure px-3 py-1 font-mono text-mono-xs uppercase text-ink-inverse"
                >
                  {request.error_code}
                </p>
              ) : null}
              <p className="mt-3 font-display text-body-sm text-status-failure-ink">
                {request.error ?? "No reason was recorded."}
              </p>

              {nonRetryable ? (
                // F2 — D5. Template drift needs a code change and a re-seed, so a
                // retry affordance here would be guaranteed to fail.
                <p
                  data-testid="no-retry-explanation"
                  className="mt-3 font-display text-body-sm text-status-failure-ink"
                >
                  Retrying will not help — this needs an engineer. Contact the platform
                  team with the code above.
                </p>
              ) : (
                <div className="mt-4">
                  <SecondaryButton data-testid="submit-as-new-request" onClick={submitAsNewRequest}>
                    Submit as new request
                  </SecondaryButton>
                  <p className="mt-2 font-display text-body-sm text-status-failure-ink">
                    A replay of the same idempotency key returns this failed request, so
                    a new key is issued.
                  </p>
                </div>
              )}
            </div>
          ) : null}

          {/* F4 — D6. A requested kind that produced nothing is a reported gap, never
              an error: a requirement with no failure path legitimately yields no
              negative cases. Partial/neutral tokens, never failure. */}
          {request.unmet_requested_kinds.length > 0 ? (
            <div
              data-testid="unmet-kinds-banner"
              className="rounded-lg border border-status-partial bg-status-partial-surface p-4"
            >
              <p className="font-mono text-mono-xs uppercase text-status-partial-ink">
                COVERAGE GAP — NOT AN ERROR
              </p>
              <p className="mt-2 font-display text-body-sm text-status-partial-ink">
                No case was produced for{" "}
                <strong>{request.unmet_requested_kinds.join(", ")}</strong>. The
                requirement may not describe that behaviour — a gap is reported rather
                than filled with a fabricated case.
              </p>
              {request.coverage_notes ? (
                <p className="mt-2 font-display text-body-sm text-status-partial-ink">
                  {request.coverage_notes}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="grid gap-4 lg:grid-cols-2">
            {/* F3 — the four-entry prompt-version map. */}
            <StatPanel
              testId="prompt-versions-panel"
              label="Prompt versions"
              icon="◈"
              meta={request.job_id ? `job ${request.job_id.slice(0, 8)}` : undefined}
              rows={promptRows}
            >
              {promptRows.length === 0 ? (
                <p
                  data-testid="prompt-versions-empty"
                  className="font-display text-body-sm text-ink-subtle"
                >
                  No stage has run yet — an empty map, not an unknown one.
                </p>
              ) : null}
            </StatPanel>

            <StatPanel
              testId="validation-panel"
              label="Validation"
              icon="◈"
              readout={{ value: request.case_count, caption: "cases generated" }}
              bars={
                request.case_count > 0
                  ? [
                      {
                        label: "passed",
                        value: request.validation_passed / request.case_count,
                        display: `${request.validation_passed}/${request.case_count}`,
                      },
                    ]
                  : undefined
              }
              tags={Object.keys(request.produced_by_type)}
            />
          </div>
        </div>
      ) : null}

      {/* ---------------- Generated results ---------------- */}
      {request && cases.length > 0 ? (
        <div className="flex flex-col gap-4">
          <SectionHeader
            eyebrow="§11.5 L869-885"
            title="Generated results"
            actions={
              <>
                <SecondaryButton
                  data-testid="download-all"
                  onClick={() =>
                    saveAs(
                      cases.map((c) => `# ${c.title}\n${c.generated_code}`).join("\n\n"),
                      "generated_tests.py",
                      "text/x-python",
                    )
                  }
                >
                  Download
                </SecondaryButton>
                <SecondaryButton
                  data-testid="export-json"
                  onClick={() =>
                    saveAs(JSON.stringify(cases, null, 2), "generated_tests.json", "application/json")
                  }
                >
                  Export as JSON
                </SecondaryButton>
                <SecondaryButton
                  data-testid="create-pr-draft"
                  disabled
                  title="Pull-request drafts arrive with the GitHub integration (Phase 3)."
                >
                  Create PR draft
                </SecondaryButton>
                <SecondaryButton
                  data-testid="save-template"
                  disabled
                  title="Test templates arrive in a later phase."
                >
                  Save as template
                </SecondaryButton>
              </>
            }
          />

          <ul className="flex flex-col gap-4">
            {cases.map((c) => (
              <li
                key={c.id}
                data-testid="generated-case"
                data-case-id={c.id}
                data-human-status={c.human_status}
                className="rounded-lg border border-rule"
              >
                <div className="flex items-start justify-between gap-4 border-b border-rule px-4 py-3">
                  <div>
                    <p className="font-mono text-mono-xs uppercase text-ink-subtle">
                      #{c.ordinal} · {c.test_type} · {c.priority} · {c.framework}
                    </p>
                    <p className="mt-1 font-display text-display-md font-semibold text-ink">
                      {c.title}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <span
                      data-testid="human-status"
                      className="inline-flex items-center rounded-full border border-rule-strong bg-surface-raised px-2.5 py-0.5 font-mono text-mono-xs uppercase text-ink-secondary"
                    >
                      {c.human_status}
                    </span>
                    <span
                      data-testid="validation-status"
                      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-mono-xs uppercase ${
                        c.schema_valid && c.syntax_valid
                          ? "border-status-success bg-status-success-surface text-status-success-ink"
                          : "border-status-failure bg-status-failure-surface text-status-failure-ink"
                      }`}
                    >
                      {c.schema_valid && c.syntax_valid ? "validation passed" : "validation failed"}
                    </span>
                  </div>
                </div>

                <div className="flex flex-col gap-3 px-4 py-3">
                  <div>
                    <Eyebrow>OBJECTIVE</Eyebrow>
                    <p className="mt-1 font-display text-body-sm text-ink">{c.objective}</p>
                  </div>

                  {c.preconditions ? (
                    <div>
                      <Eyebrow>PRECONDITIONS</Eyebrow>
                      <p className="mt-1 font-display text-body-sm text-ink-muted">
                        {c.preconditions}
                      </p>
                    </div>
                  ) : null}

                  {Object.keys(c.test_data).length > 0 ? (
                    <div>
                      <Eyebrow>TEST DATA</Eyebrow>
                      <dl className="mt-1 flex flex-wrap gap-x-6 gap-y-1">
                        {Object.entries(c.test_data).map(([k, v]) => (
                          <div key={k} className="flex gap-2">
                            <dt className="font-mono text-mono-xs uppercase text-ink-subtle">{k}</dt>
                            <dd className="font-mono text-mono-xs text-ink">{String(v)}</dd>
                          </div>
                        ))}
                      </dl>
                    </div>
                  ) : null}

                  <div>
                    <Eyebrow>STEPS</Eyebrow>
                    <ol className="mt-1 flex flex-col gap-1">
                      {c.steps.map((s, i) => (
                        <li key={i} className="font-display text-body-sm text-ink">
                          <span className="font-mono text-mono-xs text-ink-subtle">{i + 1}.</span>{" "}
                          {s.action} → <span className="text-ink-muted">{s.expected}</span>
                        </li>
                      ))}
                    </ol>
                  </div>

                  <div>
                    <Eyebrow>EXPECTED RESULT</Eyebrow>
                    <p className="mt-1 font-display text-body-sm text-ink">{c.expected_result}</p>
                  </div>

                  <div>
                    <Eyebrow>SOURCE REQUIREMENT</Eyebrow>
                    <p data-testid="source-requirement" className="mt-1 font-display text-body-sm text-ink-muted">
                      {request.title}
                    </p>
                  </div>

                  {c.tags.length > 0 ? (
                    <div className="flex flex-wrap items-center gap-2">
                      {c.tags.map((tag) => (
                        <TagPill key={tag}>{tag}</TagPill>
                      ))}
                    </div>
                  ) : null}

                  <div>
                    <Eyebrow>GENERATED CODE</Eyebrow>
                    {editing === c.id ? (
                      <div className="mt-1 flex flex-col gap-2">
                        <textarea
                          data-testid="code-editor"
                          className={`${INPUT} min-h-40 font-mono text-mono-sm`}
                          value={draftCode}
                          onChange={(e) => setDraftCode(e.target.value)}
                        />
                        <div className="flex gap-2">
                          <PrimaryButton
                            data-testid="save-edit"
                            onClick={() => {
                              setCases((prev) =>
                                prev.map((x) =>
                                  x.id === c.id
                                    ? { ...x, generated_code: draftCode, is_edited: true }
                                    : x,
                                ),
                              );
                              setEditing(null);
                            }}
                          >
                            Save
                          </PrimaryButton>
                          <SecondaryButton data-testid="cancel-edit" onClick={() => setEditing(null)}>
                            Cancel
                          </SecondaryButton>
                        </div>
                      </div>
                    ) : (
                      <pre
                        data-testid="generated-code"
                        className="mt-1 overflow-x-auto rounded-md bg-surface-raised p-3 font-mono text-mono-sm text-ink"
                      >
                        {c.generated_code}
                      </pre>
                    )}
                  </div>

                  {c.validation_errors.length > 0 ? (
                    <div>
                      <Eyebrow>VALIDATION ERRORS</Eyebrow>
                      <ul className="mt-1 flex flex-col gap-1">
                        {c.validation_errors.map((e, i) => (
                          <li key={i} className="font-mono text-mono-xs text-status-failure-ink">
                            {e.check}: {e.message}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  <div className="flex flex-wrap items-center gap-4 border-t border-rule-subtle pt-3">
                    <span className="font-mono text-mono-xs uppercase text-ink-subtle">
                      duplicate score{" "}
                      <span className="text-ink">
                        {c.duplicate_score === null ? "—" : c.duplicate_score.toFixed(2)}
                      </span>
                    </span>
                    {/* §11.5 L885 displays execution status. It is null in this phase
                        and must never read as "passed" (ADR-0205). */}
                    <span
                      data-testid="execution-status"
                      className="font-mono text-mono-xs uppercase text-ink-subtle"
                    >
                      execution{" "}
                      <span className="text-ink">
                        {c.execution_status ?? "not run — sandbox deferred"}
                      </span>
                    </span>
                    {c.is_edited ? (
                      <span
                        data-testid="edited-flag"
                        className="font-mono text-mono-xs uppercase text-ink-subtle"
                      >
                        edited
                      </span>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap items-center gap-2 border-t border-rule-subtle pt-3">
                    <PrimaryButton
                      data-testid="approve-case"
                      disabled={c.human_status === "APPROVED"}
                      onClick={() => review(c.id, "approve")}
                    >
                      Approve
                    </PrimaryButton>
                    <SecondaryButton
                      data-testid="reject-case"
                      disabled={c.human_status === "REJECTED"}
                      onClick={() => review(c.id, "reject")}
                    >
                      Reject
                    </SecondaryButton>
                    <SecondaryButton
                      data-testid="edit-case"
                      onClick={() => {
                        setEditing(c.id);
                        setDraftCode(c.generated_code);
                      }}
                    >
                      Edit
                    </SecondaryButton>
                    <SecondaryButton
                      data-testid="copy-code"
                      onClick={() => void navigator.clipboard?.writeText(c.generated_code)}
                    >
                      Copy code
                    </SecondaryButton>
                    <SecondaryButton data-testid="validate-case" onClick={() => revalidate(c.id)}>
                      Re-validate
                    </SecondaryButton>
                    {/* D3 — code only, this case only. Dashed, because it spends a
                        provider call. */}
                    <AiActionButton
                      action="regenerate"
                      data-testid="regenerate-case"
                      onClick={() => regenerate(c.id)}
                    >
                      Regenerate
                    </AiActionButton>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ) : request && TERMINAL_STATES.has(request.status) && !isFailed ? (
        <EmptyState message="No cases were generated for this request." />
      ) : null}
    </section>
  );
}
