# ADR-0207 — Requirement decomposition: the ten outputs

**Status:** Accepted (Phase 2, N1) — feeds N5

## Sources

| Claim | Spec |
|---|---|
| The ten decomposition outputs | §22.1 L1962–1971 |
| Position of decomposition in the pipeline | §22 L1931–1955 |
| Input sources that reach decomposition | §11.5 L845–853 |
| Validation levels applied downstream | §22.2 L1977–1983 |

## Context

§22 places **requirement decomposition** third in the pipeline, after input
validation and before entity/constraint extraction, risk identification and
test-plan generation. It is the first step whose output is structured: it turns
one untrusted blob of requirement text into named fields that every later step
reads. If its shape is not fixed now, N5 will invent one and N6/N7 will be built
against an invention rather than the spec.

## Decision

Decomposition produces exactly the **ten** outputs §22.1 L1962–1971 lists, under these
names, as one JSON object. The list is closed for Phase 2: no additions, no
renames, no silent omissions.

| # | Output | Field | Type | Empty when |
|---|---|---|---|---|
| 1 | Actors | `actors` | `string[]` | no actor is identifiable |
| 2 | Preconditions | `preconditions` | `string[]` | the requirement states none |
| 3 | Actions | `actions` | `string[]` | never — see below |
| 4 | Business rules | `business_rules` | `string[]` | the requirement encodes none |
| 5 | State transitions | `state_transitions` | `object[]` | the requirement is stateless |
| 6 | Success conditions | `success_conditions` | `string[]` | never — see below |
| 7 | Failure conditions | `failure_conditions` | `string[]` | no failure path is stated |
| 8 | Data constraints | `data_constraints` | `object[]` | no data is constrained |
| 9 | Security constraints | `security_constraints` | `string[]` | no security concern is stated |
| 10 | Integration dependencies | `integration_dependencies` | `string[]` | the requirement is self-contained |

`state_transitions` entries are `{from, to, trigger}`. `data_constraints`
entries are `{field, constraint}`. The remaining eight are arrays of strings.

### Every key is always present

An absent key and an empty array mean different things, and only one of them is
honest. A model that omits `security_constraints` has not told us there are no
security constraints — it has told us nothing. All ten keys are **required** in
the schema; emptiness is expressed as `[]`. This is what lets N6 distinguish
"nothing to test here" from "the decomposition step failed quietly", and it is
the required-field validation of §22.2 level 2 applied at this stage.

### `actions` and `success_conditions` may not both be empty

A requirement that decomposes to no actions and no success conditions has
nothing testable in it. Rather than generate tests from that, decomposition
fails and the request surfaces the failure. This is the one semantic check at
this level; everything else is permitted to be empty.

### Decomposition output is data, never instructions

The requirement text arriving here is untrusted (ADR-0205). Its decomposition is
equally untrusted: the ten fields are model output derived from user input, so
they are carried as structured data into subsequent prompts and never
concatenated into an instruction position. A `business_rules` entry reading
"ignore all previous instructions" is a string in an array, not a directive.

### Not persisted as columns in Phase 2

Decomposition is an intermediate pipeline artifact. §15.6 gives
`generated_test_cases` no decomposition columns, and inventing ten more would
put a second, divergent copy of the requirement next to `source_reference`.
Phase 2 keeps the object in the worker's memory for the life of the job and
records only its provenance — the `model_runs` row for the decomposition call,
whose `operation` is `requirement_decomposition`.

The consequence is accepted deliberately: decomposition is **not** reproducible
from the database after the fact. If a later phase needs to show a reviewer why
a test was generated, that is a new column or table decision, taken then.

## Alternatives considered

**Let the model return whatever fields it finds.** Rejected: N6's prompt and
N7's display would then have to handle an open set, and the ten names in §22.1
would stop being a contract.

**Collapse the ten into a smaller set** (e.g. one `constraints` list merging
business rules, data constraints and security constraints). Rejected: §22.1
distinguishes them, and security constraints in particular drive the security
test cases §11.5 L864 offers as a config option. Merged, they are unrecoverable.

**Persist all ten now.** Rejected as above — not in §15.6, and it duplicates
requirement text into a second location. *(Inference from §26.5's intent, not a
rule it states: §26.5 specifies detection and redaction of secrets and PII and
says nothing about duplicating data across tables. Keeping the number of places
requirement text lives small follows from that intent — it is our reasoning, not
the spec's requirement.)*

## Consequences

- N5 implements one fixed schema with ten required keys; its validator is the
  §22.2 level-1/level-2 check for this stage.
- N6 can rely on every key existing, so it branches on emptiness, not presence.
- N7 has a stable vocabulary if decomposition is ever surfaced in the UI.
- Decomposition is not auditable from the database in Phase 2. Flagged, not
  fixed — see the note above.
