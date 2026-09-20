import type { LobbyCredentials, LobbyResponse, LobbyState } from "./types";

const stripSlash = (value: string) => value.replace(/\/$/, "");

export function apiOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_API_ORIGIN?.trim();
  if (configured) return stripSlash(configured);
  if (typeof window === "undefined") return "http://127.0.0.1:8000";
  return `${window.location.protocol}//${window.location.hostname}:8000`;
}

export function websocketOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_WS_ORIGIN?.trim();
  if (configured) return stripSlash(configured);
  return apiOrigin().replace(/^http/, "ws");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${apiOrigin()}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("The game server is unavailable. Check that FastAPI is running.");
  }

  if (!response.ok) {
    let message = "Something went wrong.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the restrained fallback message for non-JSON responses.
    }
    throw new Error(message);
  }
  return (await response.json()) as T;
}

export const createLobby = () => request<LobbyResponse>("/api/lobbies", { method: "POST" });

export const joinLobby = (code: string) =>
  request<LobbyResponse>("/api/lobbies/join", {
    method: "POST",
    body: JSON.stringify({ code }),
  });

export const getLobby = (id: string) =>
  request<LobbyState>(`/api/lobbies/${encodeURIComponent(id)}`);

const key = (lobbyId: string) => `gravity-wars:${lobbyId}:session`;

export function saveCredentials(response: LobbyResponse): LobbyCredentials {
  const credentials = {
    lobbyId: response.lobby.id,
    playerId: response.player_id,
    token: response.token,
  };
  sessionStorage.setItem(key(response.lobby.id), JSON.stringify(credentials));
  return credentials;
}

export function loadCredentials(lobbyId: string): LobbyCredentials | null {
  try {
    const raw = sessionStorage.getItem(key(lobbyId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<LobbyCredentials>;
    if (value.lobbyId !== lobbyId || !value.playerId || !value.token) return null;
    return value as LobbyCredentials;
  } catch {
    return null;
  }
}

export function removeCredentials(lobbyId: string) {
  sessionStorage.removeItem(key(lobbyId));
}
