// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { dismissBootSplash } from "./bootSplash";

describe("dismissBootSplash", () => {
  beforeEach(() => {
    document.body.innerHTML =
      '<div id="boot-splash" class="boot-splash"><span>x</span></div>';
    vi.useFakeTimers();
  });
  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
  });

  it("adds done class then removes the node", () => {
    dismissBootSplash();
    const el = document.getElementById("boot-splash");
    expect(el?.classList.contains("boot-splash--done")).toBe(true);
    vi.advanceTimersByTime(250);
    expect(document.getElementById("boot-splash")).toBeNull();
  });

  it("is a no-op when splash missing", () => {
    document.body.innerHTML = "";
    expect(() => dismissBootSplash()).not.toThrow();
  });
});
