"use client";

// Client-side session state (ADR-0110). The token lives in localStorage; this
// context holds the identity resolved from it so components read the caller's
// roles and permissions without each re-fetching /auth/me.

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { ApiError, apiClient, type MeResponse } from "@/lib/api-client";
import { clearToken, readToken, storeToken } from "@/lib/token";

export type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  status: AuthStatus;
  identity: MeResponse | null;
  error: string | null;
  signIn: (email: string) => Promise<void>;
  signOut: () => void;
  hasPermission: (permission: string) => boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = useState<AuthStatus>("loading");
  const [identity, setIdentity] = useState<MeResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Resolve the stored token once on mount. A token that no longer identifies
  // an active user is treated as no token at all.
  useEffect(() => {
    let cancelled = false;

    if (!readToken()) {
      setStatus("anonymous");
      return;
    }
    apiClient
      .me()
      .then((me) => {
        if (cancelled) return;
        setIdentity(me);
        setStatus("authenticated");
      })
      .catch(() => {
        if (cancelled) return;
        clearToken();
        setIdentity(null);
        setStatus("anonymous");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const signIn = useCallback(async (email: string) => {
    setError(null);
    try {
      const token = await apiClient.devLogin(email);
      storeToken(token.access_token);
      setIdentity(await apiClient.me());
      setStatus("authenticated");
    } catch (cause) {
      clearToken();
      setStatus("anonymous");
      setError(
        cause instanceof ApiError
          ? cause.message
          : "Could not reach the API. Is it running?",
      );
      throw cause;
    }
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    setIdentity(null);
    setError(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      status,
      identity,
      error,
      signIn,
      signOut,
      hasPermission: (permission: string) =>
        identity?.permissions.includes(permission) ?? false,
    }),
    [status, identity, error, signIn, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used inside an AuthProvider");
  }
  return context;
}
