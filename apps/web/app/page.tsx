"use client";

import Link from "next/link";
import { useCallback } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/RequestState";
import { StatPanel } from "@/components/StatPanel";
import { StatusBadge } from "@/components/StatusBadge";
import { apiClient, type Job } from "@/lib/api-client";
import { useAuth } from "@/lib/auth";
import { useApi } from "@/lib/use-api";

function relativeTime(iso: string): string {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  if (seconds < 86_400) return `${Math.round(seconds / 3600)}h ago`;
  return `${Math.round(seconds / 86_400)}d ago`;
}

function JobRow({ job }: { job: Job }) {
  return (
    <li
      data-testid="overview-job"
      className="flex items-center justify-between gap-4 border-b border-rule-subtle py-2 last:border-b-0"
    >
      <div className="min-w-0">
        <p className="truncate text-sm text-ink">{job.kind}</p>
        <p className="text-xs text-ink-subtle">{relativeTime(job.created_at)}</p>
      </div>
      <span className="shrink-0 rounded-md border border-rule px-2 py-0.5 font-mono text-xs text-ink-secondary">
        {job.state}
      </span>
    </li>
  );
}

export default function OverviewPage() {
  const { identity } = useAuth();

  const loadProjects = useCallback(() => apiClient.projects(), []);
  const loadJobs = useCallback(() => apiClient.jobs(5), []);
  const loadHealth = useCallback(() => apiClient.systemHealth(), []);

  const projects = useApi(loadProjects);
  const jobs = useApi(loadJobs);
  const health = useApi(loadHealth);

  const anyLoading = projects.loading || jobs.loading || health.loading;

  return (
    <section>
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold text-ink">Overview</h1>
          <p className="mt-2 max-w-2xl text-ink-muted">
            High-level status across CI failures, test generation, and triage.
          </p>
        </div>
        {health.data ? <StatusBadge status={health.data.status} /> : null}
      </div>

      <div className="mt-6 flex flex-col gap-8">
        {anyLoading ? <LoadingState label="your workspace" /> : null}

        {/* Each panel reports its own failure: one broken call should not blank
            the whole page. */}
        {projects.error ? (
          <ErrorState
            message={`Projects could not be loaded: ${projects.error}`}
            onRetry={projects.reload}
          />
        ) : null}
        {jobs.error ? (
          <ErrorState
            message={`Jobs could not be loaded: ${jobs.error}`}
            onRetry={jobs.reload}
          />
        ) : null}
        {health.error ? (
          <ErrorState
            message={`System health could not be loaded: ${health.error}`}
            onRetry={health.reload}
          />
        ) : null}

        {!anyLoading ? (
          <StatPanel
            testId="overview-stats"
            label="Workspace"
            icon="◈"
            meta={identity ? identity.user.email : undefined}
            tiles={[
              { label: "Projects", value: projects.data?.total ?? "—" },
              { label: "Jobs run", value: jobs.data?.total ?? "—" },
              {
                label: "Workers online",
                value:
                  typeof health.data?.components.workers?.metrics.online === "number"
                    ? (health.data.components.workers.metrics.online as number)
                    : "—",
              },
              {
                label: "Queue depth",
                value:
                  typeof health.data?.components.queue?.metrics.depth === "number"
                    ? (health.data.components.queue.metrics.depth as number)
                    : "—",
              },
            ]}
          />
        ) : null}

        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-sm font-medium text-ink">Projects</h2>
            <div className="mt-3">
              {projects.loading ? (
                <LoadingState label="projects" />
              ) : projects.data && projects.data.items.length > 0 ? (
                <ul className="rounded-lg border border-rule px-4">
                  {projects.data.items.slice(0, 5).map((project) => (
                    <li
                      key={project.id}
                      data-testid="overview-project"
                      className="border-b border-rule-subtle py-2 last:border-b-0"
                    >
                      <p className="text-sm text-ink">{project.name}</p>
                      <p className="font-mono text-xs text-ink-subtle">
                        {project.slug}
                      </p>
                    </li>
                  ))}
                </ul>
              ) : projects.error ? null : (
                <EmptyState message="No projects yet. Create one to get started." />
              )}
            </div>
          </div>

          <div>
            <h2 className="text-sm font-medium text-ink">Recent jobs</h2>
            <div className="mt-3">
              {jobs.loading ? (
                <LoadingState label="jobs" />
              ) : jobs.data && jobs.data.items.length > 0 ? (
                <ul className="rounded-lg border border-rule px-4">
                  {jobs.data.items.map((job) => (
                    <JobRow key={job.id} job={job} />
                  ))}
                </ul>
              ) : jobs.error ? null : (
                <EmptyState message="No jobs have been run yet." />
              )}
            </div>
          </div>
        </div>

        <p className="text-sm text-ink-subtle">
          Component detail is on the{" "}
          <Link href="/system-health" className="underline">
            System Health
          </Link>{" "}
          page.
        </p>
      </div>
    </section>
  );
}
