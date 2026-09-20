export type PlayerColor = "red" | "blue" | "green" | "yellow";
export type GravityDirection = "up" | "down" | "left" | "right";
export type GameStatus = "waiting" | "playing" | "finished";

export type JokerType =
  | "gravity_roulette"
  | "fifty_fifty"
  | "skip"
  | "steal"
  | "swap"
  | "gravity_lock";

export type Cell = PlayerColor | null;
export type Board = Cell[][];
export type Position = [row: number, column: number];

export interface PlayerState {
  id: string;
  username: string;
  color: PlayerColor;
  connected: boolean;
  joker_count: number;
}

export interface LobbyState {
  id: string;
  pin: string;
  host_player_id: string;
  status: GameStatus;
  gravity: GravityDirection;
  gravity_locked: boolean;
  current_turn: number;
  winner_ids: string[];
  board: Board;
  players: PlayerState[];
}

export interface LobbyCredentials {
  lobbyId: string;
  playerId: string;
  token: string;
}

export interface LobbyResponse {
  lobby: LobbyState;
  player_id: string;
  token: string;
  invitations?: Invitation[];
}

export type AccessRole = "admin" | "guest";

export interface AccessSessionState {
  authenticated: boolean;
  role: AccessRole | null;
  lobby_id?: string | null;
  player_id?: string | null;
}

export type InvitationStatus = "unused" | "used" | "revoked" | "expired";

export interface Invitation {
  id: string;
  slot: number;
  expires_at: number;
  status: InvitationStatus;
  secret?: string;
}

export type ServerMessage =
  | { type: "welcome"; player_id: string; jokers: JokerType[] }
  | { type: "state"; lobby: LobbyState }
  | { type: "hand"; jokers: JokerType[] }
  | { type: "error"; message: string };

export type ClientMessage =
  | { type: "auth"; token: string }
  | { type: "start" }
  | { type: "rematch" }
  | { type: "drop"; lane: number }
  | { type: "rename"; username: string }
  | {
      type: "joker";
      joker: JokerType;
      target?: Position;
      second_target?: Position;
    };

export type ConnectionState = "connecting" | "open" | "reconnecting" | "closed";
