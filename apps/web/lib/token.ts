// Access-token storage (ADR-0110).
//
// localStorage, read on demand rather than held in module state, so a token
// written by another tab is picked up on the next request. Cookie-based
// sessions with CSRF protection arrive with server-side sessions —
// TODO(phase-6).

export const TOKEN_STORAGE_KEY = "qe-copilot.access-token";

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). Treating that
    // as "signed out" is better than crashing the whole app.
    return null;
  }
}

export function storeToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
  } catch {
    // Ignored: the session simply will not persist across reloads.
  }
}

export function clearToken(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignored.
  }
}
