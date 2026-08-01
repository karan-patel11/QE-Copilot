import type { HealthStatus, JobState } from "@/lib/api-client";

export type BadgeStatus = HealthStatus | JobState;

// T3 semantic tokens only. No stock Tailwind palette class appears here: every
// colour resolves through globals.css, so replacing an approximate hex with the
// real extracted value never touches this file (design-tokens.md §8).
//
// Colour is a reinforcement, never the only signal: the status word is always
// rendered, so the badge still reads correctly in monochrome, under red-green
// colour blindness, and for `pending` vs `muted` — which differ only in shade.
const SEMANTIC = {
  success: "border-status-success bg-status-success-surface text-status-success-ink",
  failure: "border-status-failure bg-status-failure-surface text-status-failure-ink",
  // The border uses the accent (3.19:1 — a UI component); the label uses the ink
  // (7.09:1). Using the accent for text here would be a defect, not a variation.
  partial: "border-status-partial bg-status-partial-surface text-status-partial-ink",
  active: "border-status-active bg-status-active-surface text-status-active-ink",
  pending: "border-status-pending bg-status-pending-surface text-status-pending-ink",
  muted: "border-status-muted bg-status-muted-surface text-status-muted-ink",
} as const;

type Semantic = keyof typeof SEMANTIC;

// The full mapping from design-tokens.md T3 — all ten JobState values and all
// three HealthStatus values. Exhaustive by construction: `Record` over the union
// means a status added to api-client.ts fails the type check here rather than
// falling through to an unstyled badge.
const STATUS_SEMANTIC: Record<BadgeStatus, Semantic> = {
  // JobState
  COMPLETED: "success",
  PARTIALLY_COMPLETED: "partial",
  FAILED: "failure",
  RUNNING: "active",
  WAITING_FOR_PROVIDER: "active",
  VALIDATING: "active",
  PENDING: "pending",
  QUEUED: "pending",
  CANCELLED: "muted",
  TIMED_OUT: "muted",
  // HealthStatus
  healthy: "success",
  degraded: "partial",
  unhealthy: "failure",
};

export function StatusBadge({ status }: { status: BadgeStatus }) {
  const semantic = STATUS_SEMANTIC[status];
  return (
    <span
      data-testid="status-badge"
      data-status={status}
      data-semantic={semantic}
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 font-mono text-mono-xs uppercase ${SEMANTIC[semantic]}`}
    >
      {status}
    </span>
  );
}
