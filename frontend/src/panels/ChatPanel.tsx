import { useEffect, useState } from "react";
import { api } from "../api/client";
import { useRunStore } from "../stores/runStore";

interface ChatMessage {
  message_id: string;
  role: string;
  content: string;
  streaming: boolean;
}
interface ChatEvent {
  event: string;
  data: Record<string, unknown>;
}
interface ChatLink {
  source_node_id: string;
  message_id: string;
}
function text(value: unknown): string {
  if (typeof value === "string") return value;
  const serialized: unknown = JSON.stringify(value);
  return typeof serialized === "string" ? serialized : "";
}
function newSession(): string {
  return `s_${crypto.randomUUID().replaceAll("-", "")}`;
}

export function ChatPanel({
  workflowId,
  enabled,
  onClose,
}: {
  workflowId: string;
  enabled: boolean;
  onClose: () => void;
}) {
  const [sessionId, setSessionId] = useState(newSession);
  const [runId, setRunId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    void api<ChatMessage[]>(`/workflows/${workflowId}/chat/${sessionId}`)
      .then((messages) => {
        setMessages(messages);
      })
      .catch(() => {
        setMessages([]);
      });
  }, [workflowId, sessionId]);
  useEffect(() => {
    const listener = (event: Event) => {
      const message = (event as CustomEvent<ChatEvent>).detail;
      const data = message.data;
      if (message.event === "chat.message" && data.session_id === sessionId) {
        const final: ChatMessage = {
          message_id: text(data.message_id),
          role: text(data.role),
          content: text(data.content),
          streaming: false,
        };
        setMessages((current) => {
          const index = current.findIndex(
            (item) => item.message_id === final.message_id,
          );
          if (index < 0) return [...current, final];
          return current.map((item, itemIndex) =>
            itemIndex === index ? final : item,
          );
        });
      }
      if (message.event === "node.stream" && data.run_id === runId) {
        const links = (data.chat_links ?? []) as ChatLink[];
        for (const link of links) {
          setMessages((current) => {
            const index = current.findIndex(
              (item) => item.message_id === link.message_id,
            );
            if (index < 0)
              return [
                ...current,
                {
                  message_id: link.message_id,
                  role: "assistant",
                  content: text(data.delta),
                  streaming: true,
                },
              ];
            return current.map((item, itemIndex) =>
              itemIndex === index
                ? { ...item, content: item.content + text(data.delta) }
                : item,
            );
          });
        }
      }
      if (message.event === "run.finished" && data.run_id === runId) {
        setMessages((current) => {
          if (
            current.some(
              (item) =>
                item.role === "assistant" && item.message_id.includes(runId),
            )
          )
            return current;
          return [
            ...current,
            {
              message_id: `m_${runId}_empty`,
              role: "system",
              content: "运行完成（无输出）",
              streaming: false,
            },
          ];
        });
      }
    };
    window.addEventListener("weft-chat", listener);
    return () => {
      window.removeEventListener("weft-chat", listener);
    };
  }, [runId, sessionId]);
  const reconcile = async (runId: string, sessionId: string) => {
    let status = "";
    for (let attempt = 0; attempt < 200; attempt += 1) {
      const record = await api<{ status: string }>(`/runs/${runId}`);
      status = record.status;
      if (["succeeded", "failed", "cancelled"].includes(status)) break;
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
    const history = await api<ChatMessage[]>(
      `/workflows/${workflowId}/chat/${sessionId}`,
    );
    if (
      status === "succeeded" &&
      !history.some(
        (item) => item.role === "assistant" && item.message_id.includes(runId),
      )
    )
      history.push({
        message_id: `m_${runId}_empty`,
        role: "system",
        content: "运行完成（无输出）",
        streaming: false,
      });
    setMessages(history);
  };
  const send = async () => {
    if (!enabled) {
      setNotice("该工作流未启用聊天触发");
      return;
    }
    try {
      const result = await api<{
        run_id: string | null;
        session_id: string;
        disposition: string;
      }>(`/workflows/${workflowId}/chat`, {
        method: "POST",
        body: JSON.stringify({ message: input, session_id: sessionId }),
      });
      setMessages((current) => [
        ...current,
        {
          message_id: `m_local_${crypto.randomUUID()}`,
          role: "user",
          content: input,
          streaming: false,
        },
      ]);
      setSessionId(result.session_id);
      setRunId(result.run_id ?? "");
      if (result.run_id) {
        useRunStore.getState().started(result.run_id);
        void reconcile(result.run_id, result.session_id).catch(
          (reason: unknown) => {
            setNotice(String(reason));
          },
        );
      }
      setNotice(result.disposition === "dropped" ? "已有运行，消息已丢弃" : "");
      setInput("");
    } catch (reason) {
      setNotice(String(reason));
    }
  };
  return (
    <section className="chat-panel" aria-label="聊天面板">
      <button onClick={onClose}>关闭</button>
      <button
        onClick={() => {
          setSessionId(newSession());
          setRunId("");
          setMessages([]);
          setNotice("");
        }}
      >
        新会话
      </button>
      <button
        onClick={() => {
          void api(`/workflows/${workflowId}/chat/${sessionId}/clear`, {
            method: "POST",
            body: JSON.stringify({ clear_memory: false }),
          }).then(() => {
            setMessages([]);
          });
        }}
      >
        清空会话
      </button>
      <div aria-live="polite">
        {messages.map((message) => (
          <p key={message.message_id} data-role={message.role}>
            {message.content}
            {message.streaming ? " …" : ""}
          </p>
        ))}
      </div>
      <textarea
        aria-label="聊天内容"
        value={input}
        onChange={(event) => {
          setInput(event.target.value);
        }}
      />
      <button onClick={() => void send()}>发送</button>
      <p role="status">{notice}</p>
    </section>
  );
}
