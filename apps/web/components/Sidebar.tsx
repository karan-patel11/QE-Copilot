"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { useAuth } from "@/lib/auth";
import { NAV_ITEMS } from "@/lib/nav";

export function Sidebar() {
  const pathname = usePathname();
  const { identity, signOut } = useAuth();

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-64 shrink-0 flex-col border-r border-rule bg-surface-raised p-4"
    >
      <div className="mb-4 px-2 text-lg font-semibold text-ink">
        QE Copilot
      </div>
      <ul className="flex flex-1 flex-col gap-1">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/"
              ? pathname === "/"
              : pathname.startsWith(item.href);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded-md px-3 py-2 text-sm ${
                  active
                    ? "bg-surface-active font-medium text-ink"
                    : "text-ink-muted hover:bg-surface-hover hover:text-ink"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>

      {identity ? (
        <div className="mt-4 border-t border-rule pt-4">
          <p className="px-3 text-xs text-ink-subtle" data-testid="signed-in-as">
            {identity.user.email}
          </p>
          <p className="px-3 text-xs text-ink-subtle">
            {identity.roles.length > 0
              ? identity.roles.join(", ").replaceAll("_", " ")
              : "no roles assigned"}
          </p>
          <button
            type="button"
            onClick={signOut}
            className="mt-2 w-full rounded-md px-3 py-2 text-left text-sm text-ink-muted hover:bg-surface-hover hover:text-ink"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </nav>
  );
}
