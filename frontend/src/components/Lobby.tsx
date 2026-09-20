"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import { QRCodeSVG } from "qrcode.react";
import { joinLobby, loadCredentials, removeCredentials, saveCredentials } from "@/lib/api";
import { LobbySocket } from "@/lib/websocket";
import type { ClientMessage, ConnectionState, JokerType, LobbyCredentials, LobbyState, PlayerColor, ServerMessage } from "@/lib/types";
import { CheckIcon, CopyIcon, EditIcon } from "./Icons";
import Game from "./Game";

const slotColors: PlayerColor[] = ["red", "blue", "green", "yellow"];

export default function Lobby({ code }: { code: string }) {
  const [credentials, setCredentials] = useState<LobbyCredentials | null>(null);
  const [lobby, setLobby] = useState<LobbyState | null>(null);
  const [hand, setHand] = useState<JokerType[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<{ id: number; message: string } | null>(null);
  const socketRef = useRef<LobbySocket | null>(null);
  const errorId = useRef(0);

  useEffect(() => {
    let active = true;
    const existing = loadCredentials(code);
    if (existing) {
      const timer = window.setTimeout(() => { if (active) setCredentials(existing); }, 0);
      return () => { active = false; window.clearTimeout(timer); };
    }
    joinLobby(code)
      .then((response) => {
        if (!active) return;
        const saved = saveCredentials(response);
        setLobby(response.lobby);
        setCredentials(saved);
      })
      .catch((error: unknown) => {
        if (active) setFatalError(error instanceof Error ? error.message : "Could not join this lobby.");
      });
    return () => { active = false; };
  }, [code]);

  useEffect(() => {
    if (!credentials) return;
    const handleMessage = (message: ServerMessage) => {
      if (message.type === "state") {
        setLobby(message.lobby);
        setServerError(null);
      }
      if (message.type === "welcome") {
        setHand(message.jokers);
      }
      if (message.type === "hand") {
        setHand(message.jokers);
      }
      if (message.type === "error") setServerError({ id: ++errorId.current, message: message.message });
    };
    const socket = new LobbySocket({
      lobbyId: credentials.lobbyId,
      token: credentials.token,
      onMessage: handleMessage,
      onState: setConnection,
      onAuthFailure: () => {
        removeCredentials(credentials.lobbyId);
        setFatalError("This player session is no longer valid. Open a fresh invitation to join again.");
      },
    });
    socketRef.current = socket;
    socket.connect();
    return () => {
      socket.stop();
      if (socketRef.current === socket) socketRef.current = null;
    };
  }, [credentials]);

  const send = useCallback((message: ClientMessage) => {
    setServerError(null);
    return socketRef.current?.send(message) ?? false;
  }, []);

  if (fatalError) {
    return (
      <main className="centered-page">
        <Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link>
        <div className="fatal-panel"><span className="eyebrow">Couldn’t enter lobby</span><h1>Game out of reach</h1><p>{fatalError}</p><Link href="/" className="button button-primary">Back to home</Link></div>
      </main>
    );
  }

  if (!lobby || !credentials) {
    return <main className="centered-page"><div className="loading-mark"><span /><span /><span /><span /></div><p className="loading-copy">Joining the table…</p></main>;
  }

  if (lobby.status !== "waiting") {
    return <Game lobby={lobby} playerId={credentials.playerId} hand={hand} connection={connection} serverError={serverError} send={send} />;
  }

  return <WaitingRoom lobby={lobby} playerId={credentials.playerId} connection={connection} serverError={serverError} send={send} />;
}

function WaitingRoom({ lobby, playerId, connection, serverError, send }: { lobby: LobbyState; playerId: string; connection: ConnectionState; serverError: { id: number; message: string } | null; send: (message: ClientMessage) => boolean }) {
  const player = lobby.players.find((item) => item.id === playerId);
  const [username, setUsername] = useState(player?.username ?? "");
  const [editing, setEditing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const [inviteUrl, setInviteUrl] = useState("");
  const isHost = playerId === lobby.host_player_id;
  const full = lobby.players.length === 4;

  useEffect(() => {
    const timer = window.setTimeout(() => setInviteUrl(`${window.location.origin}/lobby/${lobby.id}`), 0);
    return () => window.clearTimeout(timer);
  }, [lobby.id]);

  const copyInvite = async () => {
    try {
      await navigator.clipboard.writeText(inviteUrl);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setLocalError("Could not copy the link. Select it manually instead.");
    }
  };

  const rename = (event: FormEvent) => {
    event.preventDefault();
    if (!send({ type: "rename", username })) return setLocalError("Still reconnecting. Try again in a moment.");
    setEditing(false);
  };

  const start = () => {
    setLocalError(null);
    if (!send({ type: "start" })) setLocalError("Still reconnecting. Try again in a moment.");
  };

  return (
    <main className="lobby-page">
      <header className="lobby-header">
        <Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link>
        <ConnectionPill connection={connection} />
      </header>

      <div className="lobby-layout">
        <section className="lobby-table">
          <div className="lobby-title-row"><div><span className="eyebrow">Waiting room</span><h1>Assemble your crew</h1></div><div className="seat-count">{lobby.players.length}<span>/ 4</span></div></div>
          <div className="lobby-slots">
            {slotColors.map((color, index) => {
              const occupant = lobby.players[index];
              return (
                <div className={`lobby-slot slot-${color}${occupant ? " occupied" : ""}`} key={color}>
                  <span className="slot-piece" />
                  {occupant ? (
                    <div><strong>{occupant.username}{occupant.id === playerId && <span className="you-label">You</span>}</strong><span className="slot-status"><i className={occupant.connected ? "online" : ""} />{occupant.connected ? "Ready at the table" : "Disconnected"}</span></div>
                  ) : (
                    <div><strong>Open seat</strong><span className="slot-status">Waiting for a player</span></div>
                  )}
                  {occupant?.id === lobby.host_player_id && <span className="host-mark">Host</span>}
                </div>
              );
            })}
          </div>

          <div className="identity-row">
            {editing ? (
              <form onSubmit={rename} className="rename-form">
                <label htmlFor="username">Your name</label><div><input id="username" value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={24} autoFocus /><button type="submit" className="button button-small">Save</button><button type="button" className="text-button" onClick={() => setEditing(false)}>Cancel</button></div>
              </form>
            ) : (
              <div className="current-identity"><span>Playing as</span><strong>{player?.username}</strong><button type="button" onClick={() => setEditing(true)}><EditIcon /> Change</button></div>
            )}
          </div>

          {(localError || serverError) && <div className="inline-error" role="alert">{localError ?? serverError?.message}</div>}

          {isHost ? (
            <button className="button button-primary start-button" type="button" disabled={!full || connection !== "open"} onClick={start}>{full ? "Start Game" : `Waiting for ${4 - lobby.players.length} more`}</button>
          ) : (
            <div className="waiting-note"><span className="spinner" /> Waiting for the host to start</div>
          )}
        </section>

        <aside className="invite-panel">
          <span className="eyebrow">Invite players</span>
          <div className="pin-label">Lobby PIN</div>
          <div className="lobby-pin" aria-label={`Lobby PIN ${lobby.pin}`}>{lobby.pin.slice(0, 3)} <span>{lobby.pin.slice(3)}</span></div>
          <p>Scan or share the link. It joins this lobby immediately.</p>
          <div className="qr-frame">{inviteUrl && <QRCodeSVG value={inviteUrl} size={188} bgColor="#f4f1e8" fgColor="#151a21" level="M" marginSize={2} />}</div>
          <div className="invite-link"><input readOnly value={inviteUrl} aria-label="Invitation link" onFocus={(event) => event.currentTarget.select()} /><button type="button" onClick={copyInvite} aria-label="Copy invitation link">{copied ? <CheckIcon /> : <CopyIcon />}</button></div>
          <span className="privacy-note">Your private player token is never included.</span>
        </aside>
      </div>
    </main>
  );
}

function ConnectionPill({ connection }: { connection: ConnectionState }) {
  const label = connection === "open" ? "Connected" : connection === "closed" ? "Offline" : "Reconnecting";
  return <div className={`connection-pill connection-${connection}`}><i />{connection !== "open" && <span className="spinner" />}{label}</div>;
}
