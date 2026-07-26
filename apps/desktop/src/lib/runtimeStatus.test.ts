import { describe, expect, it } from "vitest";
import { deriveRuntimeStatus, runtimeStatusLabel } from "./runtimeStatus";

describe("deriveRuntimeStatus", () => {
  it("stays checking while health is checking", () => {
    expect(
      deriveRuntimeStatus("checking", { configReady: true, apiKeySet: true }),
    ).toBe("checking");
  });

  it("stays checking until config has loaded", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: false, apiKeySet: false }),
    ).toBe("checking");
  });

  it("needs_config when runtime is up but API key missing", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: true, apiKeySet: false }),
    ).toBe("needs_config");
  });

  it("ok only when runtime up and API key set", () => {
    expect(
      deriveRuntimeStatus("ok", { configReady: true, apiKeySet: true }),
    ).toBe("ok");
  });

  it("down when runtime unreachable", () => {
    expect(
      deriveRuntimeStatus("down", { configReady: true, apiKeySet: true }),
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
