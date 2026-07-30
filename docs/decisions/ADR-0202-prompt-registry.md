# ADR-0202 — Prompt registry: minimal scope, one active versioned prompt

**Status:** Accepted (Phase 2, N1)

> **Derivation note.** The spec cited as §19 is not in this repository
> (`docs/architecture/` holds only `.gitkeep`). The full lifecycle described
> there could not be read; what is deferred below is deferred by name and intent,
> not by transcription.

## Context

Prompts are the least-reviewable part of an LLM system: a one-word edit changes
behaviour with no compiler or type checker to catch it. A registry makes that
change reviewable, attributable, and reproducible.

A *full* prompt lifecycle — authoring UI, A/B rollout, per-tenant overrides,
promotion workflows, drift metrics — is a large surface. Building it now would
be speculative: Phase 2 has exactly one prompt, and no evidence yet about what
its evolution looks like.

## Decision

**Ship the smallest registry that makes prompts versioned, pinned, and
reproducible. Explicitly defer the rest.**

### In scope

`packages/prompt_registry/qe_prompt_registry/` provides:

- **One active test-generation prompt**, identified by a stable id
  (`test_generation`) and a version string (`v1`). Resolution is by
  `(id, version)`; `version="active"` resolves to the single active version.
- **A pinned input/output schema per version.** Each version declares the
  Pydantic model of its template variables *and* the Pydantic model the response
  must conform to. The output model is what gets handed to
  `LanguageModelProvider.complete_structured` (ADR-0201), so the registry's
  contract and the provider's structured-output contract are the same object —
  they cannot drift.
- **Rendering with validated inputs.** Template variables are validated against
  the input schema before rendering, so a missing or misspelled variable is an
  error at call time, not a silently-empty section in the prompt.
- **Immutable versions.** A version's text and schemas never change after it is
  written; a prompt change means a new version. The version string is persisted
  on `test_generation_requests.prompt_version` and `model_runs.prompt_version`
  (ADR-0203), so any generated artifact can be traced to the exact prompt that
  produced it.
- **Prompts live in source**, versioned by git, reviewed as code. No database
  table, no runtime mutation.

### Explicitly deferred (`TODO(phase-N)`)

Recorded so the omission is visible rather than accidental:

- Prompt authoring/editing UI, and any runtime mutation of prompt text.
- Multiple concurrently-active versions, A/B or canary rollout, traffic split.
- Per-organisation or per-project prompt overrides.
- Promotion workflow (draft → staged → active) and approval gates.
- Prompt-level evaluation scoring, regression tracking, and drift alerting.
- A `prompts` database table.

## Consequences

- Every generated test case is attributable to an exact, immutable prompt version.
- Changing the prompt is a reviewed code change with a new version string —
  which also invalidates nothing silently, because old rows keep their old
  version.
- The deferred list is the honest scope boundary: when a later phase needs
  rollout or per-tenant prompts, it starts from a working registry rather than
  from a hard-coded string.
