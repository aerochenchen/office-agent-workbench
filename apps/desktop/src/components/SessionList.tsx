import { useEffect, useRef, useState } from "react";
import type { SessionMeta } from "../lib/types";
import { GUIDE_HINTS } from "../lib/guide";
import { normalizeSessionTitle } from "../lib/sessionTitle";
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
  onRenameSession: (id: string, title: string) => void | Promise<void>;
}

type MenuState = {
  sessionId: string;
  x: number;
  y: number;
};

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
  onRenameSession,
}: Props) {
  const [menu, setMenu] = useState<MenuState | null>(null);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const renameCommitLock = useRef(false);
  const menuDisabled = sending || !runtimeReady;

  useEffect(() => {
    if (!renamingId) return;
    renameCommitLock.current = false;
    const el = renameInputRef.current;
    if (!el) return;
    el.focus();
    el.select();
  }, [renamingId]);

  useEffect(() => {
    if (!menu) return;
    const onPointer = (e: MouseEvent) => {
      if (menuRef.current?.contains(e.target as Node)) return;
      setMenu(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenu(null);
    };
    window.addEventListener("mousedown", onPointer);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onPointer);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  function startRename(session: SessionMeta) {
    if (menuDisabled) return;
    setMenu(null);
    setRenamingId(session.id);
    setDraft(session.title);
  }

  function cancelRename() {
    setRenamingId(null);
    setDraft("");
  }

  async function commitRename(session: SessionMeta) {
    if (renamingId !== session.id) return;
    if (renameCommitLock.current) return;
    renameCommitLock.current = true;
    const next = normalizeSessionTitle(draft);
    cancelRename();
    if (next === session.title) return;
    await onRenameSession(session.id, next);
  }

  return (
    <section className="pane session-pane">
      <div className="pane-header">
        <span className="pane-title">对话</span>
      </div>

      <div className="session-toolbar">
        <button
          type="button"
          className="btn btn--pane btn--full"
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
        {workspacePath && sessions.length === 0 && (
          <div className="empty-hint">{GUIDE_HINTS.noSessions}</div>
        )}
        <ul className="session-list">
          {sessions.map((s) => {
            const active = s.id === activeSessionId;
            const blocked = sending && s.id !== activeSessionId;
            const renaming = renamingId === s.id;
            return (
              <li key={s.id}>
                <div
                  className={`session-row${active ? " session-row--active" : ""}${
                    blocked ? " session-row--blocked" : ""
                  }${renaming ? " session-row--renaming" : ""}`}
                  onClick={() => {
                    if (blocked || renaming) return;
                    onSelectSession(s.id);
                  }}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    if (renamingId && renamingId !== s.id) {
                      cancelRename();
                    }
                    setMenu({ sessionId: s.id, x: e.clientX, y: e.clientY });
                  }}
                  onKeyDown={(e) => {
                    if (renaming) return;
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
                    {renaming ? (
                      <input
                        ref={renameInputRef}
                        className="session-rename-input"
                        value={draft}
                        aria-label="重命名对话"
                        onChange={(e) => setDraft(e.currentTarget.value)}
                        onClick={(e) => e.stopPropagation()}
                        onKeyDown={(e) => {
                          e.stopPropagation();
                          if (e.key === "Enter") {
                            e.preventDefault();
                            void commitRename(s);
                          } else if (e.key === "Escape") {
                            e.preventDefault();
                            cancelRename();
                          }
                        }}
                        onBlur={() => void commitRename(s)}
                      />
                    ) : (
                      <span className="session-title">{s.title}</span>
                    )}
                    <span className="session-time">{formatRelativeTime(s.updated_at)}</span>
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {menu && (
        <div
          ref={menuRef}
          className="session-context-menu"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
        >
          {(() => {
            const target = sessions.find((s) => s.id === menu.sessionId);
            if (!target) return null;
            return (
              <>
                <button
                  type="button"
                  className="session-context-item"
                  role="menuitem"
                  disabled={menuDisabled}
                  onClick={() => startRename(target)}
                >
                  重命名
                </button>
                <button
                  type="button"
                  className="session-context-item session-context-item--danger"
                  role="menuitem"
                  disabled={menuDisabled}
                  onClick={() => {
                    setMenu(null);
                    if (menuDisabled) return;
                    if (window.confirm(`删除对话「${target.title}」？此操作无法恢复。`)) {
                      onDeleteSession(target.id);
                    }
                  }}
                >
                  删除
                </button>
              </>
            );
          })()}
        </div>
      )}

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
          className="btn btn--pane btn--pane-accent btn--full"
          disabled={!runtimeReady}
          onClick={onPickWorkspace}
        >
          {workspacePath ? "更换文件夹" : "打开文件夹"}
        </button>
      </div>
    </section>
  );
}
