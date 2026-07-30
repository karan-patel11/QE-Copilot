import type { HealthStatus } from "@/lib/api-client";

// Colour is a reinforcement, never the only signal: the status word is always
// present, so the badge still reads correctly in monochrome.
const STYLES: Record<HealthStatus, string> = {
  healthy: "border-green-300 bg-green-50 text-green-800",
  degraded: "border-amber-300 bg-amber-50 text-amber-900",
  unhealthy: "border-red-300 bg-red-50 text-red-800",
};

export function StatusBadge({ status }: { status: HealthStatus }) {
  return (
    <span
      data-testid="status-badge"
      data-status={status}
      className={`inline-flex shrink-0 items-center rounded-full border px-2.5 py-0.5 text-xs font-medium capitalize ${STYLES[status]}`}
    >
      {status}
    </span>
  );
}
