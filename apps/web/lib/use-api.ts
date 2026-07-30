"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api-client";

export interface ApiState<T> {
  data: T | null;
  error: string | null;
  /** True only while the *first* load is in flight, so refreshes don't blank the page. */
  loading: boolean;
  /** HTTP status of the last failure, so callers can tell 403 from a real error. */
  status: number | null;
  reload: () => void;
}

/**
 * Run an API call and expose its loading / error / data states.
 *
 * `fetcher` must be stable (wrap it in `useCallback`), which is what lets the
 * effect re-run exactly when its inputs change and never on every render.
 */
export function useApi<T>(fetcher: () => Promise<T>): ApiState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [attempt, setAttempt] = useState(0);

  const reload = useCallback(() => setAttempt((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;

    fetcher()
      .then((result) => {
        if (cancelled) return;
        setData(result);
        setError(null);
        setStatus(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setStatus(cause instanceof ApiError ? cause.status : null);
        setError(cause instanceof Error ? cause.message : "Unknown error");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [fetcher, attempt]);

  return { data, error, loading, status, reload };
}
