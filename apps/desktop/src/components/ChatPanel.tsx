import { useEffect, useRef, useState } from "react";
import type { ChatMessage } from "../lib/types";
import "./ChatPanel.css";

interface Props {
  workspaceOpen: boolean;
  messages: ChatMessage[];
  sending: boolean;
  onSend: (text: string) => void;
}

function ToolEventRow({ name, result }: { name: string; result: unknown }) {
  const [expanded, setExpanded] = useState(false);
  const summary =
    typeof result === "string" ? result : JSON.stringify(result ?? {});
  return (
    <div className="tool-row" onClick={() => setExpanded((v) => !v)}>
      <span className="tool-dot" aria-hidden="true" />
      <span className="tool-name mono">{name}</span>
      <span className={`tool-summary mono${expanded ? " tool-summary--expanded" : ""}`}>
        {summary}
      </span>
    </div>
  );
}

function Bubble({ message }: { message: ChatMessage }) {
  const roleClass =
    message.role === "user"
      ? "bubble--user"
      : message.role === "error"
        ? "bubble--error"
        : "bubble--assistant";
  return (
    <div className={`message-row message-row--${message.role}`}>
      <div className={`bubble ${roleClass}`}>{message.content}</div>
      {message.toolEvents && message.toolEvents.length > 0 && (
        <div className="tool-events">
          {message.toolEvents.map((ev, idx) => (
            <ToolEventRow key={`${ev.name}-${idx}`} name={ev.name} result={ev.result} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ChatPanel({ workspaceOpen, messages, sending, onSend }: Props) {
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  const disabled = !workspaceOpen || sending;

  function submit() {
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft("");
  }

  return (
    <section className="pane chat-pane">
      <div className="pane-header">
        <span className="pane-title">对话</span>
        {sending && <span className="chat-status">运行中…</span>}
      </div>

      <div className="pane-body chat-scroll" ref={scrollRef}>
        {messages.length === 0 && (
          <div className="empty-hint">
            {workspaceOpen
              ? "向助手描述需要处理的公文任务，例如「整理本目录下的会议记要」。"
              : "请先在左侧选择工作区文件夹，才能开始对话。"}
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} />
        ))}
      </div>

      <form
        className="chat-input-row"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <textarea
          className="chat-input"
          placeholder={workspaceOpen ? "输入指令，Enter 发送，Shift+Enter 换行" : "请先打开工作区"}
          value={draft}
          disabled={!workspaceOpen}
          rows={2}
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button type="submit" className="btn btn--primary" disabled={disabled || !draft.trim()}>
          发送
        </button>
      </form>
    </section>
  );
}
