import { createPublicKey, createVerify, generateKeyPairSync } from "node:crypto";
import { describe, expect, it, vi } from "vitest";
import { appJwt, installationToken, setRepoVariable } from "./githubApp";

const { privateKey, publicKey } = generateKeyPairSync("rsa", {
  modulusLength: 2048,
  privateKeyEncoding: { type: "pkcs8", format: "pem" },
  publicKeyEncoding: { type: "spki", format: "pem" },
});

describe("appJwt", () => {
  it("is a valid RS256 JWT with a short life and the app id as issuer", () => {
    const t = appJwt("123", privateKey, 1000);
    const [h, b, s] = t.split(".");
    expect(JSON.parse(Buffer.from(h, "base64url").toString())).toEqual({ alg: "RS256", typ: "JWT" });
    const body = JSON.parse(Buffer.from(b, "base64url").toString());
    expect(body).toEqual({ iat: 970, exp: 1540, iss: "123" });
    expect(body.exp - body.iat).toBeLessThanOrEqual(600);
    expect(createVerify("RSA-SHA256").update(`${h}.${b}`).verify(createPublicKey(publicKey), Buffer.from(s, "base64url"))).toBe(true);
  });
});

describe("installationToken", () => {
  it("scopes the token to one repo and the listed permissions", async () => {
    const f = vi.fn(async () => new Response(JSON.stringify({ token: "ghs_x" }), { status: 201 }));
    expect(await installationToken("jwt", 9, "me/stencil", { actions_variables: "write" }, f as any)).toBe("ghs_x");
    const [url, init] = f.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain("/app/installations/9/access_tokens");
    expect(JSON.parse(init.body as string)).toEqual({ repositories: ["stencil"], permissions: { actions_variables: "write" } });
  });
  it("throws on failure", async () => {
    await expect(installationToken("j", 1, "a/b", {}, (async () => new Response("", { status: 403 })) as any)).rejects.toThrow();
  });
});

describe("setRepoVariable", () => {
  it("updates, falls back to create on 404", async () => {
    const calls: string[] = [];
    const f = (async (u: string, i: RequestInit) => {
      calls.push(`${i.method} ${u.split("/actions/")[1]}`);
      return new Response("", { status: i.method === "PATCH" ? 404 : 201 });
    }) as any;
    await setRepoVariable("t", "me/r", "AUTOPILOT_PAUSED", "true", f);
    expect(calls).toEqual(["PATCH variables/AUTOPILOT_PAUSED", "POST variables"]);
  });
  it("refuses anything outside the AUTOPILOT_ namespace", async () => {
    for (const n of ["SECRET_KEY", "autopilot_x", "AUTOPILOT_x", "AUTOPILOT_/../x"]) {
      await expect(setRepoVariable("t", "me/r", n, "v", vi.fn() as any)).rejects.toThrow();
    }
  });
});
