import { useCallback, useEffect, useRef, useState } from "react";
import "./styles/theme.css";
import "./App.css";
import { APP_NAME, APP_TAGLINE } from "./lib/brand";
import { runtimeClient, RuntimeClientError, type ChatStreamHandle } from "./lib/runtimeClient";
import { isTauriRuntime, pickFolder } from "./lib/tauri";
import type {
  ChatMessage,
  LiveStep,
  PermissionRequestEvent,
  RuntimeConfig,
  SessionMeta,
  SkillInspect,
  SkillMeta,
} from "./lib/types";
import SessionList from "./components/SessionList";
import ChatPanel from "./components/ChatPanel";
import SkillPanel from "./components/SkillPanel";
import SettingsModal from "./components/SettingsModal";
import PermissionModal from "./components/PermissionModal";

type HealthState = "checking" | "ok" | "down";

const DEFAULT_CONFIG: RuntimeConfig = {
  api_base: "https://api.deepseek.com/v1",
  api_key: "",
  model: "deepseek-v4-flash",
  allowed_hosts: ["api.deepseek.com", "127.0.0.1", "localhost"],
  permission_mode: "standard",
};

let messageSeq = 0;
function nextId(): string {
  messageSeq += 1;
  return `m${messageSeq}`;
}

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [skillsCollapsed, setSkillsCollapsed] = useState(false);
  const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequestEvent | null>(null);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const healthFailCount = useRef(0);
  const sendingRef = useRef(false);
  const streamHandleRef = useRef<ChatStreamHandle | null>(null);
  sessionIdRef.current = sessionId;
  sendingRef.current = sending;

  const checkHealth = useCallback(async () => {
    if (sendingRef.current) return;
    try {
      await runtimeClient.health();
      healthFailCount.current = 0;
      setHealth("ok");
    } catch {
      healthFailCount.current += 1;
      if (healthFailCount.current >= 2) setHealth("down");
    }
  }, []);

  useEffect(() => {
    void checkHealth();
    const timer = window.setInterval(() => void checkHealth(), 8_000);
    return () => window.clearInterval(timer);
  }, [checkHealth]);

  useEffect(() => {
    if (health !== "ok") return;
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
        });
      } catch {
        // keep defaults
      }
    })();
  }, [health]);

  const refreshSkills = useCallback(async () => {
    try {
      const { skills: list } = await runtimeClient.listSkills();
      setSkills(list);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    void refreshSkills();
  }, [refreshSkills]);

  const refreshSessions = useCallback(async (wsPath?: string | null) => {
    const path = wsPath ?? workspacePath;
    if (!path) {
      setSessions([]);
      return [];
    }
    try {
      const { sessions: list } = await runtimeClient.listSessions(path);
      setSessions(list);
      return list;
    } catch {
      setSessions([]);
      return [];
    }
  }, [workspacePath]);

  const loadSessionMessages = useCallback(async (id: string) => {
    const res = await runtimeClient.getSessionMessages(id);
    setMessages(
      res.messages.map((m) => ({
        id: nextId(),
        role: m.role,
        content: m.content,
        phase: "done" as const,
      })),
    );
  }, []);

  const runtimeReady = health === "ok";

  const handleOpenPath = useCallback(
    async (path: string) => {
      if (!runtimeReady) {
        setWorkspaceError("本地运行时未就绪，请稍候或重启应用");
        return;
      }
      setWorkspaceError(null);
      try {
        const res = await runtimeClient.openWorkspace(path);
        setWorkspacePath(res.path);
        const list = await refreshSessions(res.path);
        if (list.length > 0) {
          setSessionId(list[0].id);
          await loadSessionMessages(list[0].id);
        } else {
          const created = await runtimeClient.createSession(res.path);
          setSessionId(created.session.id);
          setMessages([]);
          await refreshSessions(res.path);
        }
      } catch (err) {
        setWorkspaceError(err instanceof RuntimeClientError ? err.message : "打开工作区失败");
      }
    },
    [runtimeReady, loadSessionMessages, refreshSessions],
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
      await refreshSessions(workspacePath);
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
  }, [workspacePath, sending, runtimeReady, refreshSessions]);

  const handleSelectSession = useCallback(
    async (id: string) => {
      if (sending && id !== sessionIdRef.current) return;
      if (id === sessionIdRef.current) return;
      setSessionId(id);
      try {
        await loadSessionMessages(id);
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
    [sending, loadSessionMessages],
  );

  const handleDeleteSession = useCallback(
    async (id: string) => {
      if (sending || !runtimeReady) return;
      try {
        await runtimeClient.deleteSession(id);
        const list = await refreshSessions(workspacePath);
        if (id === sessionIdRef.current) {
          if (list.length > 0) {
            setSessionId(list[0].id);
            await loadSessionMessages(list[0].id);
          } else if (workspacePath) {
            const created = await runtimeClient.createSession(workspacePath);
            setSessionId(created.session.id);
            setMessages([]);
            await refreshSessions(workspacePath);
          } else {
            setSessionId(undefined);
            setMessages([]);
          }
        }
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
    [sending, runtimeReady, workspacePath, refreshSessions, loadSessionMessages],
  );

  const handleSend = useCallback(
    async (text: string) => {
      if (!workspacePath || !runtimeReady) return;
      let activeId = sessionIdRef.current;
      if (!activeId) {
        const created = await runtimeClient.createSession(workspacePath);
        activeId = created.session.id;
        setSessionId(activeId);
      }

      const userMsg: ChatMessage = { id: nextId(), role: "user", content: text };
      const assistantId = nextId();
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
            session_id: activeId,
          },
          {
            onStarted: (sid) => {
              if (sid) setSessionId(sid);
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
              void refreshSessions(workspacePath);
            },
            onError: (message) => {
              setPermissionRequest(null);
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
    [workspacePath, runtimeReady, refreshSessions],
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

  const handleInspectSkill = useCallback(async (path: string): Promise<SkillInspect> => {
    const res = await runtimeClient.inspectSkill(path);
    return res.skill;
  }, []);

  const handleConfirmInstallSkill = useCallback(
    async (path: string, enabled: boolean) => {
      await runtimeClient.installSkillWithOptions(path, enabled);
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
          <span className={`health-dot health-dot--${health}`} aria-hidden="true" />
          <span className="health-label">
            {health === "ok" ? "就绪" : health === "down" ? "未就绪" : "启动中…"}
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setSkillsCollapsed((v) => !v)}
          >
            {skillsCollapsed ? "展开技能" : "收起技能"}
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => setSettingsOpen(true)}>
            设置
          </button>
        </div>
      </header>

      <div className={`workbench${skillsCollapsed ? " skills-collapsed" : ""}`}>
        <SessionList
          workspacePath={workspacePath}
          workspaceError={workspaceError}
          sessions={sessions}
          activeSessionId={sessionId}
          sending={sending}
          runtimeReady={runtimeReady}
          onPickWorkspace={handlePickFolder}
          onOpenWorkspacePath={handleOpenPath}
          onNewSession={() => void handleNewSession()}
          onSelectSession={(id) => void handleSelectSession(id)}
          onDeleteSession={(id) => void handleDeleteSession(id)}
          showManualPath={!isTauriRuntime()}
        />

        <ChatPanel
          workspaceOpen={workspacePath !== null}
          messages={messages}
          sending={sending}
          runtimeReady={runtimeReady}
          onSend={handleSend}
          onStop={() => void handleStop()}
          onOpenWorkspace={handlePickFolder}
          onToggleSteps={handleToggleSteps}
        />

        <SkillPanel
          skills={skills}
          collapsed={skillsCollapsed}
          onToggle={handleToggleSkill}
          onInspect={handleInspectSkill}
          onConfirmInstall={handleConfirmInstallSkill}
          onUninstall={handleUninstallSkill}
          onRefresh={refreshSkills}
        />
      </div>

      <SettingsModal
        open={settingsOpen}
        initial={config}
        onClose={() => setSettingsOpen(false)}
        onSave={handleSaveConfig}
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
