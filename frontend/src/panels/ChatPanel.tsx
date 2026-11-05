import { useEffect, useState } from "react";
import { api, formatApiError } from "../api/client";
import { useRunStore } from "../stores/runStore";
import { Icon } from "../components/Icon";

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
            setNotice(formatApiError(reason));
          },
        );
      }
      setNotice(result.disposition === "dropped" ? "已有运行，消息已丢弃" : "");
      setInput("");
    } catch (reason) {
      setNotice(formatApiError(reason));
    }
  };
  return (
    <section className="chat-panel" aria-label="聊天面板">
      <header className="chat-header">
        <div className="chat-title">
          <img src="/weft-mark.svg" alt="" />
          <div>
            <h2>Weft 对话</h2>
            <span>
              <span className={`status-dot ${enabled ? "succeeded" : ""}`} />
              {enabled ? "聊天触发已启用" : "聊天触发未启用"}
            </span>
          </div>
        </div>
        <div className="chat-actions">
          <button
            className="button ghost"
            onClick={() => {
              setSessionId(newSession());
              setRunId("");
              setMessages([]);
              setNotice("");
            }}
          >
            <Icon name="plus" />
            新会话
          </button>
          <button
            className="button ghost"
            onClick={() => {
              void api(`/workflows/${workflowId}/chat/${sessionId}/clear`, {
                method: "POST",
                body: JSON.stringify({ clear_memory: false }),
              }).then(() => {
                setMessages([]);
              });
            }}
          >
            <Icon name="trash" />
            清空会话
          </button>
          <button className="icon-button" aria-label="关闭" onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
      </header>
      <div className="chat-messages" aria-live="polite">
        {messages.map((message) => (
          <div
            className="chat-message"
            key={message.message_id}
            data-role={message.role}
          >
            <span className="message-avatar">
              {message.role === "user" ? (
                "你"
              ) : message.role === "assistant" ? (
                <img src="/weft-mark.svg" alt="" />
              ) : (
                <Icon name="info" />
              )}
            </span>
            <div>
              <strong>
                {message.role === "user"
                  ? "你"
                  : message.role === "assistant"
                    ? "Weft"
                    : "系统"}
              </strong>
              <p>
                {message.content}
                {message.streaming ? " …" : ""}
              </p>
            </div>
          </div>
        ))}
        {messages.length === 0 && (
          <div className="empty-state">
            <span className="empty-state-icon">
              <Icon name="send" />
            </span>
            <h3>用对话触发工作流</h3>
            <p>描述你希望这个工作流完成的事情。</p>
          </div>
        )}
      </div>
      <div className="chat-composer">
        <div className="composer-box">
          <textarea
            aria-label="聊天内容"
            placeholder="描述你想要这个工作流完成的事…"
            value={input}
            onChange={(event) => {
              setInput(event.target.value);
            }}
          />
          <div>
            <span>
              <Icon name="shield" />
              本地工作流 · 会话独立保存
            </span>
            <button className="button primary" onClick={() => void send()}>
              <Icon name="send" />
              发送
            </button>
          </div>
        </div>
        <p className="chat-notice" role="status">
          {notice}
        </p>
      </div>
    </section>
  );
}
