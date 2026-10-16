import state from "../data/state.json";
import { ranked, share, status, type State } from "../lib/portfolio";

export const dynamic = "force-dynamic";

export default function Portfolio() {
  const s = state as State;
  const now = new Date();
  const repos = ranked(s.repos, now);
  return (
    <main>
      <h1>Portfolio</h1>
      <div className="sub">
        {s.owner} · {s.global_runs_per_day} runs/day pool · snapshot {s.generated_at.slice(0, 16).replace("T", " ")}Z · read-only
      </div>
      {repos.map((r) => {
        const st = status(r, now);
        const pct = share(r, s.repos, now);
        return (
          <div className="card" key={r.name}>
            <div className="row">
              <span className="name">{r.name}</span>
              <span className={`pill ${st}`}>{st}</span>
            </div>
            <div className="meta">
              tier {r.tier} · {r.mode} · priority {r.priority}
              {r.public ? " · public" : ""}
              {r.hold_until ? ` · held until ${r.hold_until.slice(0, 16).replace("T", " ")}Z` : ""}
            </div>
            <div className="bar" aria-label={`${pct}% of pool`}>
              <i style={{ width: `${pct}%` }} />
            </div>
          </div>
        );
      })}
    </main>
  );
}
