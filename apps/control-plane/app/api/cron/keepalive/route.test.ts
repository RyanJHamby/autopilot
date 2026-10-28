import { describe, it, expect, vi, afterEach } from "vitest";
import { GET } from "./route";

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("keepalive cron", () => {
  it("returns 501 when the store is not configured", async () => {
    vi.stubEnv("SUPABASE_URL", "");
    expect((await GET()).status).toBe(501);
  });
  it("pings the store and leaks no data", async () => {
    vi.stubEnv("SUPABASE_URL", "http://db");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "k");
    const f = vi.fn(async () => new Response('[{"id":"secret-id"}]', { status: 200 }));
    vi.stubGlobal("fetch", f);
    const res = await GET();
    expect(res.status).toBe(200);
    expect(await res.text()).toBe("ok");
    expect(f).toHaveBeenCalledOnce();
  });
  it("reports 502 when the store is down", async () => {
    vi.stubEnv("SUPABASE_URL", "http://db");
    vi.stubEnv("SUPABASE_SERVICE_ROLE_KEY", "k");
    vi.stubGlobal("fetch", vi.fn(async () => new Response("", { status: 503 })));
    expect((await GET()).status).toBe(502);
  });
});
