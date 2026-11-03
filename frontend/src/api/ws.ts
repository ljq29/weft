import { sessionToken } from "./client";
import { useRunStore } from "../stores/runStore";

export function connectRuns(workflowId: string): () => void {
  const socket = new WebSocket(`ws://${window.location.host}/api/ws`);
  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({ op: "authenticate", token: sessionToken() }));
    socket.send(
      JSON.stringify({ op: "subscribe", topics: [`workflow:${workflowId}`] }),
    );
  });
  socket.addEventListener("message", (event) => {
    const message = JSON.parse(String(event.data)) as {
      event: string;
      data: Record<string, unknown>;
    };
    useRunStore.getState().apply(message);
    window.dispatchEvent(new CustomEvent("weft-chat", { detail: message }));
  });
  const unsubscribe = useRunStore.subscribe(
    (state) => state.runId,
    (runId) => {
      if (socket.readyState === WebSocket.OPEN && runId)
        socket.send(
          JSON.stringify({ op: "subscribe", topics: [`run:${runId}`] }),
        );
    },
  );
  return () => {
    unsubscribe();
    socket.close();
  };
}
