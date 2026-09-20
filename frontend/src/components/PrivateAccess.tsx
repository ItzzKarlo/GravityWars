import Link from "next/link";

export default function PrivateAccess({
  title = "Private game",
  message = "Gravity Wars is friends-only. You’ll need a current invitation from the host to enter.",
  showLogin = true,
}: {
  title?: string;
  message?: string;
  showLogin?: boolean;
}) {
  return (
    <main className="private-page">
      <Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link>
      <section className="private-panel">
        <div className="access-x" aria-hidden="true"><i /><i /></div>
        <span className="eyebrow">Access closed</span>
        <h1>{title}</h1>
        <p>{message}</p>
        {showLogin && <Link className="button button-secondary" href="/login">Administrator sign in</Link>}
      </section>
    </main>
  );
}
