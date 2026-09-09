// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from "vitest";

describe("revealMainWindow", () => {
  afterEach(() => {
    vi.resetModules();
    vi.unstubAllGlobals();
    vi.doUnmock("./tauri");
    vi.doUnmock("@tauri-apps/api/window");
  });

  it("is a no-op outside Tauri", async () => {
    vi.doMock("./tauri", () => ({ isTauriRuntime: () => false }));
    const { revealMainWindow } = await import("./revealWindow");
    await expect(revealMainWindow()).resolves.toBeUndefined();
  });

  it("calls show on the current window inside Tauri", async () => {
    const show = vi.fn().mockResolvedValue(undefined);
    vi.doMock("./tauri", () => ({ isTauriRuntime: () => true }));
    vi.doMock("@tauri-apps/api/window", () => ({
      getCurrentWindow: () => ({ show }),
    }));
    const { revealMainWindow } = await import("./revealWindow");
    await revealMainWindow();
    expect(show).toHaveBeenCalledTimes(1);
  });
});
