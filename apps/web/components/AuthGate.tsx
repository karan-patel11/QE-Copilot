"use client";

// Wraps every page: renders the app shell only for an authenticated caller, and
// sends everyone else to /login. The login route renders outside the gate.

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { Sidebar } from "@/components/Sidebar";
import { useAuth } from "@/lib/auth";

const PUBLIC_ROUTES = new Set(["/login"]);

export function AuthGate({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isPublic = PUBLIC_ROUTES.has(pathname);

  useEffect(() => {
    if (status === "anonymous" && !isPublic) {
      router.replace("/login");
    }
    if (status === "authenticated" && isPublic) {
      router.replace("/");
    }
  }, [status, isPublic, router]);

  if (isPublic) {
    return <main className="flex min-h-screen items-center justify-center p-8">{children}</main>;
  }

  if (status !== "authenticated") {
    return (
      <main
        className="flex min-h-screen items-center justify-center p-8"
        aria-busy="true"
      >
        <p className="text-sm text-gray-500">
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
