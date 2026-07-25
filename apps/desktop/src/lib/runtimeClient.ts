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

/** Cross-platform hint for where the desktop sidecar writes logs. */
export function runtimeLogHint(): string {
  const ua = typeof navigator !== "undefined" ? navigator.userAgent : "";
  const isWin = /Windows/i.test(ua);
  if (isWin) {
    return "%TEMP%\\office-agent-desktop.log";
  }
  return "系统临时目录中的 office-agent-desktop.log（macOS 多为 $TMPDIR）";
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
        `无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 ${runtimeLogHint()}`,
      );
    }
    throw new RuntimeClientError(`运行时请求失败：${msg || name || "未知错误"}`);
  } finally {
    clearTimeout(timer);
  }
}

function mapNetworkError(err: unknown, timeoutLabel = "300s"): string {
  if (err instanceof RuntimeClientError) return err.message;
  const name = err instanceof Error ? err.name : "";
  const msg = err instanceof Error ? err.message : String(err);
  if (name === "AbortError" || msg.includes("aborted") || msg.includes("timeout")) {
    return `请求超时（${timeoutLabel}）。若正在长对话/调工具，请稍候再试；勿反复刷新。`;
  }
  if (/Failed to fetch|NetworkError|ECONNREFUSED|Load failed/i.test(msg)) {
    return `无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用；若仍失败，查看 ${runtimeLogHint()}`;
  }
  return msg || "对话请求失败";
}

type StreamOutcome = {
  sawAny: boolean;
  sawFinal: boolean;
  sawError: boolean;
};

function createSseDispatcher(handlers: ChatStreamHandlers): {
  dispatchBlock: (block: string) => void;
  outcome: StreamOutcome;
} {
  const outcome: StreamOutcome = { sawAny: false, sawFinal: false, sawError: false };

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
    outcome.sawAny = true;
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
        outcome.sawFinal = true;
        handlers.onFinal?.({
          reply: String(data.reply ?? ""),
          tool_events: Array.isArray(data.tool_events)
            ? (data.tool_events as ChatReply["tool_events"])
            : [],
          session_id: String(data.session_id ?? ""),
        });
        break;
      case "error":
        outcome.sawError = true;
        handlers.onError?.(String(data.message ?? "未知错误"));
        break;
      default:
        break;
    }
  };

  return { dispatchBlock, outcome };
}

/**
 * Progressive XHR SSE reader — works in Tauri WebView2/WKWebView where
 * `fetch().body.getReader()` is often unavailable or buffered until complete.
 */
function streamChatViaXhr(
  input: { message: string; attached_paths?: string[]; session_id?: string },
  handlers: ChatStreamHandlers,
  timeoutMs = 600_000,
): Promise<StreamOutcome> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const { dispatchBlock, outcome } = createSseDispatcher(handlers);
    let buffer = "";
    let seenChars = 0;

    const pump = () => {
      const text = xhr.responseText || "";
      if (text.length <= seenChars) return;
      buffer += text.slice(seenChars);
      seenChars = text.length;
      const parts = buffer.split(/\r?\n\r?\n/);
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        if (part.trim()) dispatchBlock(part);
      }
    };

    xhr.open("POST", `${RUNTIME_BASE_URL}/chat/stream`);
    xhr.setRequestHeader("Content-Type", "application/json");
    xhr.setRequestHeader("Accept", "text/event-stream");
    xhr.timeout = timeoutMs;
    xhr.responseType = "text";

    xhr.onprogress = () => pump();
    xhr.onreadystatechange = () => {
      // readyState 3 (LOADING) also carries incremental body in some WebViews
      if (xhr.readyState === XMLHttpRequest.LOADING || xhr.readyState === XMLHttpRequest.DONE) {
        pump();
      }
    };

    xhr.onload = () => {
      pump();
      if (buffer.trim()) dispatchBlock(buffer);
      if (xhr.status === 404) {
        reject(new RuntimeClientError("stream endpoint missing", 404));
        return;
      }
      if (xhr.status < 200 || xhr.status >= 300) {
        let detail = xhr.statusText || `HTTP ${xhr.status}`;
        try {
          const body = JSON.parse(xhr.responseText) as { detail?: string };
          if (body?.detail) {
            detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
          }
        } catch {
          // ignore
        }
        reject(new RuntimeClientError(detail, xhr.status));
        return;
      }
      resolve(outcome);
    };

    xhr.onerror = () => reject(new Error("NetworkError"));
    xhr.ontimeout = () => reject(new Error("timeout"));
    xhr.onabort = () => reject(new Error("aborted"));

    try {
      xhr.send(JSON.stringify(input));
    } catch (err) {
      reject(err instanceof Error ? err : new Error(String(err)));
    }
  });
}

async function streamChatViaFetch(
  input: { message: string; attached_paths?: string[]; session_id?: string },
  handlers: ChatStreamHandlers,
  timeoutMs = 600_000,
): Promise<StreamOutcome> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
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
      throw new RuntimeClientError("stream endpoint missing", 404);
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
      throw new RuntimeClientError("stream body unavailable", res.status);
    }

    const { dispatchBlock, outcome } = createSseDispatcher(handlers);
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

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
    return outcome;
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
   * One chat turn with live progress callbacks.
   * Desktop (Tauri): XHR progressive SSE — WebView often cannot stream fetch bodies.
   * Browser: fetch ReadableStream SSE.
   * Sync `/chat` only when the stream never delivered any event (no mid-flight double-run).
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

    let delivered = false;
    const tracking: ChatStreamHandlers = {
      onStarted: (sessionId) => {
        delivered = true;
        handlers.onStarted?.(sessionId);
      },
      onStatus: (phase) => {
        delivered = true;
        handlers.onStatus?.(phase);
      },
      onToolStart: (ev) => {
        delivered = true;
        handlers.onToolStart?.(ev);
      },
      onToolDone: (ev) => {
        delivered = true;
        handlers.onToolDone?.(ev);
      },
      onFinal: (reply) => {
        delivered = true;
        handlers.onFinal?.(reply);
      },
      onError: (message) => {
        delivered = true;
        handlers.onError?.(message);
      },
    };

    try {
      const outcome = isTauriRuntime()
        ? await streamChatViaXhr(input, tracking)
        : await streamChatViaFetch(input, tracking);

      if (outcome.sawFinal || outcome.sawError) return;
      if (!outcome.sawAny && !delivered) {
        await runSync();
        return;
      }
      handlers.onError?.("流式对话异常结束，未收到最终结果");
    } catch (err) {
      if (!delivered) {
        try {
          await runSync();
          return;
        } catch (syncErr) {
          handlers.onError?.(mapNetworkError(syncErr, "600s"));
          return;
        }
      }
      handlers.onError?.(mapNetworkError(err, "600s"));
    }
  },
};
