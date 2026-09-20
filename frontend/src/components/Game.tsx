"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { AccessRole, ClientMessage, ConnectionState, JokerType, LobbyState, Position } from "@/lib/types";
import GameBoard from "./GameBoard";
import GravityIndicator from "./GravityIndicator";
import JokerHand, { getJokerInfo } from "./JokerHand";
import PlayerList from "./PlayerList";

interface GameProps {
  lobby: LobbyState;
  playerId: string;
  hand: JokerType[];
  connection: ConnectionState;
  serverError: { id: number; message: string } | null;
  send: (message: ClientMessage) => boolean;
  role: AccessRole;
  onLeave?: () => Promise<void>;
  onRevokePlayer?: (playerId: string) => Promise<void>;
}

export default function Game({ lobby, playerId, hand, connection, serverError, send, role, onLeave, onRevokePlayer }: GameProps) {
  const [selection, setSelection] = useState<{ joker: JokerType; targets: Position[] } | null>(null);
  const [pendingJoker, setPendingJoker] = useState<JokerType | null>(null);
  const [pendingDropState, setPendingDropState] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [dismissedError, setDismissedError] = useState(0);

  const localPlayer = lobby.players.find((player) => player.id === playerId);
  const currentPlayer = lobby.players[lobby.current_turn];
  const isMyTurn = currentPlayer?.id === playerId;
  const connected = connection === "open";
  const finished = lobby.status === "finished";
  const stateKey = `${lobby.current_turn}:${lobby.gravity}:${JSON.stringify(lobby.board)}`;

  const winners = useMemo(
    () => lobby.winner_ids.map((id) => lobby.players.find((player) => player.id === id)?.username).filter(Boolean) as string[],
    [lobby.players, lobby.winner_ids],
  );

  const sendAction = (message: ClientMessage) => {
    setLocalError(null);
    setPendingJoker(null);
    if (send(message)) return true;
    setLocalError("Still reconnecting. Your action was not sent.");
    return false;
  };

  const playJoker = (joker: JokerType) => {
    const info = getJokerInfo(joker);
    setLocalError(null);
    if (info.needsTarget) {
      setSelection({ joker, targets: [] });
      return;
    }
    if (sendAction({ type: "joker", joker })) setPendingJoker(joker);
  };

  const selectTarget = (position: Position) => {
    if (!selection) return;
    if (selection.joker === "steal") {
      if (sendAction({ type: "joker", joker: "steal", target: position })) setPendingJoker("steal");
      setSelection(null);
      return;
    }
    if (!selection.targets.length) {
      setSelection({ ...selection, targets: [position] });
      return;
    }
    if (sendAction({ type: "joker", joker: "swap", target: selection.targets[0], second_target: position })) setPendingJoker("swap");
    setSelection(null);
  };

  const drop = (lane: number) => {
    if (sendAction({ type: "drop", lane })) setPendingDropState(stateKey);
  };

  if (!localPlayer) return <div className="fatal-panel">Your player is no longer part of this lobby.</div>;

  return (
    <main className="game-shell">
      <header className="game-header">
        <Link className="mini-logo" href="/" aria-label="Gravity Wars home"><span>G</span> GRAVITY WARS</Link>
        <div className="game-header-center">
          <GravityIndicator direction={lobby.gravity} locked={lobby.gravity_locked} />
        </div>
        <div className="game-code"><span>{role === "admin" ? "Private host" : "Invited player"}</span>{onLeave ? <button type="button" className="game-leave" onClick={() => void onLeave()}>Leave</button> : <strong>ADMIN</strong>}</div>
      </header>

      {(connection === "reconnecting" || connection === "connecting") && (
        <div className="connection-banner"><span className="spinner" /> Reconnecting to the game…</div>
      )}

      <div className="turn-strip" aria-live="polite">
        <span className={`turn-dot color-${currentPlayer?.color ?? "red"}`} />
        <strong>{finished ? "Match over" : isMyTurn ? "Your turn" : `${currentPlayer?.username ?? "Player"}'s turn`}</strong>
        {!finished && <span>{isMyTurn ? "Choose an open lane" : "Jokers can still be played"}</span>}
      </div>

      {(localError || (serverError && serverError.id !== dismissedError)) && <div className="action-error" role="alert">{localError ?? serverError?.message}<button onClick={() => { setLocalError(null); if (serverError) setDismissedError(serverError.id); }} aria-label="Dismiss error">×</button></div>}

      <section className="game-stage">
        <PlayerList
          players={lobby.players.slice(0, 2)}
          currentTurn={lobby.current_turn}
          localPlayerId={playerId}
          finished={finished}
          className="players-left"
          onRevokePlayer={onRevokePlayer ? (id) => void onRevokePlayer(id) : undefined}
        />

        <div className="board-column">
          <GameBoard
            board={lobby.board}
            gravity={lobby.gravity}
            canDrop={isMyTurn && connected && !finished && !selection}
            pendingDrop={pendingDropState === stateKey && isMyTurn && !finished && !serverError}
            selection={selection}
            localColor={localPlayer.color}
            onDrop={drop}
            onSelect={selectTarget}
            onCancelSelection={() => setSelection(null)}
          />
          {finished && (
            <div className="result-panel" role="status">
              <span className="result-kicker">Final result</span>
              <h1>{winners.length ? (lobby.winner_ids.includes(playerId) ? "Victory!" : `${winners.join(" & ")} won`) : "Stalemate"}</h1>
              <p>{winners.length ? (lobby.winner_ids.includes(playerId) ? "Four aligned. Gravity conquered." : "The winning line survived the chaos.") : "Every space is full and gravity calls it even."}</p>
              <Link href="/" className="button button-primary">Back to home</Link>
            </div>
          )}
        </div>

        <PlayerList
          players={lobby.players.slice(2, 4)}
          currentTurn={lobby.current_turn - 2}
          localPlayerId={playerId}
          finished={finished}
          className="players-right"
          onRevokePlayer={onRevokePlayer ? (id) => void onRevokePlayer(id) : undefined}
        />
      </section>

      <div className="mobile-player-list">
        <PlayerList players={lobby.players} currentTurn={lobby.current_turn} localPlayerId={playerId} finished={finished} onRevokePlayer={onRevokePlayer ? (id) => void onRevokePlayer(id) : undefined} />
      </div>

      <JokerHand
        jokers={hand}
        selected={selection?.joker ?? null}
        pending={pendingJoker && hand.includes(pendingJoker) && !serverError ? pendingJoker : null}
        disabled={!connected || finished}
        onPlay={playJoker}
        onCancel={() => setSelection(null)}
      />
    </main>
  );
}
