import type { ChatReply, RuntimeConfig, SkillMeta, TreeEntry } from "./types";

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
        "无法连接本地运行时（127.0.0.1:8765）。请确认终端里 uvicorn 仍在运行，或重新启动：uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765",
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

  listSkills(): Promise<{ skills: SkillMeta[] }> {
    return request("/skills");
  },

  installSkill(path: string): Promise<{ ok: boolean; skill: Partial<SkillMeta> }> {
    return request("/skills/install", {
      method: "POST",
      body: JSON.stringify({ path }),
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
      timeoutMs: 300_000,
    });
  },
};
