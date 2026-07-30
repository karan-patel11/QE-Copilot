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
      className="rounded-lg border border-gray-200 p-8 text-sm text-gray-500"
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
      className="rounded-lg border border-red-200 bg-red-50 p-6 text-sm text-red-800"
    >
      <p className="font-medium">Something went wrong</p>
      <p className="mt-1">{message}</p>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="mt-3 rounded-md border border-red-300 bg-white px-3 py-1.5 text-sm font-medium text-red-800 hover:bg-red-100"
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
      className="rounded-lg border border-dashed border-gray-300 p-8 text-sm text-gray-500"
    >
      {message}
    </div>
  );
}
