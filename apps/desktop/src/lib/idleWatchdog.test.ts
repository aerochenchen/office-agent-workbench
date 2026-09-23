import { afterEach, describe, expect, it, vi } from "vitest";
import { createIdleWatchdog } from "./idleWatchdog";

describe("createIdleWatchdog", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("does not fire before idleMs, fires after, and bump resets the window", () => {
    vi.useFakeTimers();
    const onIdle = vi.fn();
    const w = createIdleWatchdog(1_000, onIdle);
    vi.advanceTimersByTime(999);
    expect(onIdle).not.toHaveBeenCalled();
    w.bump();
    vi.advanceTimersByTime(999);
    expect(onIdle).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1);
    expect(onIdle).toHaveBeenCalledTimes(1);
    w.stop();
  });

  it("stop prevents a pending idle fire", () => {
    vi.useFakeTimers();
    const onIdle = vi.fn();
    const w = createIdleWatchdog(1_000, onIdle);
    vi.advanceTimersByTime(500);
    w.stop();
    vi.advanceTimersByTime(5_000);
    expect(onIdle).not.toHaveBeenCalled();
  });
});
