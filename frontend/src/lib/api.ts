import type {
  AccessSessionState,
  Invitation,
  LobbyCredentials,
  LobbyResponse,
  LobbyState,
} from "./types";

const stripSlash = (value: string) => value.replace(/\/$/, "");

export function apiOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_API_ORIGIN?.trim();
  if (configured) return stripSlash(configured);
  if (typeof window === "undefined") return "";
  return window.location.origin;
}

export function websocketOrigin(): string {
  const configured = process.env.NEXT_PUBLIC_WS_ORIGIN?.trim();
  if (configured) return stripSlash(configured);
  return apiOrigin().replace(/^http/, "ws");
}

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

function cookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  for (const part of document.cookie.split(";")) {
    const [key, ...value] = part.trim().split("=");
    if (key === name) return decodeURIComponent(value.join("="));
  }
  return null;
}

async function request<T>(
  path: string,
  init?: RequestInit & { csrf?: boolean },
): Promise<T> {
  let response: Response;
  const { csrf, ...requestInit } = init ?? {};
  const headers = new Headers(requestInit.headers);
  headers.set("Content-Type", "application/json");
  if (csrf) {
    const token = cookie("gw_csrf");
    if (!token) throw new ApiError("Your secure session has expired.", 401);
    headers.set("X-CSRF-Token", token);
  }
  try {
    response = await fetch(`${apiOrigin()}${path}`, {
      ...requestInit,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(
      "The game server is unavailable. Try again in a moment.",
      0,
    );
  }
  if (!response.ok) {
    let message = "Something went wrong.";
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Non-JSON proxy errors use the safe fallback.
    }
    throw new ApiError(message, response.status);
  }
  return (await response.json()) as T;
}

export const getAccessSession = () =>
  request<AccessSessionState>("/api/auth/session");

export const adminLogin = (password: string) =>
  request<AccessSessionState>("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({ username: "ADMIN", password }),
  });

export const logout = () =>
  request<{ ok: true }>("/api/auth/logout", { method: "POST", csrf: true });

export const createLobby = () =>
  request<LobbyResponse>("/api/lobbies", { method: "POST", csrf: true });

export const redeemInvitation = (secret: string) =>
  request<LobbyResponse>("/api/invitations/redeem", {
    method: "POST",
    body: JSON.stringify({ secret }),
  });

export const getLobby = (id: string) =>
  request<LobbyState>(`/api/lobbies/${encodeURIComponent(id)}`);

export const getLobbyCredentials = (id: string) =>
  request<LobbyCredentials>(
    `/api/lobbies/${encodeURIComponent(id)}/credentials`,
  );

export const getInvitations = (id: string) =>
  request<{ invitations: Invitation[] }>(
    `/api/lobbies/${encodeURIComponent(id)}/invitations`,
  );

export const revokeInvitation = (lobbyId: string, invitationId: string) =>
  request<{ ok: true }>(
    `/api/lobbies/${encodeURIComponent(lobbyId)}/invitations/${encodeURIComponent(invitationId)}/revoke`,
    { method: "POST", csrf: true },
  );

export const revokePlayer = (lobbyId: string, playerId: string) =>
  request<{ ok: true }>(
    `/api/lobbies/${encodeURIComponent(lobbyId)}/players/${encodeURIComponent(playerId)}/revoke`,
    { method: "POST", csrf: true },
  );

export const leaveLobby = (lobbyId: string) =>
  request<{ ok: true }>(
    `/api/lobbies/${encodeURIComponent(lobbyId)}/leave`,
    { method: "POST", csrf: true },
  );

const credentialKey = (lobbyId: string) =>
  `gravity-wars:${lobbyId}:player`;
const invitationKey = (lobbyId: string) =>
  `gravity-wars:${lobbyId}:invitations`;

export function saveCredentials(response: LobbyResponse): LobbyCredentials {
  const credentials = {
    lobbyId: response.lobby.id,
    playerId: response.player_id,
    token: response.token,
  };
  sessionStorage.setItem(
    credentialKey(response.lobby.id),
    JSON.stringify(credentials),
  );
  if (response.invitations) {
    sessionStorage.setItem(
      invitationKey(response.lobby.id),
      JSON.stringify(response.invitations),
    );
  }
  return credentials;
}

export function saveRecoveredCredentials(
  credentials: LobbyCredentials,
): LobbyCredentials {
  sessionStorage.setItem(
    credentialKey(credentials.lobbyId),
    JSON.stringify(credentials),
  );
  return credentials;
}

export function loadCredentials(lobbyId: string): LobbyCredentials | null {
  try {
    const raw = sessionStorage.getItem(credentialKey(lobbyId));
    if (!raw) return null;
    const value = JSON.parse(raw) as Partial<LobbyCredentials>;
    if (value.lobbyId !== lobbyId || !value.playerId || !value.token) return null;
    return value as LobbyCredentials;
  } catch {
    return null;
  }
}

export function loadStoredInvitations(lobbyId: string): Invitation[] {
  try {
    const raw = sessionStorage.getItem(invitationKey(lobbyId));
    return raw ? (JSON.parse(raw) as Invitation[]) : [];
  } catch {
    return [];
  }
}

export function storeInvitations(lobbyId: string, invitations: Invitation[]) {
  sessionStorage.setItem(invitationKey(lobbyId), JSON.stringify(invitations));
}

export function removeCredentials(lobbyId: string) {
  sessionStorage.removeItem(credentialKey(lobbyId));
  sessionStorage.removeItem(invitationKey(lobbyId));
}
