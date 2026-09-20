import type { PlayerState } from "@/lib/types";
import { CardsIcon } from "./Icons";

interface PlayerListProps {
  players: PlayerState[];
  currentTurn: number;
  localPlayerId: string;
  finished?: boolean;
  className?: string;
}

export function PlayerCard({ player, active, local, finished }: { player: PlayerState; active: boolean; local: boolean; finished?: boolean }) {
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
    </div>
  );
}

export default function PlayerList({ players, currentTurn, localPlayerId, finished, className = "" }: PlayerListProps) {
  return (
    <div className={`player-list ${className}`}>
      {players.map((player, index) => (
        <PlayerCard key={player.id} player={player} active={index === currentTurn} local={player.id === localPlayerId} finished={finished} />
      ))}
    </div>
  );
}
