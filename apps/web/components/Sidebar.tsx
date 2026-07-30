"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS } from "@/lib/nav";

export function Sidebar() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="flex h-full w-64 flex-col gap-1 border-r border-gray-200 bg-gray-50 p-4"
    >
      <div className="mb-4 px-2 text-lg font-semibold text-gray-900">
        QE Copilot
      </div>
      <ul className="flex flex-col gap-1">
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
    </nav>
  );
}
