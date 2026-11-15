"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { NAV_ITEMS, isActive } from "@/lib/navigation";

export function PrimaryNav() {
  const pathname = usePathname();
  return (
    <nav aria-label="Primary" className="px-2 py-3">
      <ul className="space-y-0.5">
        {NAV_ITEMS.map((item) => {
          if (!item.href) {
            return (
              <li key={item.label}>
                <span
                  className="text-muted flex items-center justify-between rounded px-2 py-1.5"
                  aria-disabled="true"
                >
                  <span>{item.label}</span>
                  <span className="font-mono text-[10px]">Phase {item.phase}</span>
                </span>
              </li>
            );
          }
          const active = isActive(item.href, pathname);
          return (
            <li key={item.label}>
              <Link
                href={item.href}
                aria-current={active ? "page" : undefined}
                className={`block rounded px-2 py-1.5 ${
                  active ? "bg-base text-ink" : "text-muted hover:text-ink"
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
