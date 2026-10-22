import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import "./styles/theme.css";
import "./styles/scrollbar.css";
import "./App.css";
import { installWindowsScrollbars } from "./lib/windowsScrollbar";
import { APP_NAME, APP_TAGLINE } from "./lib/brand";
import { dismissBootSplash, shouldDismissBootSplash } from "./lib/bootSplash";
import {
  bootPollInterval,
  shouldEmitHealthFail,
  shouldMarkDownDuringBoot,
} from "./lib/bootHealth";
import { isModelSetupError, MODEL_SETUP_REPLY, needsModelSetup } from "./lib/guide";
import { runtimeClient, RuntimeClientError, setRuntimeApiToken, type ChatStreamHandle } from "./lib/runtimeClient";
import {
  deriveRuntimeStatus,
  runtimeStatusLabel,
  type HealthState,
} from "./lib/runtimeStatus";
import {
  SKILLS_REFRESH_INTERVAL_MS,
  shouldRetrySkillsRefresh,
} from "./lib/skillsRefresh";
import { sessionMessagesToChat } from "./lib/sessionMessages";
import {
  normalizeWorkspaceKey,
  pathsEqual,
  pickRestoreWorkspace,
  pickSessionInWorkspace,
  readSidebarMemory,
  visibleWorkspaceGroups,
  withArchivedFolder,
  withRememberedSession,
  withToggledCollapse,
  writeSidebarMemory,
  type SidebarMemory,
} from "./lib/workspaceSidebar";
import { getRuntimeToken, isTauriRuntime, logDesktopEvent, pickFolder } from "./lib/tauri";
import { initUiPreferences } from "./lib/uiPreferences";
import type {
  ChatMessage,
  LiveStep,
  PermissionRequestEvent,
  RuntimeConfig,
  SessionMeta,
  SkillInspectResult,
  SkillMeta,
} from "./lib/types";
import { SettingsIcon, SkillsIcon } from "./components/icons";
import SessionList from "./components/SessionList";
import ChatPanel from "./components/ChatPanel";
import SkillManager from "./components/SkillManager";
import SettingsModal, { type SettingsTab } from "./components/SettingsModal";
import PermissionModal from "./components/PermissionModal";

const DEFAULT_CONFIG: RuntimeConfig = {
  api_base: "https://api.deepseek.com",
  api_key: "",
  model: "deepseek-v4-flash",
  allowed_hosts: ["api.deepseek.com", "127.0.0.1", "localhost"],
  permission_mode: "standard",
  deployment_profile: "standard",
  allow_workspace_scripts: false,
};

let messageSeq = 0;
function nextId(): string {
  messageSeq += 1;
  return `m${messageSeq}`;
}

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [configReady, setConfigReady] = useState(false);
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [sidebarMemory, setSidebarMemory] = useState<SidebarMemory>(() => readSidebarMemory());
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsTab, setSettingsTab] = useState<SettingsTab | undefined>(undefined);
  const [skillManagerOpen, setSkillManagerOpen] = useState(false);
  const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequestEvent | null>(null);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const healthFailCount = useRef(0);
  const healthRef = useRef<HealthState>(health);
  const sendingRef = useRef(false);
  const streamHandleRef = useRef<ChatStreamHandle | null>(null);
  const messagesRef = useRef(messages);
  const workspacePathRef = useRef(workspacePath);
  const bootRestoreStarted = useRef(false);
  sessionIdRef.current = sessionId;
  healthRef.current = health;
  sendingRef.current = sending;
  messagesRef.current = messages;
  workspacePathRef.current = workspacePath;

  const commitMemory = useCallback((recipe: (prev: SidebarMemory) => SidebarMemory) => {
    setSidebarMemory((prev) => {
      const next = recipe(prev);
      writeSidebarMemory(next);
      return next;
    });
  }, []);

  useEffect(() => {
    initUiPreferences();
  }, []);

  useEffect(() => installWindowsScrollbars(), []);

  useEffect(() => {
    if (!isTauriRuntime() || shouldDismissBootSplash(health)) {
      dismissBootSplash();
    }
  }, [health]);

  useEffect(() => {
    const bootStartedAt = Date.now();
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    const scheduleNext = () => {
      const delay = bootPollInterval(Date.now() - bootStartedAt);
      timer = setTimeout(() => void runCheck(), delay);
    };

    const runCheck = async () => {
      if (cancelled) return;
      if (!sendingRef.current) {
        try {
          await runtimeClient.health();
          healthFailCount.current = 0;
          setHealth("ok");
        } catch {
          healthFailCount.current += 1;
          const elapsed = Date.now() - bootStartedAt;
          // Boot window: stay "checking". After timeout: down on consecutive failures (≥2).
          // Emit health_fail only on transition into down (once per down episode).
          if (
            shouldMarkDownDuringBoot(elapsed, false) &&
            healthFailCount.current >= 2 &&
            shouldEmitHealthFail(healthRef.current)
          ) {
            void logDesktopEvent("health_fail");
            healthRef.current = "down";
            setHealth("down");
          }
        }
      }
      if (!cancelled) scheduleNext();
    };

    void (async () => {
      if (isTauriRuntime()) {
        try {
          const token = await getRuntimeToken();
          if (token) setRuntimeApiToken(token);
        } catch {
          // keep unset — dev runtime may run without token
        }
      }
      await runCheck();
    })();

    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  useEffect(() => {
    if (health !== "ok") {
      setConfigReady(false);
      return;
    }
    void (async () => {
      try {
        const cfg = await runtimeClient.getConfig();
        setConfig({
          api_base: cfg.api_base,
          api_key: "",
          api_key_masked: cfg.api_key_masked,
          api_key_set: cfg.api_key_set,
          model: cfg.model,
          allowed_hosts: cfg.allowed_hosts,
          permission_mode: cfg.permission_mode ?? "standard",
          deployment_profile: cfg.deployment_profile ?? "standard",
          allow_workspace_scripts: Boolean(cfg.allow_workspace_scripts),
          require_script_sandbox: Boolean(cfg.require_script_sandbox),
        });
      } catch {
        // keep defaults — still mark ready so UI can show「待配置」
      } finally {
        setConfigReady(true);
      }
    })();
  }, [health]);

  const refreshSkills = useCallback(async (): Promise<number> => {
    try {
      const { skills: list } = await runtimeClient.listSkills();
      setSkills(list);
      return list.length;
    } catch {
      return 0;
    }
  }, []);

  // Health can precede async bundled skill seed — retry briefly until skills appear.
  useEffect(() => {
    if (health !== "ok") return;
    let cancelled = false;
    const started = Date.now();

    void (async () => {
      while (!cancelled) {
        const count = await refreshSkills();
        if (cancelled) return;
        const elapsed = Date.now() - started;
        if (!shouldRetrySkillsRefresh(elapsed, count)) return;
        await new Promise((r) => setTimeout(r, SKILLS_REFRESH_INTERVAL_MS));
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [health, refreshSkills]);

  const refreshSessions = useCallback(async () => {
    try {
      const { sessions: list } = await runtimeClient.listAllSessions();
      setSessions(list);
      return list;
    } catch {
      setSessions([]);
      return [];
    }
  }, []);

  const loadSessionMessages = useCallback(async (id: string) => {
    const res = await runtimeClient.getSessionMessages(id);
    setMessages(sessionMessagesToChat(res.messages, nextId));
  }, []);

  const runtimeReady = health === "ok";
  const status = deriveRuntimeStatus(health, {
    configReady,
    needsConfig: needsModelSetup(config),
  });

  const rememberOpen = useCallback(
    (path: string, sessionIdToRemember: string) => {
      commitMemory((prev) => withRememberedSession(prev, path, sessionIdToRemember));
    },
    [commitMemory],
  );

  const openWorkspaceSession = useCallback(
    async (
      path: string,
      preferredSessionId: string | null,
      options?: { keepOnboardingMessages?: boolean },
    ) => {
      if (!runtimeReady) {
        setWorkspaceError("本地服务未就绪，请关闭后重新打开本应用。");
        return;
      }
      if (sendingRef.current) return;
      setWorkspaceError(null);
      try {
        const res = await runtimeClient.openWorkspace(path);
        const list = await refreshSessions();
        const memory = readSidebarMemory();
        const preferred =
          preferredSessionId ??
          memory.lastSessionByWorkspace[normalizeWorkspaceKey(res.path)] ??
          null;
        const existing = pickSessionInWorkspace(list, res.path, preferred);
        const keepOnboarding =
          Boolean(options?.keepOnboardingMessages) &&
          messagesRef.current.length > 0 &&
          !workspacePathRef.current;
        setWorkspacePath(res.path);

        if (!existing && keepOnboarding) {
          const created = await runtimeClient.createSession(res.path);
          setSessionId(created.session.id);
          rememberOpen(res.path, created.session.id);
          await refreshSessions();
          return;
        }

        if (!existing) {
          const created = await runtimeClient.createSession(res.path);
          setSessionId(created.session.id);
          setMessages([]);
          rememberOpen(res.path, created.session.id);
          await refreshSessions();
          return;
        }

        setSessionId(existing.id);
        setMessages([]);
        rememberOpen(existing.workspace_path || res.path, existing.id);
        try {
          await loadSessionMessages(existing.id);
        } catch (err) {
          setMessages([
            {
              id: nextId(),
              role: "error",
              content: err instanceof RuntimeClientError ? err.message : "加载对话失败",
            },
          ]);
        }
      } catch (err) {
        setWorkspaceError(err instanceof RuntimeClientError ? err.message : "打开文件夹失败");
      }
    },
    [runtimeReady, refreshSessions, loadSessionMessages, rememberOpen],
  );

  const openWorkspaceSessionRef = useRef(openWorkspaceSession);
  openWorkspaceSessionRef.current = openWorkspaceSession;

  useEffect(() => {
    if (health !== "ok" || bootRestoreStarted.current) return;
    bootRestoreStarted.current = true;
    void (async () => {
      const list = await refreshSessions();
      if (workspacePathRef.current) return;
      const saved = readSidebarMemory();
      const groups = visibleWorkspaceGroups(list, saved.archived);
      const path = pickRestoreWorkspace(groups, saved);
      if (!path || workspacePathRef.current) return;
      const preferred = saved.lastSessionByWorkspace[normalizeWorkspaceKey(path)] ?? null;
      await openWorkspaceSessionRef.current(path, preferred);
    })();
  }, [health, refreshSessions]);

  const handleOpenPath = useCallback(
    async (path: string) => {
      await openWorkspaceSession(path, null, {
        keepOnboardingMessages: messagesRef.current.length > 0,
      });
    },
    [openWorkspaceSession],
  );

  const handlePickFolder = useCallback(async () => {
    const path = await pickFolder();
    if (path) await handleOpenPath(path);
  }, [handleOpenPath]);

  const handleNewSession = useCallback(async () => {
    if (!workspacePath || sending || !runtimeReady) return;
    try {
      const created = await runtimeClient.createSession(workspacePath);
      setSessionId(created.session.id);
      setMessages([]);
      rememberOpen(workspacePath, created.session.id);
      await refreshSessions();
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          id: nextId(),
          role: "error",
          content: err instanceof RuntimeClientError ? err.message : "新建会话失败",
        },
      ]);
    }
  }, [workspacePath, sending, runtimeReady, refreshSessions, rememberOpen]);

  const handleSelectSession = useCallback(
    async (session: SessionMeta) => {
      if (sending && session.id !== sessionIdRef.current) return;
      if (
        session.id === sessionIdRef.current &&
        pathsEqual(session.workspace_path, workspacePathRef.current)
      ) {
        return;
      }
      if (
        session.workspace_path &&
        !pathsEqual(session.workspace_path, workspacePathRef.current)
      ) {
        await openWorkspaceSession(session.workspace_path, session.id);
        return;
      }
      setSessionId(session.id);
      if (session.workspace_path) rememberOpen(session.workspace_path, session.id);
      try {
        await loadSessionMessages(session.id);
      } catch (err) {
        setMessages([
          {
            id: nextId(),
            role: "error",
            content: err instanceof RuntimeClientError ? err.message : "加载对话失败",
          },
        ]);
      }
    },
    [sending, loadSessionMessages, openWorkspaceSession, rememberOpen],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      if (sending || !runtimeReady) return;
      const target = sessions.find((s) => s.id === id);
      try {
        await runtimeClient.deleteSession(id);
        const list = await refreshSessions();
        if (id !== sessionIdRef.current) return;
        const next = target ? pickSessionInWorkspace(list, target.workspace_path, null) : null;
        if (next) {
          setSessionId(next.id);
          rememberOpen(next.workspace_path, next.id);
          await loadSessionMessages(next.id);
          return;
        }
        if (workspacePath && target && pathsEqual(target.workspace_path, workspacePath)) {
          const created = await runtimeClient.createSession(workspacePath);
          setSessionId(created.session.id);
          setMessages([]);
          rememberOpen(workspacePath, created.session.id);
          await refreshSessions();
          return;
        }
        setSessionId(undefined);
        setMessages([]);
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "error",
            content: err instanceof RuntimeClientError ? err.message : "删除会话失败",
          },
        ]);
      }
    },
    [sending, runtimeReady, sessions, workspacePath, refreshSessions, loadSessionMessages, rememberOpen],
  );

  const handleToggleWorkspace = useCallback(
    (path: string) => {
      commitMemory((prev) => withToggledCollapse(prev, path));
    },
    [commitMemory],
  );

  const handleArchiveWorkspace = useCallback(
    (path: string) => {
      commitMemory((prev) => withArchivedFolder(prev, path));
    },
    [commitMemory],
  );

  const workspaceGroups = useMemo(
    () => visibleWorkspaceGroups(sessions, sidebarMemory.archived),
    [sessions, sidebarMemory.archived],
  );
  const collapsedPaths = useMemo(
    () => new Set(sidebarMemory.collapsed),
    [sidebarMemory.collapsed],
  );

  const handleRenameSession = useCallback(
    async (id: string, title: string) => {
      if (sending || !runtimeReady) return;
      try {
        const { session } = await runtimeClient.renameSession(id, title);
        setSessions((prev) =>
          prev.map((s) => (s.id === id ? { ...s, ...session } : s)),
        );
      } catch (err) {
        setMessages((prev) => [
          ...prev,
          {
            id: nextId(),
            role: "error",
            content: err instanceof RuntimeClientError ? err.message : "重命名失败",
          },
        ]);
      }
    },
    [sending, runtimeReady],
  );

  const handleSend = useCallback(
    async (text: string, attachedPaths: string[] = []) => {
      if (!runtimeReady) return;

      const userMsg: ChatMessage = { id: nextId(), role: "user", content: text };
      const assistantId = nextId();

      // 未配模型：直接展示固定引导。本地档有地址即可，不必有 Key。
      if (needsModelSetup(config)) {
        setMessages((prev) => [
          ...prev,
          userMsg,
          { id: assistantId, role: "assistant", content: MODEL_SETUP_REPLY, phase: "done" },
        ]);
        return;
      }

      // 无文件夹时勿 POST /sessions（仍 require_workspace）；省略 session_id，
      // 由 Runtime _prepare_chat → create_session("")，再在 onStarted/onFinal 写入。
      let activeId = sessionIdRef.current;
      if (!activeId && workspacePath) {
        const created = await runtimeClient.createSession(workspacePath);
        activeId = created.session.id;
        setSessionId(activeId);
        rememberOpen(workspacePath, activeId);
        void refreshSessions();
      }

      const pendingMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        phase: "pending",
        startedAt: Date.now(),
        liveSteps: [],
        stepsExpanded: false,
      };
      setMessages((prev) => [...prev, userMsg, pendingMsg]);
      setSending(true);

      const patchAssistant = (updater: (m: ChatMessage) => ChatMessage) => {
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? updater(m) : m)));
      };

      try {
        const stream = runtimeClient.chatStream(
          {
            message: text,
            attached_paths: attachedPaths.length > 0 ? attachedPaths : undefined,
            session_id: activeId,
          },
          {
            onStarted: (sid, turnId) => {
              if (sid) {
                setSessionId(sid);
                if (workspacePath) rememberOpen(workspacePath, sid);
              }
              if (turnId) {
                patchAssistant((m) => ({ ...m, turnId }));
              }
            },
            onStatus: (phase) => {
              patchAssistant((m) => ({
                ...m,
                phase: m.phase === "pending" ? "live" : m.phase,
                statusPhase:
                  phase === "planning" || phase === "tools" || phase === "finishing"
                    ? phase
                    : m.statusPhase,
              }));
            },
            onToolStart: (ev) => {
              patchAssistant((m) => {
                const steps = [...(m.liveSteps ?? [])];
                const idx = steps.findIndex((s) => s.id === ev.id);
                const next: LiveStep = {
                  id: ev.id || `t${steps.length + 1}`,
                  name: ev.name,
                  label: ev.label || ev.name,
                  status: "running",
                  summary: ev.args_summary,
                };
                if (idx >= 0) steps[idx] = { ...steps[idx], ...next };
                else steps.push(next);
                return { ...m, phase: "live", statusPhase: "tools", liveSteps: steps };
              });
            },
            onToolDone: (ev) => {
              patchAssistant((m) => {
                const steps = [...(m.liveSteps ?? [])];
                const idx = steps.findIndex((s) => s.id === ev.id);
                const done: LiveStep = {
                  id: ev.id || `t${steps.length + 1}`,
                  name: ev.name,
                  label: ev.label || ev.name,
                  status: ev.ok ? "ok" : "fail",
                  summary: ev.summary,
                };
                if (idx >= 0) steps[idx] = { ...steps[idx], ...done };
                else steps.push(done);
                return { ...m, phase: "live", liveSteps: steps };
              });
            },
            onPermissionRequest: (ev) => {
              setPermissionRequest(ev);
            },
            onFinal: (res) => {
              setPermissionRequest(null);
              if (res.session_id) setSessionId(res.session_id);
              patchAssistant((m) => ({
                ...m,
                phase: "done",
                content: res.reply,
                toolEvents: res.tool_events,
                stepsExpanded: false,
                statusPhase: "finishing",
              }));
              void refreshSessions();
            },
            onMemoryUpdated: (ev) => {
              patchAssistant((m) => ({
                ...m,
                memoryNote: ev,
              }));
              if (ev.skill_id) {
                void refreshSkills();
              }
            },
            onError: (message) => {
              setPermissionRequest(null);
              if (isModelSetupError(message)) {
                patchAssistant(() => ({
                  id: assistantId,
                  role: "assistant",
                  content: MODEL_SETUP_REPLY,
                  phase: "done",
                }));
                return;
              }
              patchAssistant(() => ({
                id: assistantId,
                role: "error",
                content: message,
              }));
            },
          },
        );
        streamHandleRef.current = stream;
        await stream.done;
      } finally {
        streamHandleRef.current = null;
        setSending(false);
      }
    },
    [workspacePath, runtimeReady, refreshSessions, refreshSkills, config, rememberOpen],
  );

  const handleStop = useCallback(async () => {
    const sid = sessionIdRef.current;
    streamHandleRef.current?.abort();
    if (!sid) return;
    try {
      await runtimeClient.cancelChat(sid);
    } catch {
      // Stream abort already stops the UI; ignore 404 when turn already ended.
    }
  }, []);

  const handleToggleSteps = useCallback((messageId: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === messageId ? { ...m, stepsExpanded: !m.stepsExpanded } : m)),
    );
  }, []);

  const handleToggleSkill = useCallback(async (id: string, enabled: boolean) => {
    try {
      await runtimeClient.setEnabled(id, enabled);
    } finally {
      await refreshSkills();
    }
  }, [refreshSkills]);

  const handleInspectSkill = useCallback(async (path: string): Promise<SkillInspectResult> => {
    return runtimeClient.inspectSkill(path);
  }, []);

  const handleConfirmInstallSkill = useCallback(
    async (path: string, enabled: boolean, applyFixes = false, forceOverwrite = false) => {
      await runtimeClient.installSkillWithOptions(path, enabled, applyFixes, forceOverwrite);
      await refreshSkills();
    },
    [refreshSkills],
  );

  const handleUninstallSkill = useCallback(
    async (id: string) => {
      await runtimeClient.uninstallSkill(id);
      await refreshSkills();
    },
    [refreshSkills],
  );

  const handleRestoreBundledSkill = useCallback(
    async (id: string) => {
      await runtimeClient.restoreBundledSkill(id);
      await refreshSkills();
    },
    [refreshSkills],
  );

  const handleSaveConfig = useCallback(async (partial: Partial<RuntimeConfig>) => {
    // Omit undefined fields; do not send api_key: null (JSON.stringify drops undefined).
    await runtimeClient.saveConfig(partial);
    setConfig((prev) => {
      const next: RuntimeConfig = {
        ...prev,
        ...partial,
        api_key: "",
      };
      if (partial.api_key !== undefined) {
        next.api_key_set = Boolean(partial.api_key);
        if (partial.api_key) {
          const key = partial.api_key;
          next.api_key_masked =
            key.length > 12 ? `${key.slice(0, 6)}…${key.slice(-4)}` : "***";
        } else {
          next.api_key_masked = "";
        }
      }
      return next;
    });
    setSettingsOpen(false);
    setSettingsTab(undefined);
  }, []);

  const openSettings = useCallback((tab?: SettingsTab) => {
    setSettingsTab(tab);
    setSettingsOpen(true);
  }, []);

  const handlePermissionResolve = useCallback(async (allow: boolean) => {
    if (!permissionRequest) return;
    setPermissionBusy(true);
    try {
      await runtimeClient.resolvePermission(permissionRequest.id, allow);
      setPermissionRequest(null);
    } catch (err) {
      const message = err instanceof Error ? err.message : "权限确认失败";
      setMessages((prev) => [
        ...prev,
        { id: nextId(), role: "error", content: message },
      ]);
    } finally {
      setPermissionBusy(false);
    }
  }, [permissionRequest]);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <img
            className="topbar-logo"
            src="/logo-mark.png"
            width={28}
            height={28}
            alt=""
            aria-hidden="true"
          />
          <div className="topbar-brand-text">
            <span className="topbar-title">{APP_NAME}</span>
            <span className="topbar-tagline">{APP_TAGLINE}</span>
          </div>
        </div>
        <div className="topbar-actions">
          <button
            type="button"
            className={`health-status health-status--${status}`}
            onClick={() => {
              if (status === "needs_config") openSettings("model");
            }}
            title={
              status === "needs_config" ? "请先在设置中填写模型密钥" : undefined
            }
            disabled={status !== "needs_config"}
          >
            <span className={`health-dot health-dot--${status}`} aria-hidden="true" />
            <span className="health-label">{runtimeStatusLabel(status)}</span>
          </button>
          <div className="topbar-tools">
            <button
              type="button"
              className="btn btn--ghost btn--icon"
              onClick={() => setSkillManagerOpen(true)}
              aria-label="技能管理"
              title="技能管理"
              aria-haspopup="dialog"
              aria-expanded={skillManagerOpen}
            >
              <SkillsIcon />
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--icon"
              onClick={() => openSettings()}
              aria-label="设置"
              title="设置"
              aria-haspopup="dialog"
              aria-expanded={settingsOpen}
            >
              <SettingsIcon />
            </button>
          </div>
        </div>
      </header>

      <div className="workbench">
        <SessionList
          groups={workspaceGroups}
          collapsedPaths={collapsedPaths}
          workspacePath={workspacePath}
          workspaceError={workspaceError}
          activeSessionId={sessionId}
          sending={sending}
          runtimeReady={runtimeReady}
          onPickWorkspace={handlePickFolder}
          onOpenWorkspace={(path) => void openWorkspaceSession(path, null)}
          onToggleWorkspace={handleToggleWorkspace}
          onArchiveWorkspace={handleArchiveWorkspace}
          onNewSession={() => void handleNewSession()}
          onSelectSession={(session) => void handleSelectSession(session)}
          onDeleteSession={(id) => void handleDeleteSession(id)}
          onRenameSession={(id, title) => void handleRenameSession(id, title)}
        />

        <ChatPanel
          workspaceOpen={workspacePath !== null}
          workspacePath={workspacePath}
          messages={messages}
          sending={sending}
          runtimeReady={runtimeReady}
          onSend={handleSend}
          onStop={() => void handleStop()}
          onToggleSteps={handleToggleSteps}
          onOpenMemory={() => openSettings("memory")}
        />
      </div>

      <SkillManager
        open={skillManagerOpen}
        skills={skills}
        onClose={() => setSkillManagerOpen(false)}
        onToggle={handleToggleSkill}
        onInspect={handleInspectSkill}
        onConfirmInstall={handleConfirmInstallSkill}
        onUninstall={handleUninstallSkill}
        onRestoreBundled={handleRestoreBundledSkill}
        onRefresh={refreshSkills}
      />

      <SettingsModal
        open={settingsOpen}
        initial={config}
        initialTab={settingsTab}
        onClose={() => {
          setSettingsOpen(false);
          setSettingsTab(undefined);
        }}
        onSave={handleSaveConfig}
        memory={{
          load: () => runtimeClient.getMemory(),
          save: (body) => runtimeClient.putMemory(body),
          onOpenSkills: () => {
            setSettingsOpen(false);
            setSettingsTab(undefined);
            setSkillManagerOpen(true);
          },
        }}
      />

      <PermissionModal
        request={permissionRequest}
        busy={permissionBusy}
        onAllow={() => void handlePermissionResolve(true)}
        onDeny={() => void handlePermissionResolve(false)}
      />
    </div>
  );
}

export default App;
