"use client";

import { useState } from "react";

import { useAuth } from "@/lib/auth";

// Dev-mode sign-in (ADR-0101). In a deployment with an external OIDC issuer this
// page is replaced by a redirect to the provider; everything behind it is
// unchanged, because the app only ever sees the resulting access token.
export default function LoginPage() {
  const { signIn, error } = useAuth();
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    try {
      await signIn(email.trim());
    } catch {
      // The message is surfaced from the auth context below.
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="w-full max-w-sm">
      <h1 className="text-2xl font-semibold text-ink">QE Copilot</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Sign in to continue. This environment uses the development identity
        provider.
      </p>

      <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-3">
        <label htmlFor="email" className="text-sm font-medium text-ink-secondary">
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@example.com"
          className="rounded-md border border-rule-strong px-3 py-2 text-sm text-ink focus:border-ink focus:outline-none"
        />
        <button
          type="submit"
          disabled={submitting || email.trim() === ""}
          className="rounded-md bg-surface-inverse px-3 py-2 text-sm font-medium text-ink-inverse disabled:cursor-not-allowed disabled:bg-surface-disabled"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      {error ? (
        <p role="alert" className="mt-4 text-sm text-status-failure-ink">
          {error}
        </p>
      ) : null}
    </section>
  );
}
