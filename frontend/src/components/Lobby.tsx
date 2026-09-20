"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  getAccessSession,
  getInvitations,
  getLobby,
  getLobbyCredentials,
  leaveLobby,
  loadCredentials,
  loadStoredInvitations,
  removeCredentials,
  revokeInvitation,
  revokePlayer,
  saveRecoveredCredentials,
  storeInvitations,
} from "@/lib/api";
import { LobbySocket } from "@/lib/websocket";
import type {
  AccessRole,
  ClientMessage,
  ConnectionState,
  Invitation,
  JokerType,
  LobbyCredentials,
  LobbyState,
  PlayerColor,
  ServerMessage,
} from "@/lib/types";
import { CheckIcon, CopyIcon, EditIcon } from "./Icons";
import Game from "./Game";
import PrivateAccess from "./PrivateAccess";

const slotColors: PlayerColor[] = ["red", "blue", "green", "yellow"];

export default function Lobby({ code }: { code: string }) {
  const router = useRouter();
  const [credentials, setCredentials] = useState<LobbyCredentials | null>(null);
  const [lobby, setLobby] = useState<LobbyState | null>(null);
  const [role, setRole] = useState<AccessRole | null>(null);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [hand, setHand] = useState<JokerType[]>([]);
  const [connection, setConnection] = useState<ConnectionState>("connecting");
  const [fatalError, setFatalError] = useState<string | null>(null);
  const [serverError, setServerError] = useState<{ id: number; message: string } | null>(null);
  const socketRef = useRef<LobbySocket | null>(null);
  const errorId = useRef(0);

  useEffect(() => {
    let active = true;
    async function initialize() {
      try {
        const access = await getAccessSession();
        if (!access.authenticated || !access.role) throw new Error("Private game — invitation required.");
        if (access.role === "guest" && access.lobby_id !== code) throw new Error("This invitation does not grant access to that lobby.");
        let playerCredentials = loadCredentials(code);
        if (!playerCredentials) playerCredentials = saveRecoveredCredentials(await getLobbyCredentials(code));
        const state = await getLobby(code);
        if (!active) return;
        setRole(access.role);
        setCredentials(playerCredentials);
        setLobby(state);
        if (access.role === "admin") {
          const stored = loadStoredInvitations(code);
          const metadata = (await getInvitations(code)).invitations;
          const merged = metadata.map((item) => ({ ...item, secret: stored.find((candidate) => candidate.id === item.id)?.secret }));
          setInvitations(merged);
          storeInvitations(code, merged);
        }
      } catch (error) {
        if (active) setFatalError(error instanceof Error ? error.message : "Private game — invitation required.");
      }
    }
    void initialize();
    return () => { active = false; };
  }, [code]);

  useEffect(() => {
    if (!credentials) return;
    const socket = new LobbySocket({
      lobbyId: credentials.lobbyId,
      token: credentials.token,
      onMessage: (message: ServerMessage) => {
        if (message.type === "state") {
          setLobby(message.lobby);
          setServerError(null);
          if (role === "admin" && message.lobby.status === "waiting") {
            void getInvitations(message.lobby.id).then(({ invitations: metadata }) => {
              setInvitations((current) => {
                const merged = metadata.map((item) => ({
                  ...item,
                  secret: current.find((candidate) => candidate.id === item.id)?.secret,
                }));
                storeInvitations(message.lobby.id, merged);
                return merged;
              });
            }).catch(() => undefined);
          }
        }
        if (message.type === "welcome" || message.type === "hand") setHand(message.jokers);
        if (message.type === "error") setServerError({ id: ++errorId.current, message: message.message });
      },
      onState: setConnection,
      onAuthFailure: () => {
        removeCredentials(credentials.lobbyId);
        setFatalError("Your access to this private lobby is no longer active.");
      },
    });
    socketRef.current = socket;
    socket.connect();
    return () => { socket.stop(); if (socketRef.current === socket) socketRef.current = null; };
  }, [credentials, role]);

  const send = useCallback((message: ClientMessage) => {
    setServerError(null);
    return socketRef.current?.send(message) ?? false;
  }, []);

  const leave = async () => {
    if (!credentials) return;
    await leaveLobby(credentials.lobbyId);
    removeCredentials(credentials.lobbyId);
    router.replace("/");
  };

  const removePlayer = async (playerId: string) => {
    if (!credentials) return;
    await revokePlayer(credentials.lobbyId, playerId);
  };

  if (fatalError) return <PrivateAccess title="Private game" message={fatalError} />;
  if (!lobby || !credentials || !role) return <main className="centered-page"><div className="loading-mark"><span /><span /><span /><span /></div><p className="loading-copy">Verifying your seat…</p></main>;

  if (lobby.status !== "waiting") {
    return <Game lobby={lobby} playerId={credentials.playerId} hand={hand} connection={connection} serverError={serverError} send={send} role={role} onLeave={role === "guest" ? leave : undefined} onRevokePlayer={role === "admin" ? removePlayer : undefined} />;
  }

  return <WaitingRoom lobby={lobby} playerId={credentials.playerId} role={role} invitations={invitations} setInvitations={setInvitations} connection={connection} serverError={serverError} send={send} onLeave={leave} onRevokePlayer={removePlayer} />;
}

function WaitingRoom({ lobby, playerId, role, invitations, setInvitations, connection, serverError, send, onLeave, onRevokePlayer }: { lobby: LobbyState; playerId: string; role: AccessRole; invitations: Invitation[]; setInvitations: (items: Invitation[]) => void; connection: ConnectionState; serverError: { id: number; message: string } | null; send: (message: ClientMessage) => boolean; onLeave: () => Promise<void>; onRevokePlayer: (id: string) => Promise<void> }) {
  const player = lobby.players.find((item) => item.id === playerId);
  const [username, setUsername] = useState(player?.username ?? "");
  const [editing, setEditing] = useState(false);
  const [localError, setLocalError] = useState<string | null>(null);
  const isHost = role === "admin";
  const full = lobby.players.length === 4;
  const ready = full && lobby.players.every((item) => item.connected);
  const startLabel = ready
    ? "Start Game"
    : full
      ? "Waiting for players to reconnect"
      : `Waiting for ${4 - lobby.players.length} more`;

  const rename = (event: FormEvent) => {
    event.preventDefault();
    if (!send({ type: "rename", username })) return setLocalError("Still reconnecting. Try again in a moment.");
    setEditing(false);
  };
  const start = () => {
    setLocalError(null);
    if (!send({ type: "start" })) setLocalError("Still reconnecting. Try again in a moment.");
  };
  const revoke = async (invitation: Invitation) => {
    try {
      await revokeInvitation(lobby.id, invitation.id);
      const next = invitations.map((item) => item.id === invitation.id ? { ...item, status: "revoked" as const, secret: undefined } : item);
      setInvitations(next); storeInvitations(lobby.id, next);
    } catch (error) { setLocalError(error instanceof Error ? error.message : "Could not revoke invitation."); }
  };

  return (
    <main className="lobby-page">
      <header className="lobby-header"><Link className="wordmark compact" href="/"><span>GRAVITY</span><span>WARS</span></Link><div className="lobby-head-actions">{role === "guest" && <button className="text-button leave-button" type="button" onClick={() => void onLeave()}>Leave Lobby</button>}<ConnectionPill connection={connection} /></div></header>
      <div className="lobby-layout">
        <section className="lobby-table">
          <div className="lobby-title-row"><div><span className="eyebrow">Private waiting room</span><h1>Assemble your crew</h1></div><div className="seat-count">{lobby.players.length}<span>/ 4</span></div></div>
          <div className="lobby-slots">{slotColors.map((color, index) => {
            const occupant = lobby.players[index];
            return <div className={`lobby-slot slot-${color}${occupant ? " occupied" : ""}`} key={color}><span className="slot-piece" />{occupant ? <div><strong>{occupant.username}{occupant.id === playerId && <span className="you-label">You</span>}</strong><span className="slot-status"><i className={occupant.connected ? "online" : ""} />{occupant.connected ? "Ready at the table" : "Disconnected"}</span></div> : <div><strong>Reserved seat</strong><span className="slot-status">Waiting for its invitation</span></div>}{occupant?.id === lobby.host_player_id && <span className="host-mark">Host</span>}{isHost && occupant && occupant.id !== playerId && <button className="remove-player" type="button" onClick={() => void onRevokePlayer(occupant.id)}>Revoke access</button>}</div>;
          })}</div>
          <div className="identity-row">{editing ? <form onSubmit={rename} className="rename-form"><label htmlFor="username">Your name</label><div><input id="username" value={username} onChange={(event) => setUsername(event.target.value)} minLength={3} maxLength={24} autoFocus /><button type="submit" className="button button-small">Save</button><button type="button" className="text-button" onClick={() => setEditing(false)}>Cancel</button></div></form> : <div className="current-identity"><span>Playing as</span><strong>{player?.username}</strong><button type="button" onClick={() => setEditing(true)}><EditIcon /> Change</button></div>}</div>
          {(localError || serverError) && <div className="inline-error" role="alert">{localError ?? serverError?.message}</div>}
          {isHost ? <button className="button button-primary start-button" type="button" disabled={!ready || connection !== "open"} onClick={start}>{startLabel}</button> : <div className="waiting-note"><span className="spinner" /> Waiting for the host to start</div>}
        </section>
        <aside className="invite-panel friends-panel">{isHost ? <><span className="eyebrow">Three private seats</span><h2>Friend invitations</h2><p>Each link works once and expires 30 minutes after the lobby was created.</p><div className="friend-invites">{invitations.map((invitation) => <InvitationCard key={invitation.id} invitation={invitation} onRevoke={() => void revoke(invitation)} />)}</div></> : <><span className="eyebrow">Access verified</span><div className="verified-seal"><CheckIcon /></div><h2>Your seat is reserved</h2><p>Your browser can refresh or reconnect without using another invitation. Choose Leave Lobby only when you mean to revoke this access.</p></>}</aside>
      </div>
    </main>
  );
}

function InvitationCard({ invitation, onRevoke }: { invitation: Invitation; onRevoke: () => void }) {
  const [copied, setCopied] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 30_000); return () => window.clearInterval(timer); }, []);
  const remaining = Math.max(0, Math.ceil((invitation.expires_at * 1000 - now) / 60_000));
  const available = invitation.status === "unused" && remaining > 0;
  const link = invitation.secret && typeof window !== "undefined" ? `${window.location.origin}/invite#${invitation.secret}` : "";
  const copy = async () => { if (!link) return; await navigator.clipboard.writeText(link); setCopied(true); window.setTimeout(() => setCopied(false), 1600); };
  const status = invitation.status === "unused" && !remaining ? "expired" : invitation.status;
  return <article className={`friend-invite status-${status}`}><div className="invite-number">0{invitation.slot}</div><div className="invite-card-copy"><strong>Friend {invitation.slot}</strong><span>{available ? `Expires in ${remaining} min` : status === "used" ? "Invitation used" : status === "revoked" ? "Invitation revoked" : "Invitation expired"}</span></div>{available && link ? <button className="copy-invite" type="button" onClick={() => void copy()}>{copied ? <CheckIcon /> : <CopyIcon />} {copied ? "Copied" : "Copy link"}</button> : available ? <span className="link-unavailable">Link shown only when created</span> : null}{available && <button className="revoke-invite" type="button" onClick={onRevoke}>Revoke</button>}</article>;
}

function ConnectionPill({ connection }: { connection: ConnectionState }) {
  const label = connection === "open" ? "Connected" : connection === "closed" ? "Offline" : "Reconnecting";
  return <div className={`connection-pill connection-${connection}`}><i />{connection !== "open" && <span className="spinner" />}{label}</div>;
}
