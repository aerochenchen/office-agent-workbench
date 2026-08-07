import { APP_NAME, APP_VERSION, SUPPORT_EMAIL } from "./brand";

export { SUPPORT_EMAIL };

export const AI_CONTENT_REPORT_SUBJECT = `[${APP_NAME}] 不当 AI 内容举报`;

/** Default max chars for assistant excerpt embedded in mailto body. */
export const DEFAULT_EXCERPT_MAX_CHARS = 1200;

export function truncateForMailto(text: string, maxChars: number): string {
  if (text.length <= maxChars) return text;
  return `${text.slice(0, Math.max(0, maxChars))}…`;
}

export interface AiContentReportMailtoInput {
  userNote: string;
  appVersion?: string;
  assistantExcerpt?: string | null;
  maxExcerptChars?: number;
}

/** Build a mailto: URL for reporting inappropriate generative AI output (Store 11.16). */
export function buildAiContentReportMailto(input: AiContentReportMailtoInput): string {
  const version = input.appVersion ?? APP_VERSION;
  const maxExcerpt = input.maxExcerptChars ?? DEFAULT_EXCERPT_MAX_CHARS;
  const note = input.userNote.trim() || "（用户未填写说明）";
  const lines = [
    "我要举报文书通中不当或有问题的 AI 生成内容。",
    "",
    `说明：${note}`,
    `版本：${version}`,
  ];
  if (input.assistantExcerpt != null && input.assistantExcerpt.trim()) {
    lines.push(
      "",
      "助手回复摘要：",
      truncateForMailto(input.assistantExcerpt.trim(), maxExcerpt),
    );
  }
  lines.push("", "请开发者查收并采取适当处理。");
  const body = lines.join("\n");
  return `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent(AI_CONTENT_REPORT_SUBJECT)}&body=${encodeURIComponent(body)}`;
}
