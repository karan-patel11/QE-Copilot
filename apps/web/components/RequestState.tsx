"use client";

// The three states every data-backed page has to render: in flight, failed, and
// succeeded-but-empty. Sharing them keeps the wording and markup consistent —
// and makes it obvious when a page has forgotten one.

export function LoadingState({ label }: { label: string }) {
  return (
    <div
      role="status"
      aria-busy="true"
      data-testid="loading-state"
      className="rounded-lg border border-rule p-8 text-sm text-ink-subtle"
    >
      Loading {label}…
    </div>
  );
}

export function ErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      data-testid="error-state"
      className="rounded-lg border border-status-failure bg-status-failure-surface p-6 text-sm text-status-failure-ink"
    >
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-status-failure bg-surface px-3 py-1.5 text-sm font-medium text-status-failure-ink hover:bg-status-failure-surface"
        >
          Try again
        </button>
      ) : null}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return (
    <div
      data-testid="empty-state"
      className="rounded-lg border border-dashed border-rule-strong p-8 text-sm text-ink-subtle"
    >
      {message}
    </div>
  );
}
