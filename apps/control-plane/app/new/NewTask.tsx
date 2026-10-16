"use client";
import { useState } from "react";

export default function NewTask({ repos }: { repos: string[] }) {
  const [repo, setRepo] = useState(repos[0] ?? "");
  const [goal, setGoal] = useState("");
  const [acc, setAcc] = useState("");
  const [busy, setBusy] = useState(false);
  const [out, setOut] = useState<{ kind: "ok" | "err"; lines: string[]; url?: string } | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setOut(null);
    try {
      const res = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, goal, acceptance: acc.split("\n").map((l) => l.trim()).filter(Boolean) }),
      });
      const j = await res.json().catch(() => ({}));
      if (res.ok && j.created) {
        setOut({ kind: "ok", lines: [`Queued as issue #${j.number}.${j.paused ? " Note: this project is paused." : ""} It runs at the next scheduled dispatch.`], url: j.url });
        setGoal("");
        setAcc("");
      } else setOut({ kind: "err", lines: j.problems ?? [`failed (${res.status})`] });
    } catch {
      setOut({ kind: "err", lines: ["network error"] });
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="card" style={{ display: "grid", gap: 10 }}>
      <label>Project
        <select value={repo} onChange={(e) => setRepo(e.target.value)} style={{ width: "100%" }}>
          {repos.map((r) => <option key={r}>{r}</option>)}
        </select>
      </label>
      <label>Goal (what is true when this is done?)
        <textarea value={goal} onChange={(e) => setGoal(e.target.value)} rows={3} style={{ width: "100%" }} required />
      </label>
      <label>Acceptance commands, one per line (must exit 0 when done)
        <textarea value={acc} onChange={(e) => setAcc(e.target.value)} rows={3} placeholder="npm test" style={{ width: "100%", fontFamily: "ui-monospace, monospace" }} required />
      </label>
      <button disabled={busy || !repo} className="btn on">{busy ? "Checking…" : "Queue task"}</button>
      {out && (
        <div className={`flash ${out.kind}`} role="status">
          {out.lines.map((l) => <div key={l}>{l}</div>)}
          {out.url && <a href={out.url}>Open issue</a>}
        </div>
      )}
    </form>
  );
}
