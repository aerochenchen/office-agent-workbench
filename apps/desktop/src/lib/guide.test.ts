import { describe, expect, it } from "vitest";
import {
  FORBIDDEN_USER_TERMS,
  GUIDE_HINTS,
  GUIDE_PILLARS,
  MODEL_SETUP_REPLY,
} from "./guide";

function collectUserCopy(): string[] {
  return [
    ...GUIDE_PILLARS.flatMap((p) => [p.title, p.summary, p.body]),
    ...Object.values(GUIDE_HINTS),
    MODEL_SETUP_REPLY,
  ];
}

describe("guide copy", () => {
  it("does not expose forbidden terms to users", () => {
    const blob = collectUserCopy().join("\n");
    for (const term of FORBIDDEN_USER_TERMS) {
      expect(blob, `found forbidden term: ${term}`).not.toContain(term);
    }
  });

  it("MODEL_SETUP_REPLY guides user to settings and API key", () => {
    expect(MODEL_SETUP_REPLY).toMatch(/设置/);
    expect(MODEL_SETUP_REPLY).toMatch(/API|密钥|Key/i);
    expect(MODEL_SETUP_REPLY).toMatch(/模型/);
  });

  it("emptyChat invites chatting first", () => {
    expect(GUIDE_HINTS.emptyChat.length).toBeGreaterThan(8);
    expect(GUIDE_HINTS.emptyChat).toMatch(/问|聊|试/);
  });
});
