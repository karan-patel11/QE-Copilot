# ADR-0205 — Validation is static only; sandbox execution is deferred

**Status:** Accepted (Phase 2, N1)

> **Derivation note.** The spec cited as §22.2 (validation) and §23 (sandbox) is
> not in this repository. The Phase 2 brief states sandbox execution is **P1, not
> P0** per §39; that priority is taken as given and is the reason for deferral
> recorded below.

## Context

Generated test code is model output. Before it is shown to a reviewer — let alone
approved — it needs checking. There are two tiers available:

1. **Static analysis** — parse and inspect the code without running it.
2. **Sandboxed execution** — actually run the tests in an isolated environment.

Sandboxed execution is the stronger signal and also the larger, riskier build:
container/VM isolation, resource and time limits, egress control, filesystem
confinement, dependency resolution for arbitrary imports, and a threat model for
running untrusted generated code. Getting any one of those wrong turns a QA
feature into remote code execution.

## Decision

**Phase 2 ships static validation only. No generated code is executed anywhere —
not in the API, not in the worker, not in the test suite, not in CI.**

### The validation chain

Each generated case runs through every check; failures accumulate into
`generated_test_cases.validation_errors` as `[{check, message}]` and set
`validation_status = FAILED`. A failing case is **persisted and surfaced to the
reviewer with its errors**, not silently dropped — a rejected-by-validation case
is information, and dropping it would hide model failure modes.

| Check | What it does | Failure |
|---|---|---|
| **Schema** | Provider response conforms to the pinned Pydantic output schema (ADR-0202) | whole response rejected, bounded retry, then job `FAILED` |
| **Required fields** | `title`, `code`, `test_type`, `priority` present and non-empty | case marked `FAILED` |
| **Pytest syntax** | `ast.parse(code)` — parse only, never `exec`/`eval`/`compile` to a callable | `SyntaxError` recorded with line/offset |
| **Import validation** | Imports extracted from the AST and checked against an allowlist; unresolvable or disallowed imports rejected | recorded per offending import |
| **Test discoverability** | At least one `def test_*` or `class Test*` — a "test" pytest cannot collect is not a test | case marked `FAILED` |
| **Duplicate score** | Similarity against other cases in the same request; near-duplicates linked via `duplicate_of` + `duplicate_score` | flagged, not deleted — the reviewer decides |

`ast.parse` is the whole of the syntax check by design: it builds a tree and
never executes module-level code. Importing the generated module, or calling
`compile()` and then running the result, would execute it — neither happens.

### Deferred: sandbox execution (`TODO(phase-N)`)

Not built in Phase 2, and the reason is recorded rather than left implicit:

- **It is P1, not P0.** The Phase 2 brief is explicit; static validation is what
  P0 requires.
- **It is a security build, not a feature build.** Executing untrusted model
  output safely needs isolation, resource limits, egress policy, and a threat
  model — that is its own phase, not a bolt-on.
- **Half-built is worse than absent.** A sandbox that leaks is strictly more
  dangerous than no sandbox, because it invites trust it hasn't earned.

Until it exists, the honest claim about a generated test is *"it parses, imports
resolve, and pytest could collect it"* — **not** *"it passes"*. The API and UI
must not imply the stronger claim: `validation_status = PASSED` means static
checks passed, and the field is named and documented accordingly.

## Consequences

- No code path in Phase 2 executes generated code — a property that is
  mechanically checkable and gets a named test in N9.
- Reviewers see validation failures with reasons, so a bad generation is
  diagnosable rather than invisible.
- The `validation_errors` corpus is the evidence base for whether a sandbox is
  worth building next, and for what it would need to catch.
