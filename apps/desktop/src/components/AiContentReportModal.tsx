import { useEffect, useId, useState } from "react";
import { APP_VERSION, SUPPORT_EMAIL } from "../lib/brand";
import {
  buildAiContentReportBody,
  buildAiContentReportMailto,
} from "../lib/aiContentReport";
import { openMailto } from "../lib/tauri";
import "./AiContentReportModal.css";

export interface AiContentReportTarget {
  /** Optional assistant message text to embed (truncated) in the mail body. */
  assistantExcerpt?: string | null;
}

interface Props {
  open: boolean;
  target: AiContentReportTarget | null;
  onClose: () => void;
}

export default function AiContentReportModal({ open, target, onClose }: Props) {
  const titleId = useId();
  const noteId = useId();
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setNote("");
    setBusy(false);
    setStatus(null);
    setError(null);
  }, [open, target]);

  if (!open) return null;

  const handleSubmit = async () => {
    setBusy(true);
    setError(null);
    setStatus(null);
    const payload = {
      userNote: note,
      appVersion: APP_VERSION,
      assistantExcerpt: target?.assistantExcerpt,
    };
    const body = buildAiContentReportBody(payload);
    const url = buildAiContentReportMailto(payload);

    try {
      await navigator.clipboard.writeText(
        `收件人：${SUPPORT_EMAIL}\n主题：文书通 AI 内容举报\n\n${body}`,
      );
    } catch {
      // Clipboard is best-effort; mail open still proceeds.
    }

    try {
      await openMailto(url);
      setStatus(
        `已打开邮件客户端。收件人应为 ${SUPPORT_EMAIL}；若为空，请粘贴剪贴板内容或手动填写该邮箱后发送。`,
      );
    } catch {
      setError(
        `无法打开邮件客户端。请手动发信至 ${SUPPORT_EMAIL}（举报正文已尽量复制到剪贴板）。`,
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="modal-overlay ai-report-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby={titleId}
    >
      <div className="modal ai-report-modal">
        <div className="modal-header">
          <span id={titleId}>举报不当 AI 内容</span>
        </div>
        <div className="modal-body">
          <p className="ai-report-lead">
            若助手生成的内容不当、有害或违反使用规范，可通过邮件向开发者举报。我们会根据举报采取适当处理。
          </p>
          <div className="ai-report-recipient">
            <span className="field-label">举报邮箱</span>
            <div className="ai-report-recipient-value" aria-label="举报邮箱">
              {SUPPORT_EMAIL}
            </div>
          </div>
          <label className="field-label" htmlFor={noteId}>
            说明（可选）
          </label>
          <textarea
            id={noteId}
            className="ai-report-note"
            rows={4}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="简述问题，例如：含不当言论、误导信息…"
            disabled={busy}
          />
          {status ? <p className="ai-report-status">{status}</p> : null}
          {error ? <p className="field-error">{error}</p> : null}
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn--ghost" onClick={onClose} disabled={busy}>
            {status ? "关闭" : "取消"}
          </button>
          {!status ? (
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void handleSubmit()}
              disabled={busy}
            >
              {busy ? "打开中…" : "打开邮件举报"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
