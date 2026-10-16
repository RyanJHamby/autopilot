import { redirect } from "next/navigation";
import { currentSession } from "../../lib/session";
import { status } from "../../lib/portfolio";
import { loadState } from "../../lib/store";
import NewTask from "./NewTask";

export const dynamic = "force-dynamic";

export default async function New() {
  if (!(await currentSession())) redirect("/login");
  const s = await loadState();
  const now = new Date();
  const repos = s.repos.filter((r) => ["active", "paused"].includes(status(r, now))).map((r) => `${s.owner}/${r.name}`);
  return (
    <main>
      <h1>New task</h1>
      <div className="sub"><a href="/">← Portfolio</a> · queued tasks run at the next scheduled dispatch</div>
      <NewTask repos={repos} />
    </main>
  );
}
