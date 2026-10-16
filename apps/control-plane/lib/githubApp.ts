import { createSign } from "node:crypto";

const b64u = (b: Buffer | string) => Buffer.from(b).toString("base64url");

/** App JWT (RS256, 9 minutes; GitHub allows at most 10). */
export function appJwt(appId: string, pem: string, now = Math.floor(Date.now() / 1000)): string {
  const head = b64u(JSON.stringify({ alg: "RS256", typ: "JWT" }));
  const body = b64u(JSON.stringify({ iat: now - 30, exp: now + 540, iss: appId }));
  const sig = createSign("RSA-SHA256").update(`${head}.${body}`).sign(pem);
  return `${head}.${body}.${b64u(sig)}`;
}

/** Repo-scoped installation token with only the permissions asked for, so a leaked token is as small as possible. */
export async function installationToken(
  jwt: string,
  installationId: number,
  repo: string,
  permissions: Record<string, "read" | "write">,
  f: typeof fetch = fetch,
): Promise<string> {
  const res = await f(`https://api.github.com/app/installations/${installationId}/access_tokens`, {
    method: "POST",
    headers: { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json", "User-Agent": "autopilot-control" },
    body: JSON.stringify({ repositories: [repo.split("/")[1]], permissions }),
  });
  if (!res.ok) throw new Error(`installation token failed: ${res.status}`);
  return ((await res.json()) as { token: string }).token;
}

/** Create-or-update a repository variable. Names are restricted to the AUTOPILOT_ namespace. */
export async function setRepoVariable(token: string, repo: string, name: string, value: string, f: typeof fetch = fetch) {
  if (!/^AUTOPILOT_[A-Z_]+$/.test(name)) throw new Error(`refusing to set non-autopilot variable: ${name}`);
  const h = { Authorization: `Bearer ${token}`, Accept: "application/vnd.github+json", "User-Agent": "autopilot-control" };
  const base = `https://api.github.com/repos/${repo}/actions/variables`;
  const upd = await f(`${base}/${name}`, { method: "PATCH", headers: h, body: JSON.stringify({ name, value }) });
  if (upd.status === 404) {
    const crt = await f(base, { method: "POST", headers: h, body: JSON.stringify({ name, value }) });
    if (!crt.ok) throw new Error(`create variable failed: ${crt.status}`);
  } else if (!upd.ok) throw new Error(`update variable failed: ${upd.status}`);
}

/** Installation id for one repo (app-level call). 404 means the app is not installed there. */
export async function repoInstallationId(jwt: string, repo: string, f: typeof fetch = fetch): Promise<number> {
  const res = await f(`https://api.github.com/repos/${repo}/installation`, {
    headers: { Authorization: `Bearer ${jwt}`, Accept: "application/vnd.github+json", "User-Agent": "autopilot-control" },
  });
  if (!res.ok) throw new Error(`app is not installed on ${repo} (${res.status})`);
  return ((await res.json()) as { id: number }).id;
}
