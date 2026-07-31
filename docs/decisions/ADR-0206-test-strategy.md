# ADR-0206 — Test strategy: deterministic on MockProvider, evals tolerance-based and CI-skipped

**Status:** Accepted (Phase 2, N1) — **verified against `docs/architecture/design-spec.md` (N0.5)**

## Sources

The first revision of this ADR cited no section. §32 does exist and is cited now.

| Claim | Spec |
|---|---|
| Unit-test coverage incl. schema validation, prompt assembly, permission checks | §32.1 L2419–2427 |
| Integration-test coverage incl. **AI-provider adapter** | §32.2 L2431–2440 |
| Contract tests incl. **AI structured outputs** | §32.3 L2444–2450 |
| End-to-end flow: log in → upload requirement → generate → approve | §32.4 L2456–2459 |
| AI evaluation tests use **fixed datasets**; measure test-code validity | §32.5 L2468–2479 |
| Security tests incl. prompt injection, secret leakage, unsafe generated-code execution | §32.6 L2483–2493 |
| Unit and integration tests are **P0** | §39 L2898 |

The three-tier structure below maps onto §32 directly: tier 1 covers §32.1/§32.2,
tier 2 is §32.3's "AI structured outputs", tier 3 is §32.5.

**Marked as inference — `design-spec.md` is silent on all of these:** the use of
a `MockProvider` as the substitute in tiers 1–2, excluding the evaluation tier
from the default CI job, tolerance-based rather than exact-match assertions, and
the three-consecutive-clean-runs flakiness gate. §32 specifies *what* to cover,
not *how* to keep it deterministic. These are engineering decisions, not sourced
facts.

## Context

Phase 0 and Phase 1 established a suite that is fully deterministic: `make check`
runs it on every commit and a red result always means a real defect. Introducing
a language model threatens that property in three ways:

1. **Non-determinism.** The same prompt can produce different valid output. On
   `claude-opus-5` there is no `temperature=0` escape hatch — sampling parameters
   are rejected outright (400), so output variance cannot be dialled down.
2. **Network dependence.** A provider outage or rate limit would turn an
   unrelated commit red.
3. **Cost.** A suite that calls a paid API on every push bills every push.

The failure mode to avoid is a suite people learn to ignore. A test that fails
because the model phrased something differently teaches everyone that red means
"probably fine" — at which point the suite has negative value.

## Decision

Three tiers, with a hard rule: **anything that runs in the default CI job is
deterministic and offline.**

### 1. Deterministic suite — `MockProvider`, default CI

Everything except the eval tier. Unit and integration tests for the pipeline,
validation chain, API, RBAC, tenancy, audit, and reliability all run against
`MockProvider` (ADR-0201). No network, no API key, no cost.

This tier asserts **exact** outcomes, because with a stubbed provider the system
is fully deterministic: given this response, these rows exist, this job reaches
`COMPLETED`, this validation error is recorded, this caller gets 403.

Malformed-response handling is tested here too, by programming the mock to
return bad JSON / a schema-violating payload / a timeout — the paths that are
hardest to trigger against a real provider are the easiest to trigger against a
mock. **Gate: zero live-provider calls in this tier** — mechanically checkable,
since an accidental real call fails with no API key configured.

### 2. Contract test — real provider, schema conformance only

A single narrow test that the live provider's structured output still validates
against the pinned Pydantic schema (ADR-0202). It asserts **shape, never
content**: that the response parses and every required field is present and
well-typed. It does not assert what the tests say.

This is the test that catches a provider or model change breaking the
integration. Same marker and skip policy as tier 3.

### 3. Evaluation suite — real provider, tolerance-based, skipped by default

A small fixed set of requirements run against the real provider, scored on
tolerances rather than equality:

- **Tolerance-based, never exact-match.** Assertions are of the form "≥ N cases
  generated", "≥ X% pass static validation", "at least one negative-path case",
  "no case exceeds the size limit". Never `assert output == "..."`.
- **Fixed inputs**, so scores are comparable run to run.
- **Marked `pytest.mark.evaluation` and deselected in the default CI job.** Run
  deliberately — before a prompt version change, before a model change, on a
  schedule — not on every push.
- **Skipped, not failed, when `ANTHROPIC_API_KEY` is absent**, so a contributor
  without a key gets a green local run rather than a misleading red one.

### Flakiness policy

A test that fails intermittently is a defect in the test, not noise to be
retried. The deterministic suite's gate is **three consecutive clean runs** (N8).
No retries, no reruns, no `flaky` markers — if it is not deterministic it does
not belong in tier 1.

## Consequences

- `make check` stays fast, free, offline, and trustworthy.
- Model or prompt regressions are caught by tier 2/3 — deliberately, with a human
  reading the scores — rather than by a mystery red build on an unrelated PR.
- The eval suite is real evidence about model quality precisely because it is
  *not* load-bearing for CI: it can report a degraded score without blocking
  anyone, which is what makes running it honest.
