// Shared, typed API client — the only boundary the web app uses to reach the
// backend. Feature calls are added here per phase; Phase 0 exposes health/ping.

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export interface PingResponse {
  message: string;
}

export interface ReadinessResponse {
  status: "ready" | "not_ready";
  checks: Record<string, boolean>;
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
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!res.ok) {
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

  return (await res.json()) as T;
}

export const apiClient = {
  ping: (): Promise<PingResponse> => request<PingResponse>("/api/v1/ping"),
  readiness: (): Promise<ReadinessResponse> =>
    request<ReadinessResponse>("/readyz"),
  // TODO(phase-4): testGenerator.*  TODO(phase-5): defectTriage.*
};
