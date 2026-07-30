// Shared, typed API client — the only boundary the web app uses to reach the
// backend. Every call attaches the stored access token; a 401 clears it so the
// auth gate sends the user back to the login page instead of looping.

import { clearToken, readToken } from "@/lib/token";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export type HealthStatus = "healthy" | "degraded" | "unhealthy";

export type JobState =
  | "PENDING"
  | "QUEUED"
  | "RUNNING"
  | "WAITING_FOR_PROVIDER"
  | "VALIDATING"
  | "COMPLETED"
  | "PARTIALLY_COMPLETED"
  | "FAILED"
  | "CANCELLED"
  | "TIMED_OUT";

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface User {
  id: string;
  organisation_id: string;
  email: string;
  full_name: string | null;
  is_active: boolean;
  roles: string[];
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: User;
}

export interface MeResponse {
  user: User;
  roles: string[];
  permissions: string[];
}

export interface Organisation {
  id: string;
  name: string;
  slug: string;
  created_at: string;
  updated_at: string;
}

export interface Project {
  id: string;
  organisation_id: string;
  name: string;
  slug: string;
  description: string | null;
  created_at: string;
  updated_at: string;
}

export interface Job {
  id: string;
  organisation_id: string;
  project_id: string | null;
  created_by: string | null;
  kind: string;
  state: JobState;
  payload: Record<string, unknown>;
  result: Record<string, unknown> | null;
  error: string | null;
  attempts: number;
  queued_at: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface ComponentHealth {
  status: HealthStatus;
  detail: string | null;
  metrics: Record<string, unknown>;
}

export interface SystemHealth {
  status: HealthStatus;
  checked_at: string;
  components: Record<string, ComponentHealth>;
  jobs: Record<string, number>;
}

export interface ApiErrorBody {
  code: string;
  message: string;
  request_id: string | null;
  details: { field: string | null; message: string }[];
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: ApiErrorBody | null;

  constructor(status: number, body: ApiErrorBody | null, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const token = readToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...((init?.headers as Record<string, string> | undefined) ?? {}),
  };
  if (token) {
    headers.Authorization = `Bearer ${token}`;
  }

  const res = await fetch(`${API_BASE_URL}${path}`, { ...init, headers });

  if (!res.ok) {
    // An expired or revoked token is worth acting on, not just reporting.
    if (res.status === 401) {
      clearToken();
    }
    let body: ApiErrorBody | null = null;
    try {
      const parsed: unknown = await res.json();
      if (parsed && typeof parsed === "object" && "error" in parsed) {
        body = (parsed as { error: ApiErrorBody }).error;
      }
    } catch {
      body = null;
    }
    throw new ApiError(res.status, body, body?.message ?? res.statusText);
  }

  if (res.status === 204) {
    return undefined as T;
  }
  return (await res.json()) as T;
}

export const apiClient = {
  ping: (): Promise<{ message: string }> => request("/api/v1/ping"),
  readiness: (): Promise<{ status: string; checks: Record<string, boolean> }> =>
    request("/readyz"),

  devLogin: (email: string): Promise<TokenResponse> =>
    request("/api/v1/auth/dev/login", {
      method: "POST",
      body: JSON.stringify({ email }),
    }),
  me: (): Promise<MeResponse> => request("/api/v1/auth/me"),

  systemHealth: (): Promise<SystemHealth> => request("/api/v1/system-health"),

  organisations: (): Promise<Organisation[]> =>
    request("/api/v1/organisations"),
  projects: (limit = 50): Promise<Page<Project>> =>
    request(`/api/v1/projects?limit=${limit}`),
  jobs: (limit = 10): Promise<Page<Job>> =>
    request(`/api/v1/jobs?limit=${limit}`),
  users: (limit = 50): Promise<Page<User>> =>
    request(`/api/v1/users?limit=${limit}`),
  createJob: (kind = "health_check"): Promise<Job> =>
    request("/api/v1/jobs", { method: "POST", body: JSON.stringify({ kind }) }),

  // TODO(phase-4): testGenerator.*  TODO(phase-5): defectTriage.*
};
