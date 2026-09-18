import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import {
  CAPABILITY_TREE,
  FORBIDDEN_USER_TERMS,
  GUIDE_EMPTY_HEADLINE_NO_FOLDER,
  GUIDE_EMPTY_HEADLINE_WITH_FOLDER,
  GUIDE_HINTS,
  GUIDE_PILLARS,
  guideEmptyHeadline,
  listCapabilityLeaves,
  isModelSetupError,
  MODEL_SETUP_REPLY,
  needsModelSetup,
} from "./guide";

const here = fileURLToPath(new URL(".", import.meta.url));

function collectUserCopy(): string[] {
  return [
    ...GUIDE_PILLARS.flatMap((p) => [p.title, p.summary, p.body]),
    ...Object.values(GUIDE_HINTS),
    GUIDE_EMPTY_HEADLINE_NO_FOLDER,
    GUIDE_EMPTY_HEADLINE_WITH_FOLDER,
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

  it("empty headlines are state-aware: folder gate then one-sentence start", () => {
    expect(GUIDE_EMPTY_HEADLINE_NO_FOLDER).toBe("打开文件夹，一句话开始办事");
    expect(GUIDE_EMPTY_HEADLINE_WITH_FOLDER).toBe("一句话开始办事");
    expect(guideEmptyHeadline(false)).toBe(GUIDE_EMPTY_HEADLINE_NO_FOLDER);
    expect(guideEmptyHeadline(true)).toBe(GUIDE_EMPTY_HEADLINE_WITH_FOLDER);
  });

  it("capability tree is the sole empty-chat capability catalog (no featured subset)", () => {
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
    expect(listCapabilityLeaves().length).toBeGreaterThanOrEqual(16);
  });

  it("includes plan-resume for continuing unfinished work-plan items", () => {
    const leaf = listCapabilityLeaves().find((l) => l.id === "plan-resume");
    expect(leaf).toEqual({
      id: "plan-resume",
      label: "继续工作计划",
      saying: "按工作计划未完成项继续",
    });
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

describe("needsModelSetup", () => {
  it("local deploy with api base does not require an API key", () => {
    expect(
      needsModelSetup({
        api_base: "http://88.12.1.2:9081/v1",
        api_key_set: false,
        deployment_profile: "local",
      }),
    ).toBe(false);
  });

  it("local deploy without api base still needs setup", () => {
    expect(
      needsModelSetup({
        api_base: "",
        api_key_set: false,
        deployment_profile: "local",
      }),
    ).toBe(true);
  });

  it("standard deploy still requires an API key", () => {
    expect(
      needsModelSetup({
        api_base: "https://api.deepseek.com",
        api_key_set: false,
        deployment_profile: "standard",
      }),
    ).toBe(true);
    expect(
      needsModelSetup({
        api_base: "https://api.deepseek.com",
        api_key_set: true,
        deployment_profile: "standard",
      }),
    ).toBe(false);
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
