"use client";
import { useState } from "react";

export default function Controls({ repo, priority }: { repo: string; priority: number }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);

  async function send(changes: Record<string, unknown>) {
    setBusy(true);
    setMsg("");
    try {
      const res = await fetch("/api/levers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, changes }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) setMsg(j.error ?? `failed (${res.status})`);
      else if (j.plan?.pr?.length) setMsg("guardrail change: needs a PR (not applied)");
      else if (j.plan?.rejected?.length) setMsg(`rejected: ${j.plan.rejected.map((r: any) => r.why).join("; ")}`);
      else setMsg(`applied ${j.applied.join(", ")}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="meta" style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
      <button disabled={busy} onClick={() => send({ paused: true })}>Pause</button>
      <button disabled={busy} onClick={() => send({ paused: false })}>Resume</button>
      <label>
        priority{" "}
        <select disabled={busy} defaultValue={priority} onChange={(e) => send({ priority: Number(e.target.value) })}>
          {Array.from({ length: 11 }, (_, i) => (
            <option key={i} value={i}>{i}</option>
          ))}
        </select>
      </label>
      {msg && <span>{msg}</span>}
    </div>
  );
}
