# ADR-0202 — Prompt registry: minimal Phase 2 scope against a fuller §19

**Status:** Accepted (Phase 2, N1) — **corrected against `docs/architecture/design-spec.md` (N0.5)**

## Sources

| Claim | Spec |
|---|---|
| Prompts are version-controlled application assets | §19 L1772 |
| Twelve required per-version fields | §19 L1774–1787 |
| No production deploy without evaluation | §19 L1789 |
| Seven-stage prompt lifecycle | §19 L1791–1807 |
| `prompt_versions` **table** | §15.8 L1542–1551 |
| `model_runs.prompt_version_id` references it | §15.8 L1533 |
| Prompt registry is part of the AI stack | §10.3 L594 |
| **Prompt versioning is P1** | §39 L2907 |

## Context

§19 specifies a substantially richer registry than Phase 2 needs: twelve fields
per version, a seven-stage lifecycle (Draft → Offline evaluation → Review →
Staging → Limited release → Active → Deprecated), a mandatory evaluation gate
before production, and a backing `prompt_versions` table in §15.8.

**§39 L2907 classifies "Prompt versioning" as P1 — strongly recommended, not
required.** Phase 2's deliverables (§38 L2793–2802) do not include it. So the
narrow scope below is a sanctioned priority decision, not a gap in the spec.

An earlier revision of this ADR stated "No database table, no runtime mutation"
as though that were the design. **That was wrong** — §15.8 L1542 specifies a
`prompt_versions` table and §15.8 L1533 has `model_runs.prompt_version_id`
referencing it. Corrected below.

## Decision

**Build the smallest registry that makes prompts versioned, pinned, and
reproducible. Defer the rest to the P1 prompt-versioning work, by name.**

### In scope for Phase 2

`packages/prompt_registry/qe_prompt_registry/` provides:

- **One active test-generation prompt**, resolved by `(name, version)`;
  `version="active"` resolves to the single active version.
- **Source-resident, git-versioned** prompt definitions — the direct reading of
  §19 L1772 ("version-controlled application assets").
- **Rendering with validated inputs** — template variables are validated against
  the version's input schema before rendering, so a missing variable is an error
  at call time rather than a silently-empty prompt section.
- **Immutable versions** — a change means a new version string, which is recorded
  on `test_generation_requests.prompt_version` and `model_runs` so any generated
  artifact traces to the exact prompt that produced it.

Of §19's twelve per-version fields (L1774–1787), Phase 2 carries:

| §19 field | Phase 2 |
|---|---|
| Name, Version | carried |
| Purpose | carried |
| Input schema, Output schema | carried — the output schema is the same Pydantic model handed to `generate_structured` (ADR-0201), so registry and provider contracts cannot drift |
| Prompt template | carried |
| Safety instructions | carried — required by §26.6 (N9), not optional |
| Compatible models | carried — a plain list; enforcement is advisory in Phase 2 |
| Example inputs, Example outputs | **deferred** — feed the §33 evaluation datasets, which are Phase 6 (§38 L2840) |
| Evaluation results | **deferred** — requires the §33 framework (Phase 6) |
| Activation status | **partially** — a version is active or not; the seven-stage lifecycle is deferred |

### Deferred to the P1 prompt-versioning work (§39 L2907)

Named rather than vaguely gestured at:

- The **`prompt_versions` table (§15.8 L1542)** and `model_runs.prompt_version_id`
  as a foreign key. Phase 2 stores the version as a string on `model_runs`; the
  table lands with P1, and the string is forward-compatible with it.
- The **seven-stage lifecycle** (§19 L1791–1807) and the promotion workflow.
- The **evaluation gate before production** (§19 L1789) — unbuildable until §33
  exists in Phase 6.
- Multiple concurrently-active versions, A/B or canary rollout, traffic split.
- Per-organisation or per-project overrides *(inference: §19 is silent on
  multi-tenancy of prompts; deferring is a scope choice, not a sourced one)*.
- Prompt authoring UI and any runtime mutation of prompt text.

## Consequences

- Every generated test case is attributable to an exact, immutable prompt version.
- Phase 2 ships without the §19 evaluation gate — acceptable only because prompt
  versioning is P1 and the gate depends on a Phase 6 framework. It is recorded
  here as a known, deliberate shortfall against §19 L1789, not as compliance.
- The version string is the forward-compatible seam: when `prompt_versions`
  lands, existing rows can be backfilled to foreign keys.
