import { describe, expect, it } from "vitest";
import {
  BOOT_TIMEOUT_MS,
  bootPollInterval,
  shouldEmitHealthFail,
  shouldMarkDownDuringBoot,
} from "./bootHealth";

describe("bootHealth", () => {
  it("polls every 1s during boot window", () => {
    expect(bootPollInterval(0)).toBe(1000);
    expect(bootPollInterval(24_999)).toBe(1000);
  });
  it("polls every 8s after boot window", () => {
    expect(bootPollInterval(BOOT_TIMEOUT_MS)).toBe(8000);
  });
  it("marks down only after boot timeout while still failing", () => {
    expect(shouldMarkDownDuringBoot(5_000, false)).toBe(false);
    expect(shouldMarkDownDuringBoot(BOOT_TIMEOUT_MS, false)).toBe(true);
    expect(shouldMarkDownDuringBoot(BOOT_TIMEOUT_MS, true)).toBe(false);
  });
  it("emits health_fail only on transition into down", () => {
    expect(shouldEmitHealthFail("checking")).toBe(true);
    expect(shouldEmitHealthFail("ok")).toBe(true);
    expect(shouldEmitHealthFail("down")).toBe(false);
  });
});
