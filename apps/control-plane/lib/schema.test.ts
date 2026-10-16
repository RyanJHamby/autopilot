import { readFileSync } from "node:fs";
import { PGlite } from "@electric-sql/pglite";
import { beforeAll, describe, expect, it } from "vitest";

const OWNER = "00000000-0000-0000-0000-000000000001";
const CONTRIB = "00000000-0000-0000-0000-000000000002";
const OUTSIDER = "00000000-0000-0000-0000-000000000003";
let db: PGlite;
let proj: string;

async function as(uid: string) {
  await db.exec(`set role authenticated; select set_config('app.uid', '${uid}', false);`);
}
async function admin() {
  await db.exec("reset role");
}

beforeAll(async () => {
  db = new PGlite();
  // Minimal stand-in for Supabase's auth.uid() and role
  await db.exec(`
    create schema auth;
    create function auth.uid() returns uuid language sql stable as $$ select nullif(current_setting('app.uid', true), '')::uuid $$;
    create role authenticated;
  `);
  await db.exec(readFileSync(new URL("../supabase/migrations/0001_core.sql", import.meta.url), "utf8"));
  await db.exec(`grant usage on schema public to authenticated;
    grant select, insert, update, delete on all tables in schema public to authenticated;`);
  const org = (await db.query<{ id: string }>(`insert into orgs(name, owner_id) values ('me', '${OWNER}') returning id`)).rows[0].id;
  await db.exec(`insert into members values ('${org}', '${OWNER}', 'owner'), ('${org}', '${CONTRIB}', 'contributor')`);
  proj = (await db.query<{ id: string }>(`insert into projects(org_id, repo, tier, enabled) values ('${org}', 'me/stencil', 'A', true) returning id`)).rows[0].id;
});

describe("RLS", () => {
  it("outsiders see nothing", async () => {
    await as(OUTSIDER);
    expect((await db.query("select * from projects")).rows).toHaveLength(0);
    await admin();
  });

  it("a contributor without a grant sees no project; with view they do, but cannot change levers", async () => {
    await as(CONTRIB);
    expect((await db.query("select * from projects")).rows).toHaveLength(0);
    await admin();
    await db.exec(`insert into grants values ('${proj}', '${CONTRIB}', 'view')`);
    await as(CONTRIB);
    expect((await db.query("select * from projects")).rows).toHaveLength(1);
    const r = await db.query(`update projects set priority = 9 where id = '${proj}' returning id`);
    expect(r.rows).toHaveLength(0);
    await admin();
  });

  it("change_levers lets a contributor tune levers within bounds only", async () => {
    await db.exec(`insert into grants values ('${proj}', '${CONTRIB}', 'change_levers')`);
    await as(CONTRIB);
    expect((await db.query(`update projects set priority = 7, greediness = 2 where id = '${proj}' returning id`)).rows).toHaveLength(1);
    await expect(db.query(`update projects set greediness = 9 where id = '${proj}'`)).rejects.toThrow();
    await admin();
  });

  it("contributors cannot grant themselves access", async () => {
    await as(CONTRIB);
    await expect(db.query(`insert into grants values ('${proj}', '${CONTRIB}', 'manage_access')`)).rejects.toThrow();
    await admin();
  });

  it("only the owner reads the audit log, and nobody can edit it", async () => {
    await db.exec(`insert into audit(org_id, actor, action) select org_id, '${OWNER}', 'lever.priority' from projects`);
    await as(CONTRIB);
    expect((await db.query("select * from audit")).rows).toHaveLength(0);
    await as(OWNER);
    expect((await db.query("select * from audit")).rows).toHaveLength(1);
    expect((await db.query("update audit set action = 'x' returning id")).rows).toHaveLength(0);
    expect((await db.query("delete from audit returning id")).rows).toHaveLength(0);
    await admin();
  });
});

describe("schema invariants", () => {
  it("has no column that can loosen a guardrail", async () => {
    const cols = (await db.query<{ column_name: string }>(`select column_name from information_schema.columns where table_schema='public'`)).rows.map((r) => r.column_name);
    for (const bad of ["auto_merge_classes", "protected_paths", "comms", "protected_extra"]) expect(cols).not.toContain(bad);
  });
});
