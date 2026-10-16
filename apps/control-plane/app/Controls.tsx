"use client";
import { useState } from "react";

type Flash = { kind: "ok" | "err" | "info"; text: string } | null;

export default function Controls({ repo, priority, paused }: { repo: string; priority: number; paused: boolean }) {
  const [isPaused, setPaused] = useState(paused);
  const [prio, setPrio] = useState(priority);
  const [busy, setBusy] = useState<string | null>(null);
  const [flash, setFlash] = useState<Flash>(null);

  async function send(label: string, changes: Record<string, unknown>, onOk: () => void) {
    setBusy(label);
    setFlash(null);
    try {
      const res = await fetch("/api/levers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo, changes }),
      });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) setFlash({ kind: "err", text: j.error ?? `failed (${res.status})` });
      else if (j.plan?.pr?.length) setFlash({ kind: "info", text: "guardrail change: needs a PR, not applied" });
      else if (j.plan?.rejected?.length) setFlash({ kind: "err", text: j.plan.rejected.map((r: { why: string }) => r.why).join("; ") });
      else {
        onOk();
        setFlash({ kind: "ok", text: `saved ${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` });
      }
    } catch {
      setFlash({ kind: "err", text: "network error" });
    } finally {
      setBusy(null);
    }
  }

  const cls = (on: boolean) => `btn${on ? " on" : ""}`;
  return (
    <div className="controls">
      <button className={cls(isPaused)} aria-pressed={isPaused} disabled={!!busy} onClick={() => send("pause", { paused: true }, () => setPaused(true))}>
        {busy === "pause" ? "Pausing…" : "Pause"}
      </button>
      <button className={cls(!isPaused)} aria-pressed={!isPaused} disabled={!!busy} onClick={() => send("resume", { paused: false }, () => setPaused(false))}>
        {busy === "resume" ? "Resuming…" : "Resume"}
      </button>
      <label>
        priority{" "}
        <select disabled={!!busy} value={prio} onChange={(e) => { const v = Number(e.target.value); send("prio", { priority: v }, () => setPrio(v)); }}>
          {Array.from({ length: 11 }, (_, i) => (<option key={i} value={i}>{i}</option>))}
        </select>
      </label>
      {flash && <span className={`flash ${flash.kind}`} role="status">{flash.text}</span>}
    </div>
  );
}
