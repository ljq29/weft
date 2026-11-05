import { create } from "zustand";

export type ConnectionStatus =
  | "idle"
  | "connecting"
  | "authenticating"
  | "subscribing"
  | "ready"
  | "disconnected"
  | "backoff";

interface ConnectionState {
  status: ConnectionStatus;
  workflowId: string;
  attempt: number;
  retryAt: number | null;
  error: string;
  reconnect: () => void;
}

let reconnectHandler: (() => void) | null = null;

export function setReconnectHandler(handler: (() => void) | null): void {
  reconnectHandler = handler;
}

export const useConnectionStore = create<ConnectionState>(() => ({
  status: "idle",
  workflowId: "",
  attempt: 0,
  retryAt: null,
  error: "",
  reconnect: () => {
    reconnectHandler?.();
  },
}));
