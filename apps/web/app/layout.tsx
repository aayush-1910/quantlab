import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { NAV_ITEMS } from "@/lib/navigation";

import "./globals.css";

export const metadata: Metadata = {
  title: "QUANTLAB",
  description: "Quantitative research platform for Indian equities. Research use only.",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen font-sans text-sm antialiased">
        <div className="flex min-h-screen flex-col md:flex-row">
          <aside className="border-line bg-panel border-b md:w-60 md:shrink-0 md:border-r md:border-b-0">
            <div className="border-line border-b px-4 py-4">
              <p className="text-accent font-mono text-base font-semibold tracking-widest">
                QUANTLAB
              </p>
              <p className="text-muted mt-1 text-xs">Research use only</p>
            </div>
            <nav aria-label="Primary" className="px-2 py-3">
              <ul className="space-y-0.5">
                {NAV_ITEMS.map((item) => (
                  <li key={item.label}>
                    {item.href ? (
                      <Link
                        href={item.href}
                        className="bg-base text-ink block rounded px-2 py-1.5"
                        aria-current="page"
                      >
                        {item.label}
                      </Link>
                    ) : (
                      <span
                        className="text-muted flex items-center justify-between rounded px-2 py-1.5"
                        aria-disabled="true"
                      >
                        <span>{item.label}</span>
                        <span className="font-mono text-[10px]">Phase {item.phase}</span>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </nav>
          </aside>
          <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
