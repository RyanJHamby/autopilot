import { describe, expect, it } from "vitest";
import { sameOriginJson } from "./origin";

const r = (h: Record<string, string>) => new Request("https://app.example/api/levers", { method: "POST", headers: h });

describe("sameOriginJson", () => {
  it("accepts JSON from our own origin only", () => {
    expect(sameOriginJson(r({ "content-type": "application/json", origin: "https://app.example" }))).toBe(true);
    expect(sameOriginJson(r({ "content-type": "application/json", origin: "https://evil.example" }))).toBe(false);
    expect(sameOriginJson(r({ "content-type": "application/json" }))).toBe(false);
    expect(sameOriginJson(r({ "content-type": "text/plain", origin: "https://app.example" }))).toBe(false);
  });
});
