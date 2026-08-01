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


// --- Test generation (§16.3, ADR-0212) --------------------------------------

export type SourceType = "requirement_text" | "user_story" | "acceptance_criteria";
export type TestFramework = "pytest";
export type TestType =
  | "unit"
  | "integration"
  | "positive"
  | "negative"
  | "boundary"
  | "edge_case"
  | "security";
export type TestPriority = "P0" | "P1" | "P2" | "P3";

/** The eleven §11.5 L857-867 options (ADR-0208). */
export interface TestGeneratorConfig {
  test_type: TestType;
  framework: TestFramework;
  target_service: string | null;
  number_of_tests: number;
  include_positive_cases: boolean;
  include_negative_cases: boolean;
  include_boundary_cases: boolean;
  include_security_cases: boolean;
  /** Always false on the wire: the API refuses `true` with 422 (ADR-0212 D2). */
  include_accessibility_cases: boolean;
  desired_priority: TestPriority | null;
  max_generation_cost_usd: number | null;
}

export interface TestGenerationRequestCreate {
  project_id: string;
  title: string;
  source_type: SourceType;
  source_reference: string;
  framework: TestFramework;
  repository_id?: string | null;
  configuration: Partial<TestGeneratorConfig>;
}

export interface TestGenerationRequest {
  id: string;
  project_id: string;
  repository_id: string | null;
  job_id: string | null;
  title: string;
  source_type: string;
  framework: string;
  status: JobState;
  configuration: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  error: string | null;
  /** Structured counterpart to `error` — D5. `PROMPT_TEMPLATE_DRIFT` is not retryable. */
  error_code: string | null;
  /** All four stage prompts — D4. Empty until the pipeline reaches a provider stage. */
  prompt_versions: Record<string, string>;
  case_count: number;
  produced_by_type: Record<string, number>;
  /** Requested kinds no case carries — D6. Reported, never an error. */
  unmet_requested_kinds: string[];
  coverage_notes: string | null;
  model_run_ids: string[];
  validation_passed: number;
  validation_failed: number;
}

export interface TestStep {
  action: string;
  expected: string;
}

export interface GeneratedTestCase {
  id: string;
  request_id: string;
  ordinal: number;
  title: string;
  objective: string;
  preconditions: string | null;
  test_data: Record<string, unknown>;
  steps: TestStep[];
  expected_result: string;
  priority: string;
  tags: string[];
  test_type: string;
  framework: string;
  generated_code: string;
  schema_valid: boolean;
  syntax_valid: boolean;
  validation_errors: { check: string; message: string }[];
  /** Null in this phase — the sandbox is P1 (ADR-0205). Never implies "passed". */
  execution_status: string | null;
  human_status: string;
  duplicate_of: string | null;
  duplicate_score: number | null;
  is_edited: boolean;
  reviewed_by: string | null;
  reviewed_at: string | null;
  created_at: string;
}

export interface TestCaseValidation {
  id: string;
  schema_valid: boolean;
  syntax_valid: boolean;
  validation_status: string;
  validation_errors: { check: string; message: string }[];
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

  // --- Test generation (§16.3) ---
  createGenerationRequest: (
    body: TestGenerationRequestCreate,
    idempotencyKey?: string,
  ): Promise<TestGenerationRequest> =>
    request("/api/v1/test-generation/requests", {
      method: "POST",
      body: JSON.stringify(body),
      // §26.8. A replay returns the original request instead of billing a second
      // generation — and after a dispatch failure it returns that failed row
      // forever, which is why the UI rotates the key rather than reusing it (C-13).
      headers: idempotencyKey ? { "Idempotency-Key": idempotencyKey } : {},
    }),
  generationRequest: (id: string): Promise<TestGenerationRequest> =>
    request(`/api/v1/test-generation/requests/${id}`),
  generationTests: (id: string, limit = 50): Promise<Page<GeneratedTestCase>> =>
    request(`/api/v1/test-generation/requests/${id}/tests?limit=${limit}`),
  approveTest: (id: string, note?: string): Promise<GeneratedTestCase> =>
    request(`/api/v1/generated-tests/${id}/approve`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  rejectTest: (id: string, note?: string): Promise<GeneratedTestCase> =>
    request(`/api/v1/generated-tests/${id}/reject`, {
      method: "POST",
      body: JSON.stringify({ note: note ?? null }),
    }),
  regenerateTest: (
    id: string,
  ): Promise<{ test_id: string; request_id: string; job_id: string }> =>
    request(`/api/v1/generated-tests/${id}/regenerate`, { method: "POST" }),
  validateTest: (id: string): Promise<TestCaseValidation> =>
    request(`/api/v1/generated-tests/${id}/validate`, { method: "POST" }),

  // TODO(phase-5): defectTriage.*
};
