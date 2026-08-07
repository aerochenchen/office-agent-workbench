import { APP_NAME, APP_VERSION, SUPPORT_EMAIL } from "./brand";

export { SUPPORT_EMAIL };

export const AI_CONTENT_REPORT_SUBJECT = `[${APP_NAME}] 不当 AI 内容举报`;

/** Default max chars for assistant excerpt in the report body (plain text). */
export const DEFAULT_EXCERPT_MAX_CHARS = 800;

/**
 * Keep mailto under common OS / ShellExecute limits so the recipient is not dropped.
 * (Long percent-encoded Chinese bodies are a frequent cause of empty "To" fields.)
 */
export const MAX_MAILTO_URL_CHARS = 1400;

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

/** Plain-text report body (also copied to clipboard as a fallback). */
export function buildAiContentReportBody(input: AiContentReportMailtoInput): string {
  const version = input.appVersion ?? APP_VERSION;
  const maxExcerpt = input.maxExcerptChars ?? DEFAULT_EXCERPT_MAX_CHARS;
  const note = input.userNote.trim() || "（用户未填写说明）";
  const lines = [
    "我要举报文书通中不当或有问题的 AI 生成内容。",
    "",
    `收件人：${SUPPORT_EMAIL}`,
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
  return lines.join("\n");
}

function encodeMailto(email: string, subject: string, body: string): string {
  // Put the address in the path (required). Also set `to=` for clients that ignore the path.
  return `mailto:${email}?to=${encodeURIComponent(email)}&subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(body)}`;
}

/** Build a length-capped mailto: URL for reporting inappropriate generative AI output (Store 11.16). */
export function buildAiContentReportMailto(input: AiContentReportMailtoInput): string {
  let body = buildAiContentReportBody(input);
  let url = encodeMailto(SUPPORT_EMAIL, AI_CONTENT_REPORT_SUBJECT, body);

  // Shrink body until under the URL budget; never drop the recipient.
  while (url.length > MAX_MAILTO_URL_CHARS && body.length > 40) {
    body = truncateForMailto(body, Math.max(40, Math.floor(body.length * 0.7)));
    url = encodeMailto(SUPPORT_EMAIL, AI_CONTENT_REPORT_SUBJECT, body);
  }

  if (url.length > MAX_MAILTO_URL_CHARS) {
    // Last resort: address + subject only (To must still be filled).
    url = `mailto:${SUPPORT_EMAIL}?to=${encodeURIComponent(SUPPORT_EMAIL)}&subject=${encodeURIComponent(AI_CONTENT_REPORT_SUBJECT)}`;
  }

  return url;
}
