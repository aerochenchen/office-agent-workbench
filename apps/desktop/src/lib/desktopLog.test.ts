import { describe, expect, it } from "vitest";
import { desktopLogLine } from "./desktopLog";

describe("desktopLogLine", () => {
  it("emits boot fields without token", () => {
    const line = desktopLogLine({
      event: "boot",
      bootId: "b1",
      extra: { token: "secret", version: "1.6.0" },
    });
    const row = JSON.parse(line);
    expect(row.event).toBe("boot");
    expect(row.boot_id).toBe("b1");
    expect(row.version).toBe("1.6.0");
    expect(JSON.stringify(row)).not.toContain("secret");
  });
});
