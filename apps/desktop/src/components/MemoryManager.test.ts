import { describe, expect, it } from "vitest";
import { habitFromLine, habitLine } from "./MemoryManager";

describe("habitLine", () => {
  it("shows only the sentence, never topic：text", () => {
    expect(habitLine({ topic: "语气", text: "少问确认，直接做" })).toBe(
      "少问确认，直接做",
    );
  });
});

describe("habitFromLine", () => {
  it("keeps the whole sentence as text", () => {
    const h = habitFromLine("少问确认，直接做", new Set());
    expect(h.text).toBe("少问确认，直接做");
    expect(h.topic).toBe("少问确认，直接做".slice(0, 12));
  });

  it("does not split on colon", () => {
    const h = habitFromLine("语气：少确认", new Set());
    expect(h.text).toBe("语气：少确认");
  });

  it("dedupes internal topic key", () => {
    const first = "少问确认，直接做";
    const h = habitFromLine(first, new Set([first.slice(0, 12)]));
    expect(h.text).toBe(first);
    expect(h.topic).toBe(`${first.slice(0, 12)}2`);
  });
});
