export interface PrItem {
  repo: string;
  number: number;
  title: string;
  url: string;
  tier: 0 | 1 | 2;
  checks: "green" | "red" | "pending";
  isAgent: boolean;
  draft: boolean;
  updated_at: string;
}

export interface InboxEntry extends PrItem {
  action: "review" | "fix-or-close" | "wait" | "none";
  why: string;
}

/**
 * What needs the owner. Tier 0 green PRs merge themselves (nothing to do), red ones need a look,
 * tier 2 always waits for the owner (protected paths), tier 1 is the normal review queue.
 */
export function triage(p: PrItem): InboxEntry {
  if (p.draft) return { ...p, action: "none", why: "draft" };
  if (p.checks === "pending") return { ...p, action: "wait", why: "checks running" };
  if (p.checks === "red") return { ...p, action: "fix-or-close", why: "checks failing" };
  if (p.tier === 0) return { ...p, action: "none", why: "auto-merge eligible" };
  if (p.tier === 2) return { ...p, action: "review", why: "touches protected paths" };
  return { ...p, action: "review", why: p.isAgent ? "agent PR, ready for review" : "ready for review" };
}

const ORDER = { review: 0, "fix-or-close": 1, wait: 2, none: 3 } as const;

/** Protected-path PRs first within review, then oldest first so nothing rots. */
export function inbox(items: PrItem[]): InboxEntry[] {
  return items
    .map(triage)
    .filter((e) => e.action !== "none")
    .sort(
      (a, b) =>
        ORDER[a.action] - ORDER[b.action] ||
        (a.action === "review" ? b.tier - a.tier : 0) ||
        a.updated_at.localeCompare(b.updated_at),
    );
}
