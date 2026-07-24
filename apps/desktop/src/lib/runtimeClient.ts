import type {
  ChatReply,
  ChatStreamHandlers,
  RuntimeConfig,
  SessionMeta,
  SessionUiMessage,
  SkillInspect,
  SkillMeta,
  TreeEntry,
} from "./types";
import { isTauriRuntime } from "./tauri";

/** Local Python runtime is always loopback-only; not user configurable. */
export const RUNTIME_BASE_URL = "http://127.0.0.1:8765";

export class RuntimeClientError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "RuntimeClientError";
    this.status = status;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs = 30_000, ...rest } = init ?? {};
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${RUNTIME_BASE_URL}${path}`, {
      ...rest,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(rest.headers ?? {}),
      },
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = (await res.json()) as { detail?: string };
        if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
      } catch {
        // ignore non-JSON error bodies
      }
      throw new RuntimeClientError(detail, res.status);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  } catch (err) {
    if (err instanceof RuntimeClientError) throw err;
    const name = err instanceof Error ? err.name : "";
    const msg = err instanceof Error ? err.message : String(err);
    if (name === "AbortError" || msg.includes("aborted")) {
      throw new RuntimeClientError(
        `请求超时（${Math.round(timeoutMs / 1000)}s）。若正在长对话/调工具，请稍候再试；勿反复刷新。`,
      );
    }
    if (/Failed to fetch|NetworkError|ECONNREFUSED|Load failed/i.test(msg)) {
      throw new RuntimeClientError(
        "无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 %TEMP%\\office-agent-desktop.log",
      );
    }
    throw new RuntimeClientError(`运行时请求失败：${msg || name || "未知错误"}`);
  } finally {
    clearTimeout(timer);
  }
}

export const runtimeClient = {
  health(): Promise<{ ok: boolean }> {
    return request("/health", { timeoutMs: 3_000 });
  },

  openWorkspace(path: string): Promise<{ ok: boolean; path: string }> {
    return request("/workspace/open", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },

  getTree(): Promise<{ entries: TreeEntry[] }> {
    return request("/workspace/tree");
  },

  listSessions(workspacePath?: string): Promise<{ sessions: SessionMeta[] }> {
    const q = workspacePath ? `?workspace_path=${encodeURIComponent(workspacePath)}` : "";
    return request(`/sessions${q}`);
  },

  createSession(workspacePath?: string): Promise<{ ok: boolean; session: SessionMeta }> {
    return request("/sessions", {
      method: "POST",
      body: JSON.stringify(workspacePath ? { workspace_path: workspacePath } : {}),
    });
  },

  getSessionMessages(sessionId: string): Promise<{ messages: SessionUiMessage[]; raw_count: number }> {
    return request(`/sessions/${encodeURIComponent(sessionId)}/messages`);
  },

  deleteSession(sessionId: string): Promise<{ ok: boolean; id: string }> {
    return request(`/sessions/${encodeURIComponent(sessionId)}`, {
      method: "DELETE",
    });
  },

  listSkills(): Promise<{ skills: SkillMeta[] }> {
    return request("/skills");
  },

  installSkill(path: string): Promise<{ ok: boolean; skill: Partial<SkillMeta> }> {
    return request("/skills/install", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },

  inspectSkill(path: string): Promise<{ skill: SkillInspect }> {
    return request("/skills/inspect", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },

  installSkillWithOptions(
    path: string,
    enabled: boolean,
  ): Promise<{ ok: boolean; skill: SkillInspect }> {
    return request("/skills/install", {
      method: "POST",
      body: JSON.stringify({ path, enabled }),
    });
  },

  setEnabled(id: string, enabled: boolean): Promise<{ ok: boolean; id: string; enabled: boolean }> {
    return request(`/skills/${encodeURIComponent(id)}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  getConfig(): Promise<RuntimeConfig> {
    return request("/config", { timeoutMs: 5_000 });
  },

  saveConfig(partial: Partial<RuntimeConfig>): Promise<{ ok: boolean }> {
    return request("/config", {
      method: "POST",
      body: JSON.stringify(partial),
    });
  },

  chat(input: {
    message: string;
    attached_paths?: string[];
    session_id?: string;
  }): Promise<ChatReply> {
    return request("/chat", {
      method: "POST",
      body: JSON.stringify(input),
      timeoutMs: 600_000,
    });
  },

  /**
   * One chat turn with progress callbacks.
   * Packaged Tauri/WebView2 often cannot consume fetch SSE bodies, so the
   * desktop shell uses sync `/chat` (still reports started/final to the UI).
   * Browser/`vite` keeps SSE `/chat/stream` with a sync fallback.
   */
  async chatStream(
    input: {
      message: string;
      attached_paths?: string[];
      session_id?: string;
    },
    handlers: ChatStreamHandlers,
  ): Promise<void> {
    const runSync = async () => {
      handlers.onStatus?.("planning");
      const reply = await this.chat(input);
      handlers.onStarted?.(reply.session_id);
      handlers.onStatus?.("finishing");
      handlers.onFinal?.(reply);
    };

    if (isTauriRuntime()) {
      try {
        await runSync();
      } catch (err) {
        if (err instanceof RuntimeClientError) {
          handlers.onError?.(err.message);
          return;
        }
        const name = err instanceof Error ? err.name : "";
        const msg = err instanceof Error ? err.message : String(err);
        if (name === "AbortError" || msg.includes("aborted")) {
          handlers.onError?.(
            "请求超时（300s）。若正在长对话/调工具，请稍候再试；勿反复刷新。",
          );
          return;
        }
        if (/Failed to fetch|NetworkError|ECONNREFUSED|Load failed/i.test(msg)) {
          handlers.onError?.(
            "无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 %TEMP%\\office-agent-desktop.log",
          );
          return;
        }
        handlers.onError?.(msg || "对话请求失败");
      }
      return;
    }

    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 300_000);
    try {
      const res = await fetch(`${RUNTIME_BASE_URL}/chat/stream`, {
        method: "POST",
        signal: controller.signal,
        headers: {
          "Content-Type": "application/json",
          Accept: "text/event-stream",
        },
        body: JSON.stringify(input),
      });
      if (res.status === 404) {
        await runSync();
        return;
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = (await res.json()) as { detail?: string };
          if (body?.detail) detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } catch {
          // ignore
        }
        throw new RuntimeClientError(detail, res.status);
      }
      if (!res.body) {
        await runSync();
        return;
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let sawFinal = false;
      let sawError = false;
      let sawAny = false;

      const dispatchBlock = (block: string) => {
        const lines = block.split(/\r?\n/);
        let eventName = "message";
        const dataLines: string[] = [];
        for (const line of lines) {
          if (line.startsWith("event:")) eventName = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length === 0) return;
        let data: Record<string, unknown> = {};
        try {
          data = JSON.parse(dataLines.join("\n")) as Record<string, unknown>;
        } catch {
          return;
        }
        sawAny = true;
        switch (eventName) {
          case "started":
            if (typeof data.session_id === "string") handlers.onStarted?.(data.session_id);
            break;
          case "status":
            if (typeof data.phase === "string") handlers.onStatus?.(data.phase);
            break;
          case "tool_start":
            handlers.onToolStart?.({
              id: String(data.id ?? ""),
              name: String(data.name ?? ""),
              label: String(data.label ?? data.name ?? ""),
              args_summary: typeof data.args_summary === "string" ? data.args_summary : undefined,
            });
            break;
          case "tool_done":
            handlers.onToolDone?.({
              id: String(data.id ?? ""),
              name: String(data.name ?? ""),
              label: String(data.label ?? data.name ?? ""),
              ok: Boolean(data.ok),
              summary: typeof data.summary === "string" ? data.summary : undefined,
            });
            break;
          case "final":
            sawFinal = true;
            handlers.onFinal?.({
              reply: String(data.reply ?? ""),
              tool_events: Array.isArray(data.tool_events) ? (data.tool_events as ChatReply["tool_events"]) : [],
              session_id: String(data.session_id ?? ""),
            });
            break;
          case "error":
            sawError = true;
            handlers.onError?.(String(data.message ?? "未知错误"));
            break;
          default:
            break;
        }
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parts = buffer.split(/\r?\n\r?\n/);
        buffer = parts.pop() ?? "";
        for (const part of parts) {
          if (part.trim()) dispatchBlock(part);
        }
      }
      buffer += decoder.decode();
      if (buffer.trim()) dispatchBlock(buffer);

      if (sawFinal || sawError) return;
      if (!sawAny) {
        await runSync();
        return;
      }
      handlers.onError?.("流式对话异常结束，未收到最终结果");
    } catch (err) {
      if (err instanceof RuntimeClientError) {
        handlers.onError?.(err.message);
        return;
      }
      const name = err instanceof Error ? err.name : "";
      const msg = err instanceof Error ? err.message : String(err);
      if (name === "AbortError" || msg.includes("aborted")) {
        handlers.onError?.(
          "请求超时（300s）。若正在长对话/调工具，请稍候再试；勿反复刷新。",
        );
        return;
      }
      if (/Failed to fetch|NetworkError|ECONNREFUSED|Load failed/i.test(msg)) {
        handlers.onError?.(
          "无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 %TEMP%\\office-agent-desktop.log",
        );
        return;
      }
      handlers.onError?.(msg || "流式请求失败");
    } finally {
      clearTimeout(timer);
    }
  },
};
