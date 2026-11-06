import type { ChatMessage, SessionUiMessage } from "./types";

export function sessionMessagesToChat(
  messages: SessionUiMessage[],
  nextId: () => string,
): ChatMessage[] {
  return messages.map((m) => {
    if (m.role === "user") {
      return {
        id: nextId(),
        role: "user",
        content: m.content,
        ...(m.attachments && m.attachments.length > 0 ? { attachments: m.attachments } : {}),
      };
    }
    const steps = (m.live_steps ?? []).map((step) => ({
      id: step.id,
      name: step.name,
      label: step.label,
      status: step.status,
      summary: step.summary,
    }));
    return {
      id: nextId(),
      role: "assistant",
      content: m.content,
      phase: "done",
      ...(steps.length > 0 ? { liveSteps: steps } : {}),
      stepsExpanded: false,
    };
  });
}
