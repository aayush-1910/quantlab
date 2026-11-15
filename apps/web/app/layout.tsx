import type { Metadata } from "next";
import type { ReactNode } from "react";

import { PrimaryNav } from "@/components/nav";

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
              <p className="text-accent font-mono text-[16px] font-semibold tracking-widest">
                QUANTLAB
              </p>
              <p className="text-muted mt-1 text-xs">Research use only</p>
            </div>
            <PrimaryNav />
          </aside>
          <main className="min-w-0 flex-1 px-4 py-6 md:px-8">{children}</main>
        </div>
      </body>
    </html>
  );
}
