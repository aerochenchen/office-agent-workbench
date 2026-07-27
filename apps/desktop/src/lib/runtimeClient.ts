import type {
  ChatReply,
  ChatStreamHandlers,
  PermissionRequestEvent,
  RuntimeConfig,
  SessionMeta,
  SessionUiMessage,
  SkillErrorDetail,
  SkillInspectResult,
  SkillInstallResult,
  SkillMeta,
  TreeEntry,
} from "./types";
import { isTauriRuntime } from "./tauri";

/** Local Python runtime is always loopback-only; not user configurable. */
export const RUNTIME_BASE_URL = "http://127.0.0.1:8765";

let runtimeApiToken: string | null = null;

/** Set Bearer token for non-health runtime requests (from Tauri invoke at startup). */
export function setRuntimeApiToken(token: string | null | undefined): void {
  const trimmed = token?.trim();
  runtimeApiToken = trimmed ? trimmed : null;
}

export function getRuntimeApiToken(): string | null {
  return runtimeApiToken;
}

/** @internal Exported for Vitest auth header smoke tests. */
export function authHeadersForPath(path: string): Record<string, string> {
  if (!runtimeApiToken) return {};
  const bare = path.split("?")[0] ?? path;
  if (bare === "/health") return {};
  return { Authorization: `Bearer ${runtimeApiToken}` };
}

function mergeAuthHeaders(path: string, headers?: HeadersInit): Record<string, string> {
  const auth = authHeadersForPath(path);
  if (!headers) return auth;
  if (headers instanceof Headers) {
    return { ...Object.fromEntries(headers.entries()), ...auth };
  }
  if (Array.isArray(headers)) {
    return { ...Object.fromEntries(headers), ...auth };
  }
  return { ...headers, ...auth };
}

export class RuntimeClientError extends Error {
  status?: number;
  skillDetail?: SkillErrorDetail;

  constructor(message: string, status?: number, skillDetail?: SkillErrorDetail) {
    super(message);
    this.name = "RuntimeClientError";
    this.status = status;
    this.skillDetail = skillDetail;
  }
}

function parseSkillErrorDetail(detail: unknown): SkillErrorDetail | undefined {
  if (!detail || typeof detail !== "object") return undefined;
  const d = detail as SkillErrorDetail;
  if (
    d.validation ||
    Array.isArray(d.errors) ||
    Array.isArray(d.warnings) ||
    typeof d.error === "string"
  ) {
    return d;
  }
  return undefined;
}

export function formatSkillErrorDetail(detail: unknown): string {
  if (typeof detail === "string") return detail;
  const skillDetail = parseSkillErrorDetail(detail);
  if (!skillDetail) {
    return typeof detail === "object" ? JSON.stringify(detail) : String(detail);
  }
  const lines: string[] = [];
  if (skillDetail.error) lines.push(skillDetail.error);
  const errors = skillDetail.validation?.errors ?? skillDetail.errors ?? [];
  const warnings = skillDetail.validation?.warnings ?? skillDetail.warnings ?? [];
  for (const e of errors) lines.push(e);
  for (const w of warnings) lines.push(`警告：${w}`);
  return lines.length > 0 ? lines.join("\n") : "技能包校验失败";
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
        ...mergeAuthHeaders(path, rest.headers),
      },
    });
    if (!res.ok) {
      let detail: unknown = res.statusText;
      let skillDetail: SkillErrorDetail | undefined;
      try {
        const body = (await res.json()) as { detail?: unknown };
        if (body?.detail !== undefined) {
          detail = body.detail;
          skillDetail = parseSkillErrorDetail(body.detail);
        }
      } catch {
        // ignore non-JSON error bodies
      }
      throw new RuntimeClientError(formatSkillErrorDetail(detail), res.status, skillDetail);
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

/** @internal Exported for Vitest SSE parsing smoke tests. */
export function createSseDispatcher(handlers: ChatStreamHandlers): {
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
        if (typeof data.session_id === "string") {
          handlers.onStarted?.(
            data.session_id,
            typeof data.turn_id === "string" ? data.turn_id : undefined,
          );
        }
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
          turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
        });
        break;
      case "tool_done":
        handlers.onToolDone?.({
          id: String(data.id ?? ""),
          name: String(data.name ?? ""),
          label: String(data.label ?? data.name ?? ""),
          ok: Boolean(data.ok),
          summary: typeof data.summary === "string" ? data.summary : undefined,
          turn_id: typeof data.turn_id === "string" ? data.turn_id : undefined,
        });
        break;
      case "permission_request":
        handlers.onPermissionRequest?.({
          id: String(data.id ?? ""),
          tool: String(data.tool ?? ""),
          summary: String(data.summary ?? ""),
          session_id: String(data.session_id ?? ""),
        } satisfies PermissionRequestEvent);
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

/** External abort handle for an in-flight chat stream (XHR or fetch). */
export type ChatStreamHandle = {
  abort: () => void;
};

/**
 * Progressive XHR SSE reader — works in Tauri WebView2/WKWebView where
 * `fetch().body.getReader()` is often unavailable or buffered until complete.
 */
function streamChatViaXhr(
  input: { message: string; attached_paths?: string[]; session_id?: string },
  handlers: ChatStreamHandlers,
  timeoutMs = 600_000,
  onHandle?: (handle: ChatStreamHandle) => void,
): Promise<StreamOutcome> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    const { dispatchBlock, outcome } = createSseDispatcher(handlers);
    let buffer = "";
    let seenChars = 0;
    let userAborted = false;
    const streamAuth = authHeadersForPath("/chat/stream");

    onHandle?.({
      abort: () => {
        userAborted = true;
        xhr.abort();
      },
    });

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
    if (streamAuth.Authorization) {
      xhr.setRequestHeader("Authorization", streamAuth.Authorization);
    }
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
    xhr.onabort = () => {
      if (userAborted) {
        // Treat user stop as a soft end if SSE already delivered final/error.
        if (outcome.sawFinal || outcome.sawError) {
          resolve(outcome);
          return;
        }
        handlers.onError?.("已取消生成");
        outcome.sawError = true;
        resolve(outcome);
        return;
      }
      reject(new Error("aborted"));
    };

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
  onHandle?: (handle: ChatStreamHandle) => void,
): Promise<StreamOutcome> {
  const controller = new AbortController();
  let userAborted = false;
  onHandle?.({
    abort: () => {
      userAborted = true;
      controller.abort();
    },
  });
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const res = await fetch(`${RUNTIME_BASE_URL}/chat/stream`, {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
        ...authHeadersForPath("/chat/stream"),
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
  } catch (err) {
    if (userAborted) {
      const outcome: StreamOutcome = { sawAny: true, sawFinal: false, sawError: true };
      handlers.onError?.("已取消生成");
      return outcome;
    }
    throw err;
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

  inspectSkill(path: string): Promise<SkillInspectResult> {
    return request("/skills/inspect", {
      method: "POST",
      body: JSON.stringify({ path }),
    });
  },

  installSkillWithOptions(
    path: string,
    enabled: boolean,
    applyFixes = false,
  ): Promise<SkillInstallResult> {
    return request("/skills/install", {
      method: "POST",
      body: JSON.stringify({ path, enabled, apply_fixes: applyFixes }),
    });
  },

  setEnabled(id: string, enabled: boolean): Promise<{ ok: boolean; id: string; enabled: boolean }> {
    return request(`/skills/${encodeURIComponent(id)}/enabled`, {
      method: "POST",
      body: JSON.stringify({ enabled }),
    });
  },

  uninstallSkill(id: string): Promise<{ ok: boolean; id: string }> {
    return request(`/skills/${encodeURIComponent(id)}`, {
      method: "DELETE",
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

  resolvePermission(requestId: string, allow: boolean): Promise<{ ok: boolean }> {
    return request(`/chat/permissions/${encodeURIComponent(requestId)}`, {
      method: "POST",
      body: JSON.stringify({ allow }),
      timeoutMs: 30_000,
    });
  },

  cancelChat(sessionId: string): Promise<{ ok: boolean }> {
    return request("/chat/cancel", {
      method: "POST",
      body: JSON.stringify({ session_id: sessionId }),
      timeoutMs: 10_000,
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
   * No silent sync `/chat` fallback — sync auto-allows tools and would bypass
   * permission UI (cautious/standard confirmation).
   * Returns an abort handle so the UI can stop the in-flight XHR/fetch.
   */
  chatStream(
    input: {
      message: string;
      attached_paths?: string[];
      session_id?: string;
    },
    handlers: ChatStreamHandlers,
  ): { abort: () => void; done: Promise<void> } {
    let streamAbort: (() => void) | null = null;
    const handle: ChatStreamHandle = {
      abort: () => {
        streamAbort?.();
      },
    };

    const done = (async () => {
      const bindHandle = (h: ChatStreamHandle) => {
        streamAbort = h.abort;
      };

      try {
        const outcome = isTauriRuntime()
          ? await streamChatViaXhr(input, handlers, 600_000, bindHandle)
          : await streamChatViaFetch(input, handlers, 600_000, bindHandle);

        if (outcome.sawFinal || outcome.sawError) return;
        handlers.onError?.(
          outcome.sawAny
            ? "流式对话异常结束，未收到最终结果"
            : "流式对话未能建立（未回退到同步接口，以避免绕过权限确认）",
        );
      } catch (err) {
        handlers.onError?.(mapNetworkError(err, "600s"));
      }
    })();

    return { abort: () => handle.abort(), done };
  },
};
