"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { createLobby, getAccessSession, logout, saveCredentials } from "@/lib/api";
import type { AccessSessionState } from "@/lib/types";
import { ArrowIcon } from "@/components/Icons";
import PrivateAccess from "@/components/PrivateAccess";

const demoPieces = [
  [null, null, null, null, null, null, null],
  [null, null, null, null, null, null, null],
  [null, null, null, null, null, null, null],
  [null, null, null, null, null, null, null],
  [null, null, null, "yellow", null, null, null],
  [null, null, "green", "red", "blue", null, null],
  ["red", "blue", "yellow", "red", "green", "blue", null],
] as const;

export default function Home() {
  const router = useRouter();
  const [session, setSession] = useState<AccessSessionState | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    getAccessSession()
      .then((value) => { if (active) setSession(value); })
      .catch(() => { if (active) setSession({ authenticated: false, role: null }); });
    return () => { active = false; };
  }, []);

  const host = async () => {
    setCreating(true);
    setError(null);
    try {
      const response = await createLobby();
      saveCredentials(response);
      router.push(`/lobby/${response.lobby.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not host a game.");
      setCreating(false);
    }
  };

  if (!session) return <main className="centered-page"><div className="loading-mark"><span /><span /><span /><span /></div><p className="loading-copy">Checking access…</p></main>;
  if (!session.authenticated) return <PrivateAccess />;
  if (session.role === "guest") {
    return session.lobby_id ? <main className="private-page"><Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link><section className="private-panel authorized-panel"><span className="eyebrow">Invitation accepted</span><h1>Your game is waiting</h1><p>This browser is authorized for one private lobby.</p><Link className="button button-primary" href={`/lobby/${session.lobby_id}`}>Return to game <ArrowIcon /></Link></section></main> : <PrivateAccess showLogin={false} />;
  }

  return (
    <main className="home-page">
      <button className="admin-logout" type="button" onClick={async () => { await logout(); location.reload(); }}>Sign out</button>
      <section className="home-copy">
        <span className="admin-mark">ADMIN / HOST</span>
        <div className="title-lockup"><span className="title-gravity">GRAVITY</span><span className="title-wars">WARS</span><i /></div>
        <div className="home-actions"><button type="button" className="button button-primary button-large" onClick={host} disabled={creating}>{creating ? <><span className="spinner" /> Preparing table…</> : <>Host Game <ArrowIcon /></>}</button></div>
        {error && <p className="home-error" role="alert">{error}</p>}
      </section>
      <section className="home-board-scene" aria-label="A Gravity Wars board with colored pieces"><div className="orbit-arrow"><ArrowIcon direction="down" /></div><div className="demo-board">{demoPieces.flatMap((row, rowIndex) => row.map((piece, column) => <span className="demo-well" key={`${rowIndex}-${column}`}>{piece && <i className={`piece-${piece}`} />}</span>))}</div><div className="demo-shadow" /></section>
    </main>
  );
}
