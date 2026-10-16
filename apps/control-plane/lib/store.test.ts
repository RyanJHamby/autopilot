import { describe, expect, it } from "vitest";
import { fromRows } from "./store";

describe("fromRows", () => {
  it("maps database rows to the portfolio shape", () => {
    const s = fromRows(
      [{ repo: "me/stencil", tier: "A", mode: "standard", enabled: true, priority: 8, hold_until: "2026-10-16T21:00:00Z", is_public: false }],
      "me",
      new Date("2026-10-16T12:00:00Z"),
    );
    expect(s.repos[0]).toEqual({ name: "stencil", tier: "A", mode: "standard", enabled: true, priority: 8, hold_until: "2026-10-16T21:00:00Z", public: false });
    expect(s.owner).toBe("me");
  });
});
