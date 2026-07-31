# Phase 2 — Test Generation Plan

Builds on the verified Phase 0/1 foundation (auth, RBAC, organisations/projects,
repositories, Celery+Redis job framework, audit logging, system health, Next.js
shell). Migrations at `0004`; `make check` green at the start of this phase.

## Design-authority note (read first)

`docs/architecture/design-spec.md` **is in this repository and is readable** —
3,155 lines, added in `94a2acd`. Every section this phase cites — §7.1, §11.5,
§12.2, §13.2, §14, §15.6, §15.8, §16.3, §18, §19, §22, §23, §26.6, §30, §32,
§37, §38, §39 — is present and has been read directly.

**This section previously said the opposite**: that `docs/architecture/` held
only `.gitkeep`, that the spec "was not available to read", and that every `§`
reference was therefore *derived* rather than transcribed. That was accurate when
written (`46a3f45`) and became false the moment the spec landed. It then went
uncorrected across the eight commits `94a2acd`–`aa23f1b` — including `efd65cc`,
whose own subject line is "N1 correction — verified against design-spec.md", the
pass that read the spec and corrected ADR-0201 through ADR-0206 while leaving
this section claiming the spec did not exist.

Consequence for readers: **an ADR's own status line is the authority on whether
it was checked against the spec — not this section.** ADR-0201–ADR-0206 carry
"corrected/verified against `docs/architecture/design-spec.md` (N0.5)";
ADR-0207–ADR-0210 were written after the spec landed and cite it directly. Any
claim below that a decision is "derived" or "an inference" must be re-read
against the spec before it is relied on, because a decision derived under the
old caveat may now have a sourced answer.

The §15.8 contradiction this section used to record — Phase 1 citing §15.8 for
`audit_logs` while Phase 2 cited §15.8 for `model_runs`, "both cannot hold" — is
**retracted** (ADR-0203, commit `26ec81d`). §15.8 "AI Governance Tables" contains
both tables: `model_runs` at L1527 and `audit_logs` at L1575. Both citations were
correct all along.

## Architecture Decision Records

| ADR | Decision |
|---|---|
| [ADR-0201](ADR-0201-ai-gateway.md) | AI gateway — `LanguageModelProvider` / `EmbeddingProvider` protocols, Anthropic `claude-opus-5` adapter, `MockProvider`; only this package imports a vendor SDK |
| [ADR-0202](ADR-0202-prompt-registry.md) | Prompt registry — minimal: one active versioned test-gen prompt with pinned input/output schemas; full lifecycle deferred |
| [ADR-0203](ADR-0203-schema-migration.md) | Schema — `test_generation_requests`, `generated_test_cases`, `model_runs` at migration `0005`, under existing org/project tenancy |
| [ADR-0204](ADR-0204-async-boundary.md) | Async boundary — generation is a worker job returning `202` + job id; no blocking generation endpoint |
| [ADR-0205](ADR-0205-validation-scope.md) | Validation — static only (schema, required fields, `ast.parse`, imports, discoverability, duplicates); sandbox execution deferred (P1) |
| [ADR-0206](ADR-0206-test-strategy.md) | Test strategy — deterministic suite on `MockProvider`; contract + eval tiers on the real provider, tolerance-based, CI-skipped |

## Task graph

Topological order; one commit per node; no node starts until its dependencies'
gates are proven with live command output.

- **N0** Context — confirm `make check` green, Phase 1 artifacts present. *(done)*
- **N1** Lock — the six ADRs above. **Hard gate: no implementation code before this commit.**
- **N2** Migration `0005` — round-trip verified on a scratch database. DEPS: N1
- **N3** `qe_prompt_registry` — the single active prompt version, pinned schema. DEPS: N1
- **N4** `qe_ai_gateway` — interfaces, `GroqProvider` adapter (ADR-0210, superseding the Anthropic adapter of ADR-0201), `MockProvider`, retry/timeout, structured-output validation, `model_runs` persistence. DEPS: N1
- **N5** `qe_test_generation` — decompose → generate → pytest codegen → static validation chain. DEPS: N2, N3, N4
- **N6** API — generation endpoints on the Phase 1 job framework; approve/reject/regenerate/validate with audit hooks and RBAC. DEPS: N5
- **N7** Frontend — Test Generator page; nothing auto-approves. DEPS: N6
- **N8** Test suite — deterministic tier green ×3, eval tier excluded from default CI. DEPS: N5, N6
- **N9** Security — prompt-injection containment, redaction before provider calls, generated code never executed, no secrets in prompts/`model_runs`/responses. DEPS: N6, N7
- **N10** Reliability — provider timeout/outage, malformed JSON, oversized input; measured generation latency vs the <90s target. DEPS: N8, N9
- **N11** Completion gate — full task-gate table with live evidence + `PHASE2-BLOCKERS.md`. DEPS: N7, N8, N9, N10

## Out of scope (still `TODO(phase-N)`)

RAG/knowledge base, CI ingestion, defect triage, sandboxed execution of generated
code, prompt authoring UI and rollout, embedding provider implementation.
