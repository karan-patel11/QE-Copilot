# ADR-0205 — Validation scope: §22.2 levels 1–6; sandbox execution deferred

**Status:** Accepted (Phase 2, N1) — **corrected against `docs/architecture/design-spec.md` (N0.5)**

## Sources

| Claim | Spec |
|---|---|
| Seven validation levels | §22.2 L1975–1983 |
| Failing code is not presented as production-ready | §22.2 L1985 |
| Generated code must not run in the API or worker container | §23 L1991 |
| Sandbox requirements | §23 L1993–2008 |
| Generated-code sandbox is **P1** | §39 L2910 |
| Phase 2 delivers "Static validation" | §38 L2802 |
| `schema_valid`, `syntax_valid`, `execution_status` columns | §15.6 L1484–1487 |

## Correction applied in this pass

The first revision listed five checks plus a "test discoverability" check of my
own invention, and **omitted safety scanning (§22.2 level 6)** — a security
control, not an optional extra. Corrected below.

## Decision

**Implement §22.2 levels 1–6. Level 7 (sandbox execution) is deferred.**

§22.2 L1983 itself calls level 7 "**Optional** sandbox execution"; §39 L2910
classifies the generated-code sandbox as **P1**; and §38 L2802 lists only
"Static validation" among Phase 2's deliverables. The deferral is what the spec
prescribes for this phase, not a shortfall against it.

| # | §22.2 level | Phase 2 |
|---|---|---|
| 1 | JSON/schema validation | response validated against the pinned Pydantic output schema (ADR-0202); failure → bounded retry → job `FAILED` |
| 2 | Required-field validation | per-case: `title`, `objective`, `steps`, `expected_result`, `generated_code`, `priority` |
| 3 | Framework syntax validation | `ast.parse(code)` — builds a tree, never `exec`, `eval`, or `compile` to a callable |
| 4 | Import validation | imports extracted from the AST and checked against an allowlist |
| 5 | Duplicate detection | similarity within the request → `duplicate_score` + `duplicate_of` |
| 6 | **Safety scanning** | **implemented** — scans generated code for destructive or exfiltrating constructs (subprocess/`os.system`, network calls, filesystem writes outside temp, `eval`/`exec`, credential-shaped literals). Flags, never silently strips |
| 7 | Optional sandbox execution | **deferred (P1)** — `execution_status` stays NULL |

Level 6 is doubly required: §32.6 L2493 names "Unsafe generated-code execution"
as a security test, and §26.5 covers sensitive-data handling. It gets a named
test in N9.

*(Inference: §22.2 does not enumerate what safety scanning must detect. The
construct list above is derived from §23's sandbox threat model — no secrets, no
internal metadata services, network disabled — applied statically.)*

### Results are recorded, not discarded

§22.2 L1985: "Generated code that fails validation will not be presented as
production-ready." A failing case is **persisted and shown with its reasons** —
`schema_valid` / `syntax_valid` false, `validation_errors` carrying
`[{check, message}]` — never silently dropped. Dropping it would hide model
failure modes and leave the reviewer guessing.

### Why no execution in Phase 2

§23 L1991 is the binding constraint: "Generated test code must not execute
directly inside the API or worker container." Phase 2 satisfies it the simplest
way available — **nothing executes generated code anywhere**, which is a strict
superset of §23's requirement and is mechanically checkable (N9).

The sandbox §23 L1993–2008 describes (ephemeral container, no privileged mode,
read-only rootfs, CPU/memory limits, execution timeout, no platform secrets, no
metadata services, network off by default with an explicit allowlist, temp
working directory, full cleanup) is a security build, not a feature bolt-on. A
half-built sandbox is more dangerous than none, because it invites trust it has
not earned.

Until it exists, the honest claim about a generated test is *"schema and syntax
valid, imports resolve, no unsafe constructs found"* — **not** *"it passes"*.
`execution_status` being NULL is what carries that distinction in the data, and
the API and UI must not imply the stronger claim.

## Consequences

- All six statically-checkable §22.2 levels ship; the one omission is the one the
  spec marks optional and P1.
- `execution_status` already exists in the schema, so the P1 sandbox needs no
  migration — only a writer.
- The `validation_errors` corpus becomes the evidence base for what a sandbox
  would need to catch.
