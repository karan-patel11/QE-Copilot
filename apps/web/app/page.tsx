"use client";

import Link from "next/link";
import { useCallback } from "react";

import { EmptyState, ErrorState, LoadingState } from "@/components/RequestState";
import { StatCard } from "@/components/StatCard";
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
      className="flex items-center justify-between gap-4 border-b border-gray-100 py-2 last:border-b-0"
    >
      <div className="min-w-0">
        <p className="truncate text-sm text-gray-900">{job.kind}</p>
        <p className="text-xs text-gray-500">{relativeTime(job.created_at)}</p>
      </div>
      <span className="shrink-0 rounded-md border border-gray-200 px-2 py-0.5 font-mono text-xs text-gray-700">
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
          <h1 className="text-2xl font-semibold text-gray-900">Overview</h1>
          <p className="mt-2 max-w-2xl text-gray-600">
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
          <div
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
            data-testid="overview-stats"
          >
            <StatCard
              label="Projects"
              value={projects.data?.total ?? "—"}
              hint={identity ? `Signed in as ${identity.user.email}` : undefined}
            />
            <StatCard label="Jobs run" value={jobs.data?.total ?? "—"} />
            <StatCard
              label="Workers online"
              value={
                typeof health.data?.components.workers?.metrics.online === "number"
                  ? (health.data.components.workers.metrics.online as number)
                  : "—"
              }
            />
            <StatCard
              label="Queue depth"
              value={
                typeof health.data?.components.queue?.metrics.depth === "number"
                  ? (health.data.components.queue.metrics.depth as number)
                  : "—"
              }
            />
          </div>
        ) : null}

        <div className="grid gap-8 lg:grid-cols-2">
          <div>
            <h2 className="text-sm font-medium text-gray-900">Projects</h2>
            <div className="mt-3">
              {projects.loading ? (
                <LoadingState label="projects" />
              ) : projects.data && projects.data.items.length > 0 ? (
                <ul className="rounded-lg border border-gray-200 px-4">
                  {projects.data.items.slice(0, 5).map((project) => (
                    <li
                      key={project.id}
                      data-testid="overview-project"
                      className="border-b border-gray-100 py-2 last:border-b-0"
                    >
                      <p className="text-sm text-gray-900">{project.name}</p>
                      <p className="font-mono text-xs text-gray-500">
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
            <h2 className="text-sm font-medium text-gray-900">Recent jobs</h2>
            <div className="mt-3">
              {jobs.loading ? (
                <LoadingState label="jobs" />
              ) : jobs.data && jobs.data.items.length > 0 ? (
                <ul className="rounded-lg border border-gray-200 px-4">
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

        <p className="text-sm text-gray-500">
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
