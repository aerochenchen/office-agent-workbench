import { describe, expect, it } from "vitest";
import {
  FORBIDDEN_USER_TERMS,
  GUIDE_HINTS,
  GUIDE_PILLARS,
  isModelSetupError,
  MODEL_SETUP_REPLY,
} from "./guide";

function collectUserCopy(): string[] {
  return [
    ...GUIDE_PILLARS.flatMap((p) => [p.title, p.summary, p.body]),
    ...Object.values(GUIDE_HINTS),
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
    expect(GUIDE_HINTS.emptyChat).toMatch(/问|聊|试/);
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
