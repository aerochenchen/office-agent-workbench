import { useEffect, useRef, useState } from "react";
import type { SessionMeta } from "../lib/types";
import { GUIDE_HINTS } from "../lib/guide";
import { normalizeSessionTitle } from "../lib/sessionTitle";
import { normalizeWorkspaceKey, pathsEqual, type WorkspaceGroup } from "../lib/workspaceSidebar";
import { FolderIcon, NewChatIcon } from "./icons";
import "./SessionList.css";

interface Props {
  groups: WorkspaceGroup[];
  collapsedPaths: ReadonlySet<string>;
  workspacePath: string | null;
  workspaceError: string | null;
  activeSessionId: string | undefined;
  sending: boolean;
  runtimeReady: boolean;
  onPickWorkspace: () => void;
  onOpenWorkspace: (path: string) => void;
  onToggleWorkspace: (path: string) => void;
  onArchiveWorkspace: (path: string) => void;
  onNewSession: () => void;
  onSelectSession: (session: SessionMeta) => void;
  onDeleteSession: (id: string) => void;
  onRenameSession: (id: string, title: string) => void | Promise<void>;
}

type MenuState =
  | { kind: "session"; sessionId: string; x: number; y: number }
  | { kind: "folder"; path: string; name: string; x: number; y: number };

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

export default function SessionList({
  groups,
  collapsedPaths,
  workspacePath,
  workspaceError,
  activeSessionId,
  sending,
  runtimeReady,
  onPickWorkspace,
  onOpenWorkspace,
  onToggleWorkspace,
  onArchiveWorkspace,
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
  const sessions = groups.flatMap((g) => g.sessions);
  const newSessionDisabled = !workspacePath || sending || !runtimeReady;
  const newSessionTitle = !workspacePath
    ? GUIDE_HINTS.newSessionNeedsFolder
    : sending
      ? "请等待当前回复结束"
      : "在当前文件夹新建对话";

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
    <section className="pane session-pane" aria-label="文件夹">
      <div className="session-toolbar">
        <div className="session-toolbar-row">
          <button
            type="button"
            className="session-tool session-tool--primary"
            disabled={!runtimeReady || sending}
            onClick={onPickWorkspace}
          >
            <span className="session-tool-icon">
              <FolderIcon size={17} />
            </span>
            打开文件夹
          </button>
          <button
            type="button"
            className="session-tool session-tool--secondary"
            aria-disabled={newSessionDisabled || undefined}
            title={newSessionTitle}
            onClick={() => {
              if (newSessionDisabled) return;
              onNewSession();
            }}
          >
            <span className="session-tool-icon">
              <NewChatIcon size={17} />
            </span>
            新建对话
          </button>
        </div>
        {workspaceError && <div className="session-workspace-error">{workspaceError}</div>}
      </div>

      <div className="pane-body session-list-body">
        {groups.map((group) => {
          const current = pathsEqual(group.path, workspacePath);
          const collapsed = collapsedPaths.has(normalizeWorkspaceKey(group.path));
          const switchBlocked = sending && !current;
          const selectedHere =
            current && group.sessions.some((session) => session.id === activeSessionId);
          return (
            <div
              key={group.path}
              className={`workspace-group${current && !selectedHere ? " workspace-group--current" : ""}`}
            >
              <div
                className="workspace-head"
                onContextMenu={(e) => {
                  e.preventDefault();
                  setMenu({ kind: "folder", path: group.path, name: group.name, x: e.clientX, y: e.clientY });
                }}
              >
                <button
                  type="button"
                  className={`workspace-chevron${collapsed ? "" : " workspace-chevron--open"}`}
                  aria-expanded={!collapsed}
                  aria-label={collapsed ? `展开 ${group.name}` : `收起 ${group.name}`}
                  onClick={() => onToggleWorkspace(group.path)}
                >
                  <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">
                    <path
                      d="M6 4l4 4-4 4"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="1.4"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    />
                  </svg>
                </button>
                <button
                  type="button"
                  className="workspace-open"
                  title={group.path}
                  disabled={switchBlocked}
                  onClick={() => {
                    if (switchBlocked) return;
                    if (current) onToggleWorkspace(group.path);
                    else onOpenWorkspace(group.path);
                  }}
                >
                  <span className="workspace-open-icon">
                    <FolderIcon />
                  </span>
                  <span className="workspace-open-name">{group.name}</span>
                </button>
              </div>
              {!collapsed && (
                <ul className="session-list workspace-sessions">
                  {group.sessions.map((s) => {
                    const active = s.id === activeSessionId && current;
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
                            onSelectSession(s);
                          }}
                          onContextMenu={(e) => {
                            e.preventDefault();
                            if (renamingId && renamingId !== s.id) {
                              cancelRename();
                            }
                            setMenu({ kind: "session", sessionId: s.id, x: e.clientX, y: e.clientY });
                          }}
                          onKeyDown={(e) => {
                            if (renaming) return;
                            if (e.key === "Enter" || e.key === " ") {
                              e.preventDefault();
                              if (!blocked) onSelectSession(s);
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
              )}
            </div>
          );
        })}
      </div>

      {menu && (
        <div
          ref={menuRef}
          className="session-context-menu"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
        >
          {menu.kind === "folder" ? (
            <button
              type="button"
              className="session-context-item"
              role="menuitem"
              title="从左侧隐藏。对话仍保留，再次打开此文件夹后会重新出现。"
              onClick={() => {
                const path = menu.path;
                setMenu(null);
                onArchiveWorkspace(path);
              }}
            >
              归档
            </button>
          ) : (() => {
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
    </section>
  );
}
