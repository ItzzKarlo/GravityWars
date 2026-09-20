import { websocketOrigin } from "./api";
import type { ClientMessage, ConnectionState, ServerMessage } from "./types";

interface SocketOptions {
  lobbyId: string;
  token: string;
  onMessage: (message: ServerMessage) => void;
  onState: (state: ConnectionState) => void;
  onAuthFailure: () => void;
}

export class LobbySocket {
  private socket: WebSocket | null = null;
  private stopped = false;
  private generation = 0;
  private retry = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(private readonly options: SocketOptions) {}

  connect() {
    if (this.stopped) return;
    const generation = ++this.generation;
    this.options.onState(this.retry ? "reconnecting" : "connecting");
    const url = `${websocketOrigin()}/ws/lobbies/${encodeURIComponent(this.options.lobbyId)}`;
    const socket = new WebSocket(url);
    this.socket = socket;

    socket.addEventListener("open", () => {
      if (generation !== this.generation || this.stopped) return socket.close();
      this.retry = 0;
      socket.send(JSON.stringify({ type: "auth", token: this.options.token }));
      this.options.onState("open");
    });

    socket.addEventListener("message", (event) => {
      if (generation !== this.generation || this.stopped) return;
      try {
        this.options.onMessage(JSON.parse(String(event.data)) as ServerMessage);
      } catch {
        // Ignore malformed frames. The next authoritative state remains usable.
      }
    });

    socket.addEventListener("close", (event) => {
      if (generation !== this.generation || this.stopped) return;
      if (event.code === 4401) {
        this.options.onState("closed");
        this.options.onAuthFailure();
        return;
      }
      this.scheduleReconnect();
    });

    socket.addEventListener("error", () => {
      if (generation === this.generation) socket.close();
    });
  }

  send(message: ClientMessage): boolean {
    if (this.socket?.readyState !== WebSocket.OPEN) return false;
    this.socket.send(JSON.stringify(message));
    return true;
  }

  stop() {
    this.stopped = true;
    this.generation += 1;
    if (this.timer) clearTimeout(this.timer);
    this.socket?.close();
    this.options.onState("closed");
  }

  private scheduleReconnect() {
    this.retry += 1;
    this.options.onState("reconnecting");
    const delay = Math.min(1000 * 2 ** (this.retry - 1), 8000);
    this.timer = setTimeout(() => this.connect(), delay);
  }
}
