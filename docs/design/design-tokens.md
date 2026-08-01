# Design tokens — N7 design system lock (v2)

**Status:** Locked (Phase 2, N7-DESIGN v2)
**Reference:** racescout.ai, read from screenshots
**Gate:** no N7 component file is written before this document is committed.

## What this supersedes

Nothing on disk. The brief describes v2 as superseding "the beautiful-grid.webflow.io
version", but no `design-tokens.md`, no `N7-DESIGN` document, and no design lock of
any kind exists in this repository or anywhere in its git history. **This is the
first committed design lock.** Recorded so a future reader does not go looking for
a v1 that was never written down.

## Provenance and confidence — read before pixel work

**Every hex below except amber is my derivation from a verbal description of the
reference, not a value read from it.** The brief states there is no CSS access and
that hex values are approximate; I have not seen the screenshots either. So the
values here are chosen to be internally coherent and accessible, and they are
*placeholders for the real extracted values*.

| Token group | Provenance | Confidence |
|---|---|---|
| `amber` | **Invented, user-confirmed** — not in the reference | **Locked** |
| `lime`, `brick`, `navy`, grays | Derived from description | Approximate — confirm against the reference before pixel-perfect work |
| Type families | Chosen to match "geometric sans" + "monospace" | Substitutable; the *roles* in T1 are what is locked |
| Spacing, radii, weights | Ours | Locked |

Swapping an approximate value later is a one-line change in
`apps/web/tailwind.config.ts` **only if** every component consumes the semantic
token rather than a raw hex. That is the point of §8's rule.

---

## T1 — Two-register typography

Two families, strict role separation. This is the defining signature of the
system, so the rule is absolute rather than a default.

| Register | Family | Role |
|---|---|---|
| **Display** | `Space Grotesk` | Page titles, section headers, large numeric readouts (confidence scores, counts), **and body prose at regular weight** |
| **Mono** | `JetBrains Mono` | **All** metadata, without exception |

Both load through `next/font/google`, which self-hosts and subsets at build time —
no runtime request to Google, and no new npm dependency, since `next/font` ships
inside Next 15.

Space Grotesk is a geometric sans with a high x-height and tight default tracking,
and it descends from Space Mono, so the two registers share skeletal DNA rather
than merely coexisting. JetBrains Mono is chosen over the alternatives for
legibility at the 11–12px sizes dense tables actually use.

**"Display" names a role, not a second family.** The same family set at regular
weight and normal tracking carries body copy. That keeps the count at two, which
is what T1 requires.

### What "all metadata" means — the enumerated list

Monospace is mandatory for: timestamps and relative times · job IDs, request IDs,
case IDs, and every UUID · status labels (`COMPLETED`, `PENDING_REVIEW`) · stat
labels in the `GOAL`/`COURSE` register · tag pills · section eyebrow labels ·
prompt version strings (`decompose-v1`) · error codes (`PROMPT_TEMPLATE_DRIFT`) ·
counts rendered inline with a label · file paths and code identifiers.

**This applies platform-wide, including dense table views.** In a table: header
cells use display; body cells showing IDs, timestamps, status, or codes use mono;
body cells showing prose (a failure title, a test objective) use display regular.

Partly established already — `app/page.tsx` renders `job.state` and
`project.slug` in `font-mono` today. T1 makes it a rule instead of a habit.

### Mixed-weight inline headlines

The bold-word-plus-gray-regular-word-on-one-line treatment is **reserved for the
Overview page hero text only**, and is governed by T2.

### Scale

| Token | Size / line-height | Tracking | Register |
|---|---|---|---|
| `display-hero` | 48/52 | −0.03em | Display 700 — Overview hero only |
| `display-xl` | 32/36 | −0.02em | Display 700 — page titles |
| `display-lg` | 24/30 | −0.015em | Display 600 — section headers |
| `display-md` | 18/26 | −0.01em | Display 600 |
| `numeric-xl` | 44/44 | −0.02em | Display 700, tabular figures — stat readouts |
| `body` | 15/24 | 0 | Display 400 |
| `body-sm` | 13/20 | 0 | Display 400 |
| `mono-sm` | 12/18 | 0.01em | Mono 500 |
| `mono-xs` | 11/16 | 0.06em, uppercase | Mono 500 — eyebrows, stat labels |

Numeric readouts set `font-variant-numeric: tabular-nums`, so a polling counter
does not reflow as digits change.

---

## T2 — Marketing tone, scoped

Big bold headlines and the lime highlighter mark appear on **exactly two
surfaces**:

1. The **Overview page's top section** (`/`).
2. **Empty and zero-state screens**, anywhere they occur.

Every functional view — CI Failures, Failure Detail, Test Generator, Defect
Triage, Knowledge Base, Evaluations, Analytics, Integrations, System Health,
Administration — uses a **restrained header**:

```
MONOSPACE EYEBROW LABEL          ← mono-xs, uppercase, gray-500
Plain Bold Title                 ← display-xl, no mark, no oversized type
```

No highlighter marks. No hero type. No mixed-weight headline.

### Why empty states are the exception

An empty state is the one functional moment with nothing to report, so it is the
one moment where a warmer register is honest rather than decorative. A populated
table has data to respect; an empty one has a person to reassure.

### The markup contract

The highlighter mark is a single component rendering:

```html
<mark data-testid="highlight-mark" class="…">approved</mark>
```

Empty states already render `data-testid="empty-state"` (`components/RequestState.tsx`).
**The rule is expressed against those two attributes**, which is what makes the
Playwright guard in §9 mechanical rather than a matter of reviewer vigilance.

---

## T3 — Semantic status palette

### The hard rule, first

> **Colour is never the sole signal.** Every status, severity, and confidence
> indicator renders its fill *together with* the text label or the number.

This is not new. `components/StatusBadge.tsx` already carries the comment
*"Colour is a reinforcement, never the only signal: the status word is always
present, so the badge still reads correctly in monochrome."* T3 extends an
existing convention to the whole palette.

It is load-bearing for the spec, not only for accessibility: §8.3 grounds AI
output in evidence and §25 requires a confidence *score*. A confidence conveyed
by hue alone is a confidence with no evidence attached.

### Values

| Semantic | Accent / fill / bar | Ink (text) | Surface | Contrast (ink on white) |
|---|---|---|---|---|
| **lime** — success, high confidence | `#BEF264` | `#3F6212` | `#F7FEE7` | 7.08:1 ✓ AAA |
| **brick** — failure, low confidence | `#9B2C1E` | `#9B2C1E` | `#FEF2F2` | 7.57:1 ✓ AAA |
| **amber** — partial, medium | `#D97706` | `#92400E` | `#FEF3C7` | 7.09:1 ✓ AAA |
| **navy** — active, in progress | `#1E3A5F` | `#1E3A5F` | `#EFF4F9` | 11.50:1 ✓ AAA |
| **gray-idle** — queued, pending | `#D4D4D8` | `#52525B` | `#F4F4F5` | 7.73:1 ✓ AAA |
| **gray-muted** — cancelled, timed out | `#A1A1AA` | `#3F3F46` | `#FAFAFA` | 10.44:1 ✓ AAA |

**Amber carries two values, deliberately.** `#D97706` is user-confirmed and is
the accent — borders, bar fills, dot indicators, chart segments, all of which are
UI components needing only 3:1 (it measures 3.19:1). It **fails AA as a text
colour** at that ratio, so label text uses `#92400E` instead: 7.09:1 on white and
6.37:1 on the amber surface. Any component using `#D97706` for a text label is a
defect, not a variation.

### Mapping — `JobState` (all ten values)

| State | Semantic |
|---|---|
| `COMPLETED` | lime |
| `PARTIALLY_COMPLETED` | amber |
| `FAILED` | brick |
| `RUNNING`, `WAITING_FOR_PROVIDER`, `VALIDATING` | navy |
| `PENDING`, `QUEUED` | gray-idle |
| `CANCELLED`, `TIMED_OUT` | gray-muted |

### Mapping — the other status enums

| Enum | Value → semantic |
|---|---|
| `HealthStatus` | `healthy` → lime · `degraded` → amber · `unhealthy` → brick |
| `TestCaseStatus` | `APPROVED` → lime · `REJECTED` → brick · `PENDING_REVIEW` → gray-idle |
| `ValidationStatus` | `PASSED` → lime · `FAILED` → brick |
| Confidence (§25) | ≥0.75 lime · 0.40–0.74 amber · <0.40 brick — **always with the numeric score** |

`StatusBadge.tsx` currently uses stock Tailwind `green`/`amber`/`red` and must
migrate to these semantics. That is the first component change of N7.

### Two known weaknesses, stated

- **gray-idle vs gray-muted differ only in shade**, not hue. A user cannot
  reliably tell `QUEUED` from `CANCELLED` by colour. Accepted, because the hard
  rule means the word is always present — and because inventing a seventh hue for
  a terminal-but-uninteresting state would spend signal where none is needed.
- **amber vs lime is the pair most likely to collapse** under deuteranopia and
  protanopia. `#D97706` was chosen over the more orange `#B45309` with that
  tradeoff on the table. The hard rule is what keeps the interface usable for
  affected users; it is the reason the rule cannot be relaxed later for a
  "cleaner" icon-only badge.

---

## T4 — Three button tiers, and a reserved one

| Tier | Appearance | Use |
|---|---|---|
| **Primary** | Solid black pill, white text | The single main CTA per view — Approve, Submit, Save |
| **Secondary** | White pill, black border, optional arrow | View, Cancel, Export, Download |
| **AI action** | **Dashed border pill + icon** | **Reserved.** AI-triggered actions only |

The dashed variant (reference: "GET MY FIT") is **exclusive to actions that spend
a provider call**. It must never be used as a generic secondary button.

### The allowlist

```ts
export const AI_ACTIONS = [
  "run-ai-analysis",   // Run AI Analysis
  "generate-tests",    // Generate Tests
  "run-triage",        // Run Triage
  "regenerate",        // Regenerate  (ADR-0212 D3 — one case, codegen only)
] as const;
```

The visual weight is doing real work here: every dashed pill in the product is an
action that costs money and produces a `model_runs` row. Diluting it into a
generic button style would erase the one affordance that distinguishes a free
action from a billed one.

**Enforced twice** — a TypeScript union so a wrong label is a compile error, and a
Playwright guard so a hand-rolled `<div>` with dashed borders is a test failure.
The type check is the one that catches it earliest; the runtime check is the one
that catches someone bypassing the component.

---

## T5 — Stat panel: one component, three surfaces

The reference's "Sample Report" / "The Index" panel is structurally a dashboard
already. Its anatomy, top to bottom:

```
┌──────────────────────────────────────────────────────┐
│ ◈ ICON  MONO LABEL              MONO METADATA RIGHT  │  header row
├──────────────────────────────────────────────────────┤
│ 277                                                  │  numeric readout
│                                                      │
│ GOAL      ████████████████░░░░░░░░░░          0.82   │  bar rows,
│ COURSE    ██████████░░░░░░░░░░░░░░░░          0.51   │  right-aligned
│ WEATHER   ████████████████████████░░          0.94   │  numeric value
│                                                      │
│ ┌────────┐ ┌────────┐ ┌────────┐                     │  stat-tile
│ │  12    │ │   4    │ │  0.7s  │                     │  mini-grid
│ │ PASSED │ │ FAILED │ │ MEDIAN │                     │
│ └────────┘ └────────┘ └────────┘                     │
│                                                      │
│ ⬤ entitlement  ⬤ playback  ⬤ regression              │  tag pills
└──────────────────────────────────────────────────────┘
```

**Built once as `<StatPanel>`, with slots.** Not bespoke per page.

| Surface | Uses |
|---|---|
| Failure Detail — AI Summary + Evidence (§11.4) | header, readout, bar rows, tags |
| Confidence score (§25) | bar rows with numeric value — the exact GOAL/COURSE/WEATHER pattern |
| Evaluations — metric comparison (§11.8) | readout, bar rows, stat tiles |
| Overview cards | readout, stat tiles |

Every bar row renders its numeric value at the right edge. That is the §25 rule
expressed as layout: the bar is the reinforcement, the number is the signal.

The existing `components/StatCard.tsx` is a proto-version of the stat-tile
sub-element and folds into `<StatPanel>`'s tile grid rather than surviving
alongside it.

---

## T6 — Hero-block card treatment: excluded from every current view

The coloured hero-block card header — dark navy / maroon / forest green with
vertical-line texture, monospace corner metadata, brand-colour title — is
distinctive and is **reserved for genuinely card-based surfaces only**.

**No current N7 view qualifies.**

| View | Shape | Card treatment |
|---|---|---|
| CI Failures | dense table | **Never** — unchanged from v1's T1 exclusion |
| Generated-test results | dense list | **Never** |
| Failure Detail | stacked panels | No — uses T5 |
| Knowledge Base, Evaluations, Analytics | tables / panels | No |
| A future "Saved Filters" or "Recent Failures" widget | card grid | The only plausible candidate |

Until such a surface exists, the treatment is specified but unbuilt. Building it
speculatively would create the thing a later PR reaches for when it wants a page
to look more interesting — which is exactly how the exclusion gets violated.

---

## T7 — Adopt as-is

Direct adoptions, no judgment call.

- **Tag pills.** `rounded-full`, surface `#F4F4F5`, mono-xs text, optional 12px
  leading icon. For generated-test tags, failure-category chips, knowledge-doc
  metadata.
- **Hairline dividers.** 1px `#E4E4E7` between major page sections. Not between
  every row — rows use spacing; sections use rules.
- **Eyebrow labels.** Mono-xs, uppercase, `0.06em` tracking, `#71717A`, above
  **every** section header. `HOW IT WORKS` → `CI FAILURES`; `THE DIRECTORY` →
  the section name.

---

## T8 — Neutral ramp (added at N7-TOKENS-RAMP, closes C-16)

The original lock defined six *status* semantics plus `rule`, `pill`, `eyebrow`
and `highlight` — and **no neutral ramp**. There was no token for body text, for
secondary text, or for a default border, so every page legitimately fell back to
stock `gray-*`: 87 instances across `components/` and `app/`. That was a gap in
the lock, not in the components (C-16).

Zinc-based, because the status surfaces and furniture already used zinc values —
this unifies them rather than introducing a second neutral family. `--rule`,
`--pill-surface` and `--eyebrow-ink` are now aliases onto ramp steps, so the
furniture and the neutrals cannot drift into two names for one colour.

**Every ratio below was produced by a script and re-checked against the committed
values, not estimated.** The generator is the same one used for the T3 palette.

### Neutral ramp — raw steps

| Step | Hex | vs white | vs `#18181B` |
|---|---|---|---|
| `neutral-0` | `#FFFFFF` | 1.00:1 | 17.72:1 |
| `neutral-50` | `#FAFAFA` | 1.04:1 | 16.97:1 |
| `neutral-100` | `#F4F4F5` | 1.10:1 | 16.12:1 |
| `neutral-200` | `#E4E4E7` | 1.27:1 | 13.96:1 |
| `neutral-300` | `#D4D4D8` | 1.48:1 | 11.99:1 |
| `neutral-400` | `#A1A1AA` | 2.56:1 | 6.91:1 |
| `neutral-500` | `#71717A` | 4.83:1 | 3.67:1 |
| `neutral-600` | `#52525B` | 7.73:1 | 2.29:1 |
| `neutral-700` | `#3F3F46` | 10.44:1 | 1.70:1 |
| `neutral-900` | `#18181B` | 17.72:1 | 1.00:1 |

### Text (ink) roles — contrast against both surfaces

| Token | Step | Hex | On light `#FFFFFF` | On dark `#18181B` | Role |
|---|---|---|---|---|---|
| `ink` | `neutral-900` | `#18181B` | 17.72:1 AAA | 1.00:1 fail | primary text, headings |
| `ink-secondary` | `neutral-700` | `#3F3F46` | 10.44:1 AAA | 1.70:1 fail | secondary text, table cells |
| `ink-muted` | `neutral-600` | `#52525B` | 7.73:1 AAA | 2.29:1 fail | body prose, descriptions |
| `ink-subtle` | `neutral-500` | `#71717A` | 4.83:1 AA | 3.67:1 AA-large | hints, eyebrows, captions |
| `ink-inverse` | `neutral-0` | `#FFFFFF` | 1.00:1 fail | 17.72:1 AAA | text on surface-inverse |

### Non-text roles (borders/surfaces — 3:1 is the bar, and only against what they sit on)

| Token | Hex | vs white | Note |
|---|---|---|---|
| `rule-subtle` | `#F4F4F5` | 1.10:1 | row dividers on white |
| `rule` | `#E4E4E7` | 1.27:1 | default border on white |
| `rule-strong` | `#D4D4D8` | 1.48:1 | input borders on white |
| `surface-raised` | `#FAFAFA` | 1.04:1 | sidebar, subtle panel |
| `surface-hover` | `#F4F4F5` | 1.10:1 | hover state |
| `surface-active` | `#E4E4E7` | 1.27:1 | active nav item |
| `surface-inverse` | `#18181B` | 17.72:1 | primary button fill |
| `surface-disabled` | `#A1A1AA` | 2.56:1 | disabled button fill |

### There is deliberately no `ink-faint`

The obvious fifth text step, `neutral-400` (`#A1A1AA`), measures **2.56:1 on
white** — below AA for text (4.5:1) and below even the 3:1 non-text bar. The
script flagged it, which is the reason it does not exist as a token: shipping a
text colour that cannot legally carry text only invites its use.

The codebase had exactly one `text-gray-400` (`Sidebar.tsx`), and it migrated to
`ink-subtle` (4.83:1 AA). That is an accessibility **fix**, not a rename.

`surface-disabled` keeps `neutral-400` as a *fill*, which is acceptable only
because WCAG 1.4.3 exempts disabled controls. It is not a precedent for anything
enabled.

### Dark-surface column

Ratios are given against `#18181B` as well as white because `surface-inverse`
exists (the T4 primary button, and any future dark panel). The column shows which
inks survive there: only `ink-inverse` is usable on the inverse surface, and
`ink-subtle` is the sole ramp step that clears a bar on **both** — 4.83:1 light,
3.67:1 dark. Worth knowing before anyone builds a dark panel and reaches for
`ink-muted` out of habit.

---

## 8 — How the tokens are implemented

Two layers, and components may read **only** the second.

**Layer 1 — CSS custom properties** in `app/globals.css`, under `:root`. One
declaration per raw value. This is the only place a hex literal appears.

**Layer 2 — semantic Tailwind tokens** in `tailwind.config.ts` `theme.extend`,
every one resolving to a `var(--…)`:

```ts
colors: {
  status: {
    lime:  { DEFAULT: "var(--status-lime)",  ink: "var(--status-lime-ink)",  surface: "…" },
    amber: { DEFAULT: "var(--status-amber)", ink: "var(--status-amber-ink)", surface: "…" },
    // brick, navy, idle, muted
  },
}
```

**The rule:** a component writes `text-status-amber-ink`, never `text-[#92400E]`
and never `text-amber-700`. Two consequences, both deliberate — replacing an
approximate hex with the real extracted value touches one line, and a stock
Tailwind palette class in a component becomes a reviewable mistake rather than an
invisible one.

`theme.extend` is currently `{}`, so none of this collides with existing config.

---

## 9 — Enforcement

Three Playwright specs extend the existing suite in `apps/web/e2e/`, matching its
established `data-testid` convention.

### (a) Highlighter marks confined to Overview and empty states

For every route except `/`: every `[data-testid="highlight-mark"]` must have a
`[data-testid="empty-state"]` ancestor. Zero marks with no empty-state ancestor.

Expressed as an ancestor relationship rather than a per-route allowlist, because
empty states legitimately appear *inside* functional pages, and a route-level
allowlist would have to be edited every time a page is added — which is how the
check would come to be disabled.

### (b) Dashed pill only with an allowlisted AI action

Across every route: every `[data-variant="ai-action"]` carries a `data-ai-action`
attribute whose value is in `AI_ACTIONS`. Backed by the TypeScript union, so the
common case fails at compile time and this catches the bypass.

### (c) CI Failures stays a dense table

On `/ci-failures`: a `table` (or `[data-testid="failures-table"]`) is present,
and `[data-variant="hero-card"]` has count 0.

### Where they live, and why they need their own config

Committed as `apps/web/e2e/design-lock.spec.ts`, run by
`npm run test:e2e:design` against `playwright.design-lock.config.ts`.

They need a **dev** server. `/dev/tokens` is the only surface rendering the
dashed AI-action pill today, and `middleware.ts` returns a real 404 for `/dev/*`
in a production build — correctly. The default `playwright.config.ts` runs
`next build && next start`, so it can never exercise guard (b). Rather than
weaken that config so a design check could pass, the guards got their own, and
the default config now ignores this spec.

### Each guard is written twice

Every guard has a matching *non-vacuity* test that injects the violation and
asserts the predicate rejects it. A guard that only ever runs where there is
nothing to find passes forever and proves nothing — which is exactly how C-2 and
C-3 happened. The injected half is what makes the passing half mean something.

### What these checks do *not* cover

They are structural, not visual. They cannot catch a wrong shade, bad spacing, or
a mono/display swap. **Visual regression is not part of this lock** — the brief
mentions "visual-regression check", and Playwright screenshot baselines are a
real option, but committing baseline images before the components exist would
bake in placeholder hexes as the reference. Deferred, and named here so it is a
decision rather than an omission.

---

## 10 — Open items

| # | Item | Owner |
|---|---|---|
| 1 | Confirm `lime`, `brick`, `navy`, gray hexes against the actual reference; replace in `globals.css` | N7 |
| 2 | Confirm `Space Grotesk` / `JetBrains Mono` are acceptable stand-ins for the reference's actual families | N7 |
| 3 | Visual-regression baselines, once components exist | N8 |
| 4 | Guard (c)'s positive half — "`/ci-failures` renders a dense table" — activates when that page stops being a placeholder. The hero-card exclusion is enforced now. | N7 pages |
| 5 | Hero-block card treatment (T6) stays unbuilt until a card-based surface exists | future |

## Consequences

- Two families, two registers, and a rule for which is which that a reviewer can
  apply without asking.
- The marketing register cannot leak into functional views by accident, because a
  test fails when it does.
- Every status colour has an AA-or-better ink paired with it, and every indicator
  shows its word or number regardless.
- The dashed pill continues to mean "this spends money".
- Replacing an approximate colour with a real one is a one-line change.
