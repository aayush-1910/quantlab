/**
 * Primary navigation (spec section 12.2). Only sections that exist are linkable.
 * "Execution" is intentionally absent: it stays hidden until the separately
 * approved live-execution milestone (spec sections 9 and 13, Phase 9).
 */

export type NavItem = {
  label: string;
  /** Present only when the screen is implemented. */
  href?: string;
  /** Development phase that delivers the screen. */
  phase: number;
};

export const NAV_ITEMS: readonly NavItem[] = [
  { label: "Overview", href: "/", phase: 0 },
  { label: "Markets", href: "/markets", phase: 2 },
  { label: "Stock Screener", href: "/screener", phase: 2 },
  { label: "Strategy Lab", phase: 3 },
  { label: "ML Research", phase: 5 },
  { label: "Portfolio Lab", phase: 6 },
  { label: "Risk Analytics", phase: 6 },
  { label: "AI Researcher", phase: 7 },
  { label: "Paper Trading", phase: 8 },
  { label: "Experiment History", phase: 4 },
  { label: "Settings and Data Sources", phase: 1 },
];

/** True when `pathname` is the item's screen or a page beneath it. */
export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
