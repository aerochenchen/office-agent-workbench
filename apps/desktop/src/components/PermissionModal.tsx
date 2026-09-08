import type { PermissionRequestEvent } from "../lib/types";
import "./PermissionModal.css";

interface Props {
  request: PermissionRequestEvent | null;
  busy?: boolean;
  onAllow: () => void;
  onDeny: () => void;
}

export default function PermissionModal({ request, busy, onAllow, onDeny }: Props) {
  if (!request) return null;

  const destination = request.destination?.trim();
  const path = request.path?.trim();
  const isRead = request.tool === "workspace_read" || request.tool === "workspace_extract";

  return (
    <div className="modal-overlay permission-overlay" role="dialog" aria-modal="true">
      <div className="modal permission-modal">
        <div className="modal-header">
          <span>需要确认操作</span>
        </div>
        <div className="modal-body">
          <p className="permission-lead">
            {isRead
              ? "智能体要读取下列文件，内容会发送给当前配置的模型服务。请确认是否允许："
              : "智能体请求执行以下操作，请确认是否允许："}
          </p>
          <dl className="permission-meta">
            <div>
              <dt>工具</dt>
              <dd>
                <code>{request.tool}</code>
              </dd>
            </div>
            {path ? (
              <div>
                <dt>路径</dt>
                <dd>
                  <code>{path}</code>
                </dd>
              </div>
            ) : null}
            <div>
              <dt>摘要</dt>
              <dd>{request.summary || "（无摘要）"}</dd>
            </div>
            {destination ? (
              <div>
                <dt>数据去向</dt>
                <dd>
                  将发送至模型主机 <code>{destination}</code>
                </dd>
              </div>
            ) : null}
          </dl>
        </div>
        <div className="modal-footer">
          <button type="button" className="btn btn--ghost" onClick={onDeny} disabled={busy}>
            拒绝
          </button>
          <button type="button" className="btn btn--primary" onClick={onAllow} disabled={busy}>
            {busy ? "提交中…" : "允许"}
          </button>
        </div>
      </div>
    </div>
  );
}
