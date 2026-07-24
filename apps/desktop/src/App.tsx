import { useCallback, useEffect, useRef, useState } from "react";
import "./styles/theme.css";
import "./App.css";
import { runtimeClient, RuntimeClientError } from "./lib/runtimeClient";
import { pickFolder } from "./lib/tauri";
import type { ChatMessage, RuntimeConfig, SkillMeta, TreeEntry } from "./lib/types";
import WorkspaceTree from "./components/WorkspaceTree";
import ChatPanel from "./components/ChatPanel";
import SkillPanel from "./components/SkillPanel";
import SettingsModal from "./components/SettingsModal";

type HealthState = "checking" | "ok" | "down";

const DEFAULT_CONFIG: RuntimeConfig = {
  api_base: "https://api.deepseek.com/v1",
  api_key: "",
  model: "deepseek-v4-flash",
  allowed_hosts: ["api.deepseek.com", "127.0.0.1", "localhost"],
};

let messageSeq = 0;
function nextId(): string {
  messageSeq += 1;
  return `m${messageSeq}`;
}

function App() {
  const [health, setHealth] = useState<HealthState>("checking");
  const [workspacePath, setWorkspacePath] = useState<string | null>(null);
  const [treeEntries, setTreeEntries] = useState<TreeEntry[]>([]);
  const [treeError, setTreeError] = useState<string | null>(null);
  const [skills, setSkills] = useState<SkillMeta[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | undefined>(undefined);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [skillsCollapsed, setSkillsCollapsed] = useState(false);
  const [config, setConfig] = useState<RuntimeConfig>(DEFAULT_CONFIG);
  const sessionIdRef = useRef<string | undefined>(undefined);
  const healthFailCount = useRef(0);
  const sendingRef = useRef(false);
  sessionIdRef.current = sessionId;
  sendingRef.current = sending;

  const checkHealth = useCallback(async () => {
    // Avoid false "runtime down" while a long chat occupies the UI; still probe lightly.
    if (sendingRef.current) return;
    try {
      await runtimeClient.health();
      healthFailCount.current = 0;
      setHealth("ok");
    } catch {
      healthFailCount.current += 1;
      // Require two consecutive failures (~16s) before flipping to down
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
          api_key: cfg.api_key,
          model: cfg.model,
          allowed_hosts: cfg.allowed_hosts,
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
      // Skills panel shows its own empty state; runtime status dot already
      // signals connectivity issues, no need to duplicate the error here.
    }
  }, []);

  useEffect(() => {
    void refreshSkills();
  }, [refreshSkills]);

  const refreshTree = useCallback(async () => {
    try {
      const { entries } = await runtimeClient.getTree();
      setTreeEntries(entries);
      setTreeError(null);
    } catch (err) {
      setTreeError(err instanceof RuntimeClientError ? err.message : "读取目录失败");
    }
  }, []);

  const handleOpenPath = useCallback(
    async (path: string) => {
      setTreeError(null);
      try {
        const res = await runtimeClient.openWorkspace(path);
        setWorkspacePath(res.path);
        setSessionId(undefined);
        setMessages([]);
        await refreshTree();
      } catch (err) {
        setTreeError(err instanceof RuntimeClientError ? err.message : "打开工作区失败");
      }
    },
    [refreshTree],
  );

  const handlePickFolder = useCallback(async () => {
    const path = await pickFolder();
    if (path) await handleOpenPath(path);
  }, [handleOpenPath]);

  const handleSend = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = { id: nextId(), role: "user", content: text };
      setMessages((prev) => [...prev, userMsg]);
      setSending(true);
      try {
        const res = await runtimeClient.chat({
          message: text,
          session_id: sessionIdRef.current,
        });
        setSessionId(res.session_id);
        setMessages((prev) => [
          ...prev,
          { id: nextId(), role: "assistant", content: res.reply, toolEvents: res.tool_events },
        ]);
      } catch (err) {
        const detail = err instanceof RuntimeClientError ? err.message : "请求失败";
        setMessages((prev) => [...prev, { id: nextId(), role: "error", content: detail }]);
      } finally {
        setSending(false);
      }
    },
    [],
  );

  const handleToggleSkill = useCallback(async (id: string, enabled: boolean) => {
    try {
      await runtimeClient.setEnabled(id, enabled);
    } finally {
      await refreshSkills();
    }
  }, [refreshSkills]);

  const handleInstallSkill = useCallback(async (path: string) => {
    const res = await runtimeClient.installSkill(path);
    await refreshSkills();
    const tier = res.skill?.tier;
    const minRam = res.skill?.min_ram_gb;
    if (tier === "heavy") {
      const ok = window.confirm(
        `「${res.skill?.name ?? res.skill?.id}」为重量级 Skill${
          minRam ? `，建议至少 ${minRam}GB 内存` : ""
        }。是否保持启用？`,
      );
      if (!ok && res.skill?.id) {
        await runtimeClient.setEnabled(res.skill.id, false);
        await refreshSkills();
      }
    }
  }, [refreshSkills]);

  const handleSaveConfig = useCallback(async (partial: Partial<RuntimeConfig>) => {
    await runtimeClient.saveConfig(partial);
    setConfig((prev) => ({ ...prev, ...partial }));
    setSettingsOpen(false);
  }, []);

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="topbar-brand">
          <span className="topbar-title">办公智能体工作台</span>
          <span className="topbar-subtitle">Office Agent Workbench</span>
        </div>
        <div className="topbar-actions">
          <span className={`health-dot health-dot--${health}`} aria-hidden="true" />
          <span className="health-label">
            {health === "ok" ? "运行时已连接" : health === "down" ? "运行时未连接" : "检测中…"}
          </span>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={() => setSkillsCollapsed((v) => !v)}
          >
            {skillsCollapsed ? "展开 Skill" : "收起 Skill"}
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => setSettingsOpen(true)}>
            设置
          </button>
        </div>
      </header>

      <div className={`workbench${skillsCollapsed ? " skills-collapsed" : ""}`}>
        <WorkspaceTree
          workspacePath={workspacePath}
          entries={treeEntries}
          error={treeError}
          onPickFolder={handlePickFolder}
          onOpenPath={handleOpenPath}
          onRefresh={refreshTree}
        />

        <ChatPanel
          workspaceOpen={workspacePath !== null}
          messages={messages}
          sending={sending}
          onSend={handleSend}
        />

        <SkillPanel
          skills={skills}
          collapsed={skillsCollapsed}
          onToggle={handleToggleSkill}
          onInstall={handleInstallSkill}
          onRefresh={refreshSkills}
        />
      </div>

      <SettingsModal
        open={settingsOpen}
        initial={config}
        onClose={() => setSettingsOpen(false)}
        onSave={handleSaveConfig}
      />
    </div>
  );
}

export default App;
