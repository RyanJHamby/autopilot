import { describe, expect, it } from "vitest";
import { inbox, triage, type PrItem } from "./inbox";
import { allowedUser, readSession, signSession } from "./auth";

const pr = (o: Partial<PrItem> = {}): PrItem => ({
  repo: "me/a", number: 1, title: "t", url: "u", tier: 1, checks: "green", isAgent: true, draft: false, updated_at: "2026-10-16T10:00:00Z", ...o,
});

describe("inbox", () => {
  it("green tier 0 needs nothing; drafts are hidden", () => {
    expect(inbox([pr({ tier: 0 }), pr({ draft: true })])).toEqual([]);
  });
  it("protected-path PRs lead, then normal review, then failures, then waiting", () => {
    const out = inbox([
      pr({ number: 1, checks: "pending" }),
      pr({ number: 2, checks: "red" }),
      pr({ number: 3, tier: 1 }),
      pr({ number: 4, tier: 2 }),
    ]);
    expect(out.map((e) => e.number)).toEqual([4, 3, 2, 1]);
  });
  it("oldest first within the same bucket", () => {
    const out = inbox([pr({ number: 1, updated_at: "2026-10-16T12:00:00Z" }), pr({ number: 2, updated_at: "2026-10-15T12:00:00Z" })]);
    expect(out.map((e) => e.number)).toEqual([2, 1]);
  });
  it("red tier 0 still needs a look", () => {
    expect(triage(pr({ tier: 0, checks: "red" })).action).toBe("fix-or-close");
  });
});

describe("auth", () => {
  const secret = "x".repeat(40);
  it("allowlist is by numeric id and empty means nobody", () => {
    expect(allowedUser(68158512, "68158512")).toBe(true);
    expect(allowedUser(1, "68158512, 7")).toBe(false);
    expect(allowedUser(1, "")).toBe(false);
    expect(allowedUser(1, undefined)).toBe(false);
  });
  it("sessions round-trip, expire and resist tampering", () => {
    const t = signSession(secret, { uid: "68158512", exp: 2000 });
    expect(readSession(secret, t, 1000)?.uid).toBe("68158512");
    expect(readSession(secret, t, 3000)).toBeNull();
    expect(readSession("y".repeat(40), t, 1000)).toBeNull();
    const [b, m] = t.split(".");
    const forged = Buffer.from(JSON.stringify({ uid: "1", exp: 9e9 })).toString("base64url") + "." + m;
    expect(readSession(secret, forged, 1000)).toBeNull();
    expect(readSession(secret, b, 1000)).toBeNull();
    expect(readSession(secret, undefined, 1000)).toBeNull();
  });
  it("refuses a weak secret", () => {
    expect(() => signSession("short", { uid: "1", exp: 1 })).toThrow();
  });
});
