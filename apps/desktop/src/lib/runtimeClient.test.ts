import { afterEach, describe, expect, it, vi } from "vitest";
import {
  createSseDispatcher,
  formatSkillErrorDetail,
  runtimeLogHint,
} from "./runtimeClient";

describe("runtimeLogHint", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns Windows temp log path on Windows UA", () => {
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Windows NT 10.0)" });
    expect(runtimeLogHint()).toBe("%TEMP%\\office-agent-desktop.log");
  });

  it("returns generic temp hint on non-Windows", () => {
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Macintosh)" });
    expect(runtimeLogHint()).toContain("office-agent-desktop.log");
  });
});

describe("formatSkillErrorDetail", () => {
  it("joins validation errors and warnings", () => {
    const msg = formatSkillErrorDetail({
      validation: { errors: ["缺少 name"], warnings: ["版本未锁定"] },
    });
    expect(msg).toContain("缺少 name");
    expect(msg).toContain("警告：版本未锁定");
  });
});

describe("createSseDispatcher", () => {
  it("parses started event with turn_id", () => {
    const onStarted = vi.fn();
    const { dispatchBlock, outcome } = createSseDispatcher({ onStarted });
    dispatchBlock('event: started\ndata: {"session_id":"sess-1","turn_id":"turn-abc"}\n');
    expect(onStarted).toHaveBeenCalledWith("sess-1", "turn-abc");
    expect(outcome.sawAny).toBe(true);
  });

  it("omits turn_id when not a string", () => {
    const onStarted = vi.fn();
    const { dispatchBlock } = createSseDispatcher({ onStarted });
    dispatchBlock('event: started\ndata: {"session_id":"sess-1","turn_id":123}\n');
    expect(onStarted).toHaveBeenCalledWith("sess-1", undefined);
  });

  it("parses tool_start with turn_id", () => {
    const onToolStart = vi.fn();
    const { dispatchBlock } = createSseDispatcher({ onToolStart });
    dispatchBlock(
      'event: tool_start\ndata: {"id":"1","name":"read_file","turn_id":"turn-xyz"}\n',
    );
    expect(onToolStart).toHaveBeenCalledWith(
      expect.objectContaining({ id: "1", name: "read_file", turn_id: "turn-xyz" }),
    );
  });

  it("ignores blocks with invalid JSON", () => {
    const onError = vi.fn();
    const { dispatchBlock, outcome } = createSseDispatcher({ onError });
    dispatchBlock("event: error\ndata: not-json\n");
    expect(onError).not.toHaveBeenCalled();
    expect(outcome.sawAny).toBe(false);
  });
});
