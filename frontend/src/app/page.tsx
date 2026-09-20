"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { createLobby, saveCredentials } from "@/lib/api";
import { ArrowIcon } from "@/components/Icons";

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
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      const response = await createLobby();
      saveCredentials(response);
      router.push(`/lobby/${response.lobby.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not create a lobby.");
      setCreating(false);
    }
  };

  return (
    <main className="home-page">
      <section className="home-copy">
        <div className="title-lockup"><span className="title-gravity">GRAVITY</span><span className="title-wars">WARS</span><i /></div>
        <div className="home-actions">
          <button type="button" className="button button-primary button-large" onClick={create} disabled={creating}>{creating ? <><span className="spinner" /> Creating…</> : <>Create Game <ArrowIcon /></>}</button>
          <Link className="button button-secondary button-large" href="/join">Join Game</Link>
        </div>
        {error && <p className="home-error" role="alert">{error}</p>}
      </section>

      <section className="home-board-scene" aria-label="A Gravity Wars board with colored pieces">
        <div className="orbit-arrow"><ArrowIcon direction="down" /></div>
        <div className="demo-board">
          {demoPieces.flatMap((row, rowIndex) => row.map((piece, column) => (
            <span className="demo-well" key={`${rowIndex}-${column}`}>{piece && <i className={`piece-${piece}`} />}</span>
          )))}
        </div>
        <div className="demo-shadow" />
      </section>
    </main>
  );
}
