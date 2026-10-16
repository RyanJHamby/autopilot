export default function Login() {
  return (
    <main>
      <h1>Autopilot</h1>
      <div className="sub">Owner sign-in only.</div>
      <a className="card" href="/api/auth/login" style={{ display: "block", textDecoration: "none", color: "inherit" }}>
        <span className="name">Sign in with GitHub</span>
      </a>
    </main>
  );
}
