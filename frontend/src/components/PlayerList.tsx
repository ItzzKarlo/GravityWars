import type { PlayerState } from "@/lib/types";
import { CardsIcon } from "./Icons";

interface PlayerListProps {
  players: PlayerState[];
  currentTurn: number;
  localPlayerId: string;
  finished?: boolean;
  className?: string;
  onRevokePlayer?: (playerId: string) => void;
}

export function PlayerCard({ player, active, local, finished, onRevoke }: { player: PlayerState; active: boolean; local: boolean; finished?: boolean; onRevoke?: () => void }) {
  return (
    <div className={`player-card player-${player.color}${active && !finished ? " is-active" : ""}${!player.connected ? " is-offline" : ""}`}>
      <span className="player-token" aria-hidden="true" />
      <div className="player-card-copy">
        <div className="player-name">{player.username}{local && <span className="you-label">You</span>}</div>
        <div className="player-meta">
          <span className={`connection-dot${player.connected ? " online" : ""}`} />
          {player.connected ? (active && !finished ? "Taking turn" : "Connected") : "Disconnected"}
        </div>
      </div>
      <div className="joker-count" title={`${player.joker_count} joker${player.joker_count === 1 ? "" : "s"} remaining`}>
        <CardsIcon /> <span>{player.joker_count}</span>
      </div>
      {onRevoke && <button className="game-revoke-player" type="button" onClick={onRevoke} title={`Revoke ${player.username}'s access`} aria-label={`Revoke ${player.username}'s access`}>×</button>}
    </div>
  );
}

export default function PlayerList({ players, currentTurn, localPlayerId, finished, className = "", onRevokePlayer }: PlayerListProps) {
  return (
    <div className={`player-list ${className}`}>
      {players.map((player, index) => (
        <PlayerCard key={player.id} player={player} active={index === currentTurn} local={player.id === localPlayerId} finished={finished} onRevoke={!finished && ! (player.id === localPlayerId) && onRevokePlayer ? () => onRevokePlayer(player.id) : undefined} />
      ))}
    </div>
  );
}
