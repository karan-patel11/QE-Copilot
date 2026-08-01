"use client";

// Wraps every page: renders the app shell only for an authenticated caller, and
// sends everyone else to /login. The login route renders outside the gate.

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/lib/auth";

const PUBLIC_ROUTES = new Set(["/login"]);

// The design-token preview under /dev renders outside the session gate: it shows
// design primitives and no tenant data, and it does not exist in a production
// build — the route itself calls notFound() there. Double-gated deliberately, so
// neither guard alone is load-bearing.
const DEV_PREFIX = "/dev/";

function isDevPreview(pathname: string): boolean {
  return process.env.NODE_ENV !== "production" && pathname.startsWith(DEV_PREFIX);
}

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const devPreview = isDevPreview(pathname);
  const isPublic = PUBLIC_ROUTES.has(pathname) || devPreview;

  useEffect(() => {
    if (status === "anonymous" && !isPublic) {
      router.replace("/login");
    }
    // The dev preview is exempt from the bounce back to "/": it is reachable
    // whether or not a session exists, which is the point of it.
    if (status === "authenticated" && isPublic && !devPreview) {
      router.replace("/");
    }
  }, [status, isPublic, devPreview, router]);

  // Full width and top-aligned — the preview is a long scrolling page, not the
  // single centred card the login route wants.
  if (devPreview) {
    return <main className="min-h-screen p-10">{children}</main>;
  }

  if (isPublic) {
    return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
  }

  if (status !== "authenticated") {
    return (
      <main
        className="flex min-h-screen items-center justify-center p-8"
        aria-busy="true"
      >
        <p className="text-sm text-ink-subtle">
          {status === "loading" ? "Checking your session…" : "Redirecting to sign in…"}
        </p>
      </main>
    );
  }

  return (
    <div className="flex h-screen">
      <Sidebar />
      <main className="flex-1 overflow-auto p-8">{children}</main>
    </div>
  );
}
