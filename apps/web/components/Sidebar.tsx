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
      className="flex h-full w-64 shrink-0 flex-col border-r border-gray-200 bg-gray-50 p-4"
    >
      <div className="mb-4 px-2 text-lg font-semibold text-gray-900">
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
                    ? "bg-gray-200 font-medium text-gray-900"
                    : "text-gray-600 hover:bg-gray-100 hover:text-gray-900"
                }`}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>

      {identity ? (
        <div className="mt-4 border-t border-gray-200 pt-4">
          <p className="px-3 text-xs text-gray-500" data-testid="signed-in-as">
            {identity.user.email}
          </p>
          <p className="px-3 text-xs text-gray-400">
            {identity.roles.length > 0
              ? identity.roles.join(", ").replaceAll("_", " ")
              : "no roles assigned"}
          </p>
          <button
            type="button"
            onClick={signOut}
            className="mt-2 w-full rounded-md px-3 py-2 text-left text-sm text-gray-600 hover:bg-gray-100 hover:text-gray-900"
          >
            Sign out
          </button>
        </div>
      ) : null}
    </nav>
  );
}
