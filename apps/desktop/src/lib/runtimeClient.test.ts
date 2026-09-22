import { afterEach, describe, expect, it, vi } from "vitest";
import {
  authHeadersForPath,
  createSseDispatcher,
  formatSkillErrorDetail,
  getRuntimeApiToken,
  setRuntimeApiToken,
} from "./runtimeClient";

describe("authHeadersForPath", () => {
  afterEach(() => {
    setRuntimeApiToken(null);
  });

  it("returns empty headers when token unset", () => {
    setRuntimeApiToken(null);
    expect(authHeadersForPath("/config")).toEqual({});
  });

  it("adds Bearer for non-health paths", () => {
    setRuntimeApiToken("abc-123");
    expect(authHeadersForPath("/config")).toEqual({ Authorization: "Bearer abc-123" });
    expect(authHeadersForPath("/chat/stream")).toEqual({ Authorization: "Bearer abc-123" });
  });

  it("skips Bearer for /health", () => {
    setRuntimeApiToken("abc-123");
    expect(authHeadersForPath("/health")).toEqual({});
  });

  it("setRuntimeApiToken trims and stores token", () => {
    setRuntimeApiToken("  tok  ");
    expect(getRuntimeApiToken()).toBe("tok");
    setRuntimeApiToken("");
    expect(getRuntimeApiToken()).toBeNull();
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
