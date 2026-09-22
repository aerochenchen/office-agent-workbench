import type { SessionMeta } from "../lib/types";
import { GUIDE_HINTS } from "../lib/guide";
import "./SessionList.css";

interface Props {
  workspacePath: string | null;
  workspaceError: string | null;
  sessions: SessionMeta[];
  activeSessionId: string | undefined;
  sending: boolean;
  runtimeReady: boolean;
  onPickWorkspace: () => void;
  onNewSession: () => void;
  onSelectSession: (id: string) => void;
  onDeleteSession: (id: string) => void;
}

function formatRelativeTime(ts: number): string {
  if (!ts) return "";
  const ms = ts > 1e12 ? ts : ts * 1000;
  const diff = Date.now() - ms;
  if (diff < 60_000) return "刚刚";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} 分钟前`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} 小时前`;
  if (diff < 172800_000) return "昨天";
  const d = new Date(ms);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

function basename(path: string): string {
  const parts = path.replace(/\\/g, "/").split("/");
  return parts.filter(Boolean).pop() || path;
}

export default function SessionList({
  workspacePath,
  workspaceError,
  sessions,
  activeSessionId,
  sending,
  runtimeReady,
  onPickWorkspace,
  onNewSession,
  onSelectSession,
  onDeleteSession,
}: Props) {
  return (
    <section className="pane session-pane">
      <div className="pane-header">
        <span className="pane-title">对话</span>
      </div>

      <div className="session-toolbar">
        <button
          type="button"
          className="btn btn--ghost btn--full"
          disabled={!workspacePath || sending || !runtimeReady}
          onClick={onNewSession}
          title={
            !workspacePath
              ? GUIDE_HINTS.newSessionNeedsFolder
              : sending
                ? "请等待当前回复结束"
                : undefined
          }
        >
          新建对话
        </button>
      </div>

      <div className="pane-body session-list-body">
        {!workspacePath && (
          <div className="empty-hint">{GUIDE_HINTS.noWorkspace}</div>
        )}
        {workspacePath && sessions.length === 0 && (
          <div className="empty-hint">{GUIDE_HINTS.noSessions}</div>
        )}
        <ul className="session-list">
          {sessions.map((s) => {
            const active = s.id === activeSessionId;
            const blocked = sending && s.id !== activeSessionId;
            return (
              <li key={s.id}>
                <div
                  className={`session-row${active ? " session-row--active" : ""}${
                    blocked ? " session-row--blocked" : ""
                  }`}
                  onClick={() => {
                    if (blocked) return;
                    onSelectSession(s.id);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      if (!blocked) onSelectSession(s.id);
                    }
                  }}
                  role="button"
                  tabIndex={0}
                  aria-current={active ? "true" : undefined}
                >
                  <div className="session-row-main">
                    <span className="session-title">{s.title}</span>
                    <span className="session-time">{formatRelativeTime(s.updated_at)}</span>
                  </div>
                  <button
                    type="button"
                    className="session-delete"
                    title="删除对话"
                    disabled={sending || !runtimeReady}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (sending || !runtimeReady) return;
                      if (window.confirm(`删除对话「${s.title}」？此操作无法恢复。`)) {
                        onDeleteSession(s.id);
                      }
                    }}
                  >
                    删除
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="session-workspace-bar">
        <div className="session-workspace-label">当前文件夹</div>
        {workspacePath ? (
          <div className="session-workspace-path" title={workspacePath}>
            {basename(workspacePath)}
          </div>
        ) : (
          <div className="session-workspace-path session-workspace-path--empty">未打开</div>
        )}
        {workspaceError && <div className="session-workspace-error">{workspaceError}</div>}
        <button
          type="button"
          className="btn btn--full btn--ghost"
          disabled={!runtimeReady}
          onClick={onPickWorkspace}
        >
          {workspacePath ? "更换文件夹" : "打开文件夹"}
        </button>
      </div>
    </section>
  );
}
