import { describe, expect, it } from "vitest";
import { sessionMessagesToChat } from "./sessionMessages";
import type { SessionUiMessage } from "./types";

describe("sessionMessagesToChat", () => {
  it("restores one done bubble per stored turn, including collapsed live steps", () => {
    const incoming: SessionUiMessage[] = [
      { role: "user", content: "分析现在有什么资料" },
      {
        role: "assistant",
        content: "已摸完底，下面把清单和发现写成文件。",
        live_steps: [
          {
            id: "c1",
            name: "workspace_list",
            label: "查看工作区",
            status: "ok",
            summary: ".",
          },
        ],
      },
    ];
    let n = 0;
    const chat = sessionMessagesToChat(incoming, () => {
      n += 1;
      return `m${n}`;
    });
    expect(chat).toEqual([
      { id: "m1", role: "user", content: "分析现在有什么资料" },
      {
        id: "m2",
        role: "assistant",
        content: "已摸完底，下面把清单和发现写成文件。",
        phase: "done",
        liveSteps: [
          {
            id: "c1",
            name: "workspace_list",
            label: "查看工作区",
            status: "ok",
            summary: ".",
          },
        ],
        stepsExpanded: false,
      },
    ]);
  });
});
