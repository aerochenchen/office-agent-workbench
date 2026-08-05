import { useCallback, useEffect, useRef, useState } from "react";
import "./styles/theme.css";
import "./App.css";
import { APP_NAME, APP_TAGLINE } from "./lib/brand";
import { bootPollInterval, shouldMarkDownDuringBoot } from "./lib/bootHealth";
import { isModelSetupError, MODEL_SETUP_REPLY } from "./lib/guide";
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
import { getRuntimeToken, isTauriRuntime, pickFolder } from "./lib/tauri";
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
import SessionList from "./components/SessionList";
import ChatPanel from "./components/ChatPanel";
import SkillPanel from "./components/SkillPanel";
import SettingsModal from "./components/SettingsModal";
import PermissionModal from "./components/PermissionModal";

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
  const [configReady, setConfigReady] = useState(false);
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [workspaceError, setWorkspaceError] = useState<string | null>(null);
  const [sessions, setSessions] = useState<SessionMeta[]>([]);
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [skillsCollapsed, setSkillsCollapsed] = useState(false);
  const [draftPrefill, setDraftPrefill] = useState<string | null>(null);
  const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);
  const [permissionRequest, setPermissionRequest] = useState<PermissionRequestEvent | null>(null);
  const [permissionBusy, setPermissionBusy] = useState(false);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const healthFailCount = useRef(0);
  const sendingRef = useRef(false);
  const streamHandleRef = useRef<ChatStreamHandle | null>(null);
  sessionIdRef.current = sessionId;
  sendingRef.current = sending;

  useEffect(() => {
    initUiPreferences();
  }, []);

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
          if (
            shouldMarkDownDuringBoot(elapsed, false) &&
            healthFailCount.current >= 2
          ) {
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
  const status = deriveRuntimeStatus(health, {
    configReady,
    apiKeySet: Boolean(config.api_key_set),
  });

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
        // 第一期取舍：入门对话非空时保留界面 messages，并新建文件夹会话（勿复用 list[0]，
        // 否则 UI 消息与磁盘会话错配）；入门轮次不写入该会话历史。无对话时再加载/创建。
        const retainUiMessages = messages.length > 0;
        if (retainUiMessages) {
          const created = await runtimeClient.createSession(res.path);
          setSessionId(created.session.id);
          await refreshSessions(res.path);
        } else {
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
        }
      } catch (err) {
        setWorkspaceError(err instanceof RuntimeClientError ? err.message : "打开文件夹失败");
      }
    },
    [runtimeReady, loadSessionMessages, refreshSessions, messages.length],
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
    async (text: string, attachedPaths: string[] = []) => {
      if (!runtimeReady) return;

      const userMsg: ChatMessage = { id: nextId(), role: "user", content: text };
      const assistantId = nextId();

      // 无 Key：直接展示固定引导，避免 pending 闪烁，也不调用 chatStream。
      if (!config.api_key_set) {
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
              if (sid) setSessionId(sid);
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
              if (workspacePath) void refreshSessions(workspacePath);
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
    [workspacePath, runtimeReady, refreshSessions, config.api_key_set],
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
              if (status === "needs_config") setSettingsOpen(true);
            }}
            title={
              status === "needs_config"
                ? "本地运行时已启动，请先在设置中配置 API Key"
                : status === "down"
                  ? "无法连接本地运行时"
                  : status === "ok"
                    ? "本地运行时已就绪，API 已配置"
                    : "正在启动本地运行时…"
            }
            disabled={status !== "needs_config"}
          >
            <span className={`health-dot health-dot--${status}`} aria-hidden="true" />
            <span className="health-label">{runtimeStatusLabel(status)}</span>
          </button>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setSkillsCollapsed((v) => !v)}
          >
            {skillsCollapsed ? "展开办事能力" : "收起办事能力"}
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
          workspacePath={workspacePath}
          messages={messages}
          sending={sending}
          runtimeReady={runtimeReady}
          health={health}
          draftPrefill={draftPrefill}
          onDraftPrefillConsumed={() => setDraftPrefill(null)}
          onSend={handleSend}
          onStop={() => void handleStop()}
          onToggleSteps={handleToggleSteps}
        />

        <SkillPanel
          skills={skills}
          collapsed={skillsCollapsed}
          pickDisabled={sending || !runtimeReady}
          onPickSaying={setDraftPrefill}
          onToggle={handleToggleSkill}
          onInspect={handleInspectSkill}
          onConfirmInstall={handleConfirmInstallSkill}
          onUninstall={handleUninstallSkill}
          onRestoreBundled={handleRestoreBundledSkill}
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
