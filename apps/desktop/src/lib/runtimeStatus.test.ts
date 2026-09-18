import { describe, expect, it } from "vitest";
import { deriveRuntimeStatus, runtimeStatusLabel } from "./runtimeStatus";

describe("deriveRuntimeStatus", () => {
  it("stays checking while health is checking", () => {
    expect(
      deriveRuntimeStatus("checking", { configReady: true, needsConfig: false }),
    ).toBe("checking");
  });

  it("stays checking until config has loaded", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: false, needsConfig: true }),
    ).toBe("checking");
  });

  it("needs_config when runtime is up but model is not configured", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: true, needsConfig: true }),
    ).toBe("needs_config");
  });

  it("ok when runtime up and model is configured", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: true, needsConfig: false }),
    ).toBe("ok");
  });

  it("down when runtime unreachable", () => {
    expect(
      deriveRuntimeStatus("down", { configReady: true, needsConfig: false }),
    ).toBe("down");
  });
});

describe("runtimeStatusLabel", () => {
  it("maps statuses to Chinese labels", () => {
    expect(runtimeStatusLabel("ok")).toBe("就绪");
    expect(runtimeStatusLabel("needs_config")).toBe("待配置");
    expect(runtimeStatusLabel("down")).toBe("未就绪");
    expect(runtimeStatusLabel("checking")).toBe("启动中…");
  });
});
