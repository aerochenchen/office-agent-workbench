import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CAPABILITY_TREE,
  FORBIDDEN_USER_TERMS,
  GUIDE_HINTS,
  GUIDE_PILLARS,
  GUIDE_TRY_HEADLINE,
  GUIDE_TRY_SAYINGS,
  GUIDE_TRY_SUBLINE,
  listCapabilityLeaves,
  isModelSetupError,
  MODEL_SETUP_REPLY,
} from "./guide";

const here = fileURLToPath(new URL(".", import.meta.url));

function collectUserCopy(): string[] {
  return [
    ...GUIDE_PILLARS.flatMap((p) => [p.title, p.summary, p.body]),
    ...Object.values(GUIDE_HINTS),
    GUIDE_TRY_HEADLINE,
    GUIDE_TRY_SUBLINE,
    ...GUIDE_TRY_SAYINGS,
    ...CAPABILITY_TREE.flatMap((b) => [
      b.label,
      ...b.children.flatMap((c) => [c.label, c.saying]),
    ]),
    MODEL_SETUP_REPLY,
  ];
}

describe("guide copy", () => {
  it("does not expose forbidden terms to users", () => {
    const blob = collectUserCopy().join("\n");
    for (const term of FORBIDDEN_USER_TERMS) {
      expect(blob, `found forbidden term: ${term}`).not.toContain(term);
    }
  });

  it("MODEL_SETUP_REPLY guides user to settings and API key", () => {
    expect(MODEL_SETUP_REPLY).toMatch(/设置/);
    expect(MODEL_SETUP_REPLY).toMatch(/API|密钥|Key/i);
    expect(MODEL_SETUP_REPLY).toMatch(/模型/);
  });

  it("emptyChat invites chatting first", () => {
    expect(GUIDE_HINTS.emptyChat.length).toBeGreaterThan(8);
    expect(GUIDE_HINTS.emptyChat).toMatch(/右侧|分类/);
  });

  it("try-sayings are the empty-chat capability signal", () => {
    expect(GUIDE_TRY_HEADLINE).toMatch(/一句话|办事/);
    expect(GUIDE_TRY_SAYINGS.length).toBeGreaterThanOrEqual(6);
    expect(GUIDE_TRY_SAYINGS.length).toBeLessThanOrEqual(10);
    for (const saying of GUIDE_TRY_SAYINGS) {
      expect(saying.trim().length).toBeGreaterThan(4);
    }
  });

  it("emptyChat and workspaceReady hand off to the right rail after first turn", () => {
    expect(GUIDE_HINTS.emptyChat).toMatch(/右侧/);
    expect(GUIDE_HINTS.workspaceReady).toMatch(/右侧/);
    expect(GUIDE_HINTS.capabilityTreeIdle).toMatch(/中间|开聊/);
  });

  it("capability tree is categorized office scenarios with unique ids", () => {
    expect(CAPABILITY_TREE.length).toBeGreaterThanOrEqual(5);
    const ids = new Set<string>();
    for (const branch of CAPABILITY_TREE) {
      expect(branch.label.trim().length).toBeGreaterThan(1);
      expect(branch.children.length).toBeGreaterThanOrEqual(2);
      expect(ids.has(branch.id)).toBe(false);
      ids.add(branch.id);
      for (const leaf of branch.children) {
        expect(ids.has(leaf.id)).toBe(false);
        ids.add(leaf.id);
        expect(leaf.label.trim().length).toBeGreaterThan(1);
        expect(leaf.saying.trim().length).toBeGreaterThan(4);
      }
    }
    expect(listCapabilityLeaves().length).toBeGreaterThan(GUIDE_TRY_SAYINGS.length);
  });

  it("featured try-sayings all come from the capability tree", () => {
    const sayings = new Set(listCapabilityLeaves().map((l) => l.saying));
    for (const saying of GUIDE_TRY_SAYINGS) {
      expect(sayings.has(saying)).toBe(true);
    }
  });

  it("index.html boot splash mirrors GUIDE_PILLARS title+summary", () => {
    const html = readFileSync(resolve(here, "../../index.html"), "utf8");
    for (const p of GUIDE_PILLARS) {
      expect(html, p.title).toContain(p.title);
      expect(html, p.summary).toContain(p.summary);
    }
    expect(html).toContain("正在启动本地运行组件");
  });
});

describe("isModelSetupError", () => {
  it("matches API key / auth setup failures", () => {
    expect(isModelSetupError("API Key 未配置")).toBe(true);
    expect(isModelSetupError("missing api key")).toBe(true);
    expect(isModelSetupError("HTTP 401 Unauthorized")).toBe(true);
    expect(isModelSetupError("forbidden 403")).toBe(true);
  });

  it("does not match generic runtime connectivity", () => {
    expect(
      isModelSetupError("无法连接本地运行时（127.0.0.1:8765）。请关闭后重新打开本应用"),
    ).toBe(false);
    expect(isModelSetupError("网络连接失败")).toBe(false);
  });
});

describe("folderless first chat (shell contract)", () => {
  it("pre-create session only when workspace is open", () => {
    // Mirrors App.handleSend: !sessionId && workspacePath → createSession;
    // !workspacePath → omit session_id; Runtime test_chat_without_workspace_onboarding
    // covers POST /chat creating create_session("").
    const needsPreCreate = (sessionId: string | undefined, workspacePath: string | null) =>
      !sessionId && Boolean(workspacePath);
    expect(needsPreCreate(undefined, null)).toBe(false);
    expect(needsPreCreate(undefined, "/tmp/ws")).toBe(true);
    expect(needsPreCreate("sess-1", null)).toBe(false);
  });
});
