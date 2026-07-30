"use client";

import { useCallback, useEffect, useState } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/RequestState";
import { StatusBadge } from "@/components/StatusBadge";
import { apiClient, type SystemHealth } from "@/lib/api-client";

const COMPONENT_LABELS: Record<string, string> = {
  api: "API",
  database: "Database",
  redis: "Redis",
  queue: "Queue",
  workers: "Workers",
  scheduler: "Scheduler",
};

const REFRESH_INTERVAL_MS = 15_000;

function formatMetric(key: string, value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (Array.isArray(value)) return value.length > 0 ? value.join(", ") : "none";
  if (key.endsWith("_ms")) return `${value} ms`;
  if (key.endsWith("_seconds")) return `${value} s`;
  return String(value);
}

function humanise(key: string): string {
  return key.replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
}

export default function SystemHealthPage() {
  const [health, setHealth] = useState<SystemHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    try {
      setHealth(await apiClient.systemHealth());
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    // A live view, so it re-measures on an interval rather than showing a
    // snapshot that silently ages.
    const timer = setInterval(() => void load(), REFRESH_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const jobEntries = Object.entries(health?.jobs ?? {}).filter(
    ([, count]) => count > 0,
  );

  return (
    <section>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-gray-900">System Health</h1>
          <p className="mt-2 max-w-2xl text-gray-600">
            Live status of the API, database, cache, queue, workers, and
            scheduler. Measured on every request.
          </p>
        </div>
        {health ? <StatusBadge status={health.status} /> : null}
      </div>

      <div className="mt-6 flex flex-col gap-6">
        {loading && !health ? <LoadingState label="system health" /> : null}
        {error ? (
          <ErrorState message={error} onRetry={() => void load()} />
        ) : null}

        {health ? (
          <>
            <p className="text-xs text-gray-500">
              Checked at {new Date(health.checked_at).toLocaleTimeString()}
            </p>

            <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              {Object.entries(health.components).map(([name, component]) => (
                <li
                  key={name}
                  className="rounded-lg border border-gray-200 p-4"
                  data-testid={`health-component-${name}`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <h2 className="text-sm font-medium text-gray-900">
                      {COMPONENT_LABELS[name] ?? humanise(name)}
                    </h2>
                    <StatusBadge status={component.status} />
                  </div>
                  {component.detail ? (
                    <p className="mt-2 text-xs text-gray-600">
                      {component.detail}
                    </p>
                  ) : null}
                  <dl className="mt-3 flex flex-col gap-1 text-xs text-gray-600">
                    {Object.entries(component.metrics).map(([key, value]) => (
                      <div key={key} className="flex justify-between gap-3">
                        <dt className="text-gray-500">{humanise(key)}</dt>
                        <dd className="truncate font-mono">
                          {formatMetric(key, value)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                </li>
              ))}
            </ul>

            <div>
              <h2 className="text-sm font-medium text-gray-900">
                Jobs by state
              </h2>
              <div className="mt-3">
                {jobEntries.length === 0 ? (
                  <EmptyState message="No jobs have been run in this organisation yet." />
                ) : (
                  <ul className="flex flex-wrap gap-2">
                    {jobEntries.map(([state, count]) => (
                      <li
                        key={state}
                        className="rounded-md border border-gray-200 px-3 py-1.5 text-xs text-gray-700"
                      >
                        <span className="font-mono">{state}</span>
                        <span className="ml-2 font-semibold">{count}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
