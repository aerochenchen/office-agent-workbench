import { useEffect, useMemo, useState } from "react";
import type { ChatMessage, LiveStep } from "../lib/types";
import { APP_NAME, APP_TAGLINE } from "../lib/brand";
import { GUIDE_HINTS, GUIDE_PILLARS, GUIDE_WELCOME_TITLE } from "../lib/guide";
import "./ChatPanel.css";

interface Props {
  workspaceOpen: boolean;
  messages: ChatMessage[];
  sending: boolean;
  runtimeReady: boolean;
  onSend: (text: string) => void;
  onOpenWorkspace?: () => void;
  onToggleSteps?: (messageId: string) => void;
}

const PHASE_HINTS = ["理解指令…", "查看工作区…", "读写或运行脚本…", "整理结果…"] as const;

function formatElapsed(startedAt?: number, now = Date.now()): string {
  if (!startedAt) return "0:00";
  const sec = Math.max(0, Math.floor((now - startedAt) / 1000));
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
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

function LiveStepRow({ step }: { step: LiveStep }) {
  return (
    <div className={`live-step live-step--${step.status}`}>
      <span className="live-step-mark" aria-hidden="true" />
      <span className="live-step-label">{step.label}</span>
      {step.summary ? <span className="live-step-summary mono">{step.summary}</span> : null}
    </div>
  );
}

function PendingBody({ message, now }: { message: ChatMessage; now: number }) {
  const hintIndex = Math.floor(((now - (message.startedAt ?? now)) / 3500) % PHASE_HINTS.length);
  const phaseText =
    message.statusPhase === "tools"
      ? "正在执行工具…"
      : message.statusPhase === "finishing"
        ? "正在整理结果…"
        : message.phase === "live"
          ? "正在处理…"
          : PHASE_HINTS[hintIndex];
  const hasLive = (message.liveSteps?.length ?? 0) > 0;

  return (
    <div className="pending-body">
      <div className="pending-line">
        <span className="pending-pulse" aria-hidden="true" />
        <span>正在处理你的任务…</span>
        <span className="pending-elapsed mono">已等待 {formatElapsed(message.startedAt, now)}</span>
      </div>
      {!hasLive && <div className="pending-hint">{phaseText}</div>}
      {hasLive && (
        <div className="live-steps">
          {message.liveSteps!.map((step) => (
            <LiveStepRow key={step.id} step={step} />
          ))}
        </div>
      )}
      {(now - (message.startedAt ?? now)) > 15_000 && (
        <div className="pending-note">涉及读写或跑脚本时可能需要一两分钟，请稍候。</div>
      )}
    </div>
  );
}

function Bubble({
  message,
  now,
  onToggleSteps,
}: {
  message: ChatMessage;
  now: number;
  onToggleSteps?: (messageId: string) => void;
}) {
  const roleClass =
    message.role === "user"
      ? "bubble--user"
      : message.role === "error"
        ? "bubble--error"
        : "bubble--assistant";

  const inFlight = message.role === "assistant" && (message.phase === "pending" || message.phase === "live");
  const stepCount = message.liveSteps?.length || message.toolEvents?.length || 0;
  const showCollapsed =
    message.role === "assistant" &&
    message.phase === "done" &&
    stepCount > 0 &&
    !message.stepsExpanded;
  const showExpandedDone =
    message.role === "assistant" &&
    message.phase === "done" &&
    stepCount > 0 &&
    Boolean(message.stepsExpanded);

  return (
    <div className={`message-row message-row--${message.role}`}>
      <div className={`bubble ${roleClass}`}>
        {inFlight ? <PendingBody message={message} now={now} /> : message.content}
      </div>

      {showCollapsed && (
        <button
          type="button"
          className="steps-toggle"
          onClick={() => onToggleSteps?.(message.id)}
        >
          已完成 {stepCount} 步 · 点击展开
        </button>
      )}

      {showExpandedDone && (
        <div className="tool-events">
          <button
            type="button"
            className="steps-toggle steps-toggle--inline"
            onClick={() => onToggleSteps?.(message.id)}
          >
            收起过程
          </button>
          {message.liveSteps && message.liveSteps.length > 0
            ? message.liveSteps.map((step) => <LiveStepRow key={step.id} step={step} />)
            : message.toolEvents?.map((ev, idx) => (
                <ToolEventRow key={`${ev.name}-${idx}`} name={ev.name} result={ev.result} />
              ))}
        </div>
      )}

      {/* Legacy / fallback: tool events without phase metadata */}
      {message.role === "assistant" &&
        !message.phase &&
        message.toolEvents &&
        message.toolEvents.length > 0 && (
          <div className="tool-events">
            {message.toolEvents.map((ev, idx) => (
              <ToolEventRow key={`${ev.name}-${idx}`} name={ev.name} result={ev.result} />
            ))}
          </div>
        )}
    </div>
  );
}

export default function ChatPanel({
  workspaceOpen,
  messages,
  sending,
  runtimeReady,
  onSend,
  onOpenWorkspace,
  onToggleSteps,
}: Props) {
  const [draft, setDraft] = useState("");
  const [now, setNow] = useState(() => Date.now());
  const hasPending = useMemo(
    () => messages.some((m) => m.phase === "pending" || m.phase === "live"),
    [messages],
  );

  useEffect(() => {
    const el = document.querySelector(".chat-scroll");
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, now]);

  useEffect(() => {
    if (!hasPending) return;
    const timer = window.setInterval(() => setNow(Date.now()), 500);
    return () => window.clearInterval(timer);
  }, [hasPending]);

  const disabled = !workspaceOpen || sending || !runtimeReady;

  function submit() {
    const text = draft.trim();
    if (!text || disabled) return;
    onSend(text);
    setDraft("");
  }

  return (
    <section className="pane chat-pane">
      <div className="pane-header">
        <span className="pane-title">当前对话</span>
        {sending && <span className="chat-status">运行中…</span>}
      </div>

      <div className="pane-body chat-scroll">
        {messages.length === 0 && !workspaceOpen && (
          <div className="guide-welcome">
            <img
              className="chat-empty-logo"
              src="/logo-mark.png"
              width={48}
              height={48}
              alt=""
              aria-hidden="true"
            />
            <div className="chat-empty-brand">
              <div className="chat-empty-name">{APP_NAME}</div>
              <div className="chat-empty-tagline">{APP_TAGLINE}</div>
            </div>
            <h2 className="guide-welcome-title">{GUIDE_WELCOME_TITLE}</h2>
            <ul className="guide-pillars">
              {GUIDE_PILLARS.map((p) => (
                <li key={p.id} className="guide-pillar">
                  <div className="guide-pillar-title">{p.title}</div>
                  <p className="guide-pillar-body">{p.summary}</p>
                </li>
              ))}
            </ul>
            {onOpenWorkspace ? (
              <button
                type="button"
                className="btn btn--primary guide-welcome-cta"
                disabled={!runtimeReady}
                title={!runtimeReady ? "本地运行时未就绪" : undefined}
                onClick={onOpenWorkspace}
              >
                打开文件夹
              </button>
            ) : (
              <p className="empty-hint chat-empty-hint">{GUIDE_HINTS.noWorkspace}</p>
            )}
          </div>
        )}
        {messages.length === 0 && workspaceOpen && (
          <div className="chat-empty">
            <img
              className="chat-empty-logo"
              src="/logo-mark.png"
              width={48}
              height={48}
              alt=""
              aria-hidden="true"
            />
            <div className="chat-empty-brand">
              <div className="chat-empty-name">{APP_NAME}</div>
              <div className="chat-empty-tagline">{APP_TAGLINE}</div>
            </div>
            <div className="empty-hint chat-empty-hint">{GUIDE_HINTS.workspaceReady}</div>
          </div>
        )}
        {messages.map((m) => (
          <Bubble key={m.id} message={m} now={now} onToggleSteps={onToggleSteps} />
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
          placeholder={
            !runtimeReady
              ? "本地运行时未就绪…"
              : sending
                ? "处理中，完成后可继续…"
                : workspaceOpen
                  ? "输入指令，Enter 发送，Shift+Enter 换行"
                  : "请先打开工作区"
          }
          value={draft}
          disabled={!workspaceOpen || sending || !runtimeReady}
          rows={2}
          onChange={(e) => setDraft(e.currentTarget.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
        />
        <button
          type="submit"
          className={`btn${workspaceOpen && runtimeReady ? " btn--primary" : " btn--ghost"}`}
          disabled={disabled || !draft.trim()}
        >
          发送
        </button>
      </form>
    </section>
  );
}
