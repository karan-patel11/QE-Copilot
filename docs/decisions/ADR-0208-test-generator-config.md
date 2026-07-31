# ADR-0208 — Test Generator configuration: the eleven options

**Status:** Accepted (Phase 2, N1) — feeds N7

## Sources

| Claim | Spec |
|---|---|
| The eleven configuration options | §11.5 L855–867 |
| `configuration` column on the request | §15.6 L1467 |
| Fields each generated test displays | §11.5 L873–885 |
| Decomposition outputs the config selects against | §22.1 L1962–1971 (ADR-0207) |
| Framework vocabulary | ADR-0203, `qe_common.test_generation.TestFramework` |

## Context

§11.5 L855–867 lists eleven configuration options for the Test Generator page.
§15.6 gives `test_generation_requests` a single `configuration` column to hold
them. Two things need deciding before N7: what the eleven keys are called and
what they accept, and which of them Phase 2 can actually honour.

## Decision

### One JSONB column, not eleven columns

`configuration` stays a single JSONB object, as §15.6 specifies. The set is
expected to grow across phases (§11.5 is the Phase 2 view of a page that later
phases extend), and eleven nullable columns that later become twenty is a
migration per option. The cost is that the database does not enforce the shape —
so the API validates it on the way in, and an invalid `configuration` is
rejected at the boundary rather than discovered in the worker.

### The eleven keys

| # | Spec option | Key | Type | Default | Phase 2 |
|---|---|---|---|---|---|
| 1 | Test type | `test_type` | enum `TestType` | `unit` | honoured |
| 2 | Framework | `framework` | enum `TestFramework` | `pytest` | honoured |
| 3 | Target service | `target_service` | string \| null | `null` | honoured |
| 4 | Number of tests | `number_of_tests` | int 1–20 | `5` | honoured |
| 5 | Include positive cases | `include_positive_cases` | bool | `true` | honoured |
| 6 | Include negative cases | `include_negative_cases` | bool | `true` | honoured |
| 7 | Include boundary cases | `include_boundary_cases` | bool | `true` | honoured |
| 8 | Include security cases | `include_security_cases` | bool | `false` | honoured |
| 9 | Include accessibility cases | `include_accessibility_cases` | bool | `false` | **rejected** |
| 10 | Desired test priority | `desired_priority` | enum `TestPriority` \| null | `null` | honoured |
| 11 | Maximum generation cost | `max_generation_cost_usd` | decimal \| null | `null` | honoured |

`framework` duplicates the request's `framework` column deliberately: the column
is the one the worker and the code generator read, and the config key is what
the page submits. The API copies key → column on create and the column wins.

### Defaults are stored, not implied

The API writes the full eleven-key object, defaults included. A `configuration`
that omits `include_security_cases` is ambiguous once the default changes: it
could mean "the requester declined security cases" or "this request predates the
option". Storing the resolved set makes every historical request explain itself,
which matters because `configuration` is the record of what was asked for.

### `number_of_tests` is capped at 20

§11.5 gives no bound. A bound is required anyway: the value drives the size of
one model response, and an unbounded request is an unbounded cost and an
unbounded latency for a synchronous-feeling page. 20 is a starting cap, not a
spec value, and is recorded here as a Phase 2 choice to revisit — not as a
constraint the spec imposes.

### `include_accessibility_cases` is rejected, not silently ignored

This is the one option Phase 2 cannot honour. Accessibility testing needs a
rendered UI to assert against; Phase 2 generates `pytest` code from requirement
text (ADR-0203, ADR-0205) and has no browser, no DOM and no axe-style ruleset.

Accepting the flag and returning ordinary tests would be worse than refusing it:
the requester would receive tests labelled as covering accessibility that do not,
and `include_accessibility_cases: true` would sit in `configuration` as a record
of a promise that was never kept. So the API **rejects** the request with a
422 naming the option as unsupported in this phase. The key stays in the schema
with default `false` so the shape does not change when a later phase implements
it.

### `max_generation_cost_usd` is a pre-flight ceiling, not a mid-flight abort

Checked before the generation call against the estimated cost of the request;
if the estimate exceeds it, the request is rejected before any provider call.
It does **not** interrupt a call in progress — the gateway (ADR-0201) bills a
completed call whether or not we stop reading it, so aborting mid-stream would
spend the money and discard the result. Actual cost lands in
`model_runs.estimated_cost` and may exceed the ceiling; the ceiling governs what
we agree to start, and that limitation is stated rather than papered over.

### The `include_*` flags are requests, not guarantees

They shape the prompt and are checked against what came back — a request with
`include_negative_cases: true` that yields no case with `test_type = negative`
is reported in the request `summary`. They are not enforced by rejecting model
output, because a requirement with no failure path (ADR-0207's
`failure_conditions: []`) legitimately produces no negative cases. Reporting the
gap is honest; fabricating a negative case to satisfy a flag is not.

## Alternatives considered

**Accept `include_accessibility_cases` and ignore it.** Rejected — it records a
promise the phase cannot keep, in a column that outlives the phase.

**Drop the key entirely until it is supported.** Rejected — §11.5 lists eleven
options, and an absent key makes the Phase 2 config shape a different shape from
the spec's, which N7 and later phases would both have to special-case.

**Enforce the `include_*` flags on model output.** Rejected — see above; it
trades a reportable gap for a fabricated test.

## Consequences

- N7 renders eleven controls, one disabled with a reason (accessibility).
- The API owns config validation; the worker may assume a resolved eleven-key
  object and does not re-derive defaults.
- `max_generation_cost_usd` is a ceiling on what is started, not on what is
  spent. Stated in the ADR and surfaced in the UI copy.
- `number_of_tests`' cap of 20 is ours, not the spec's, and is marked for
  revisit.
