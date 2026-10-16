import { describe, expect, it } from "vitest";
import { ranked, share, status, type Repo } from "./portfolio";

const now = new Date("2026-10-16T15:00:00Z");
const base: Repo = { name: "a", tier: "A", mode: "standard", enabled: true, priority: 8, hold_until: null, public: false };

describe("status", () => {
  it("a future hold beats enabled", () => {
    expect(status({ ...base, hold_until: "2026-10-16T21:00:00Z" }, now)).toBe("held");
  });
  it("an expired hold no longer applies", () => {
    expect(status({ ...base, hold_until: "2026-10-16T10:00:00Z" }, now)).toBe("active");
  });
  it("a paused project shows paused, ranked after active", () => {
    expect(status({ ...base, paused: true }, now)).toBe("paused");
    expect(ranked([{ ...base, name: "p", paused: true }, { ...base, name: "a" }], now).map((r) => r.name)).toEqual(["a", "p"]);
  });
  it("dormant and off", () => {
    expect(status({ ...base, mode: "dormant" }, now)).toBe("dormant");
    expect(status({ ...base, enabled: false }, now)).toBe("paused-off");
  });
});

describe("ranked and share", () => {
  const repos: Repo[] = [
    { ...base, name: "low", priority: 2 },
    { ...base, name: "off", enabled: false },
    { ...base, name: "top", priority: 8 },
    { ...base, name: "held", hold_until: "2026-10-16T21:00:00Z" },
  ];
  it("orders active by priority, then held, then off", () => {
    expect(ranked(repos, now).map((r) => r.name)).toEqual(["top", "low", "held", "off"]);
  });
  it("shares sum to ~100 over active repos only", () => {
    expect(share(repos[2], repos, now)).toBe(80);
    expect(share(repos[0], repos, now)).toBe(20);
    expect(share(repos[1], repos, now)).toBe(0);
  });
});
