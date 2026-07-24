import { useEffect, useState } from "react";
import type { RuntimeConfig } from "../lib/types";
import "./SettingsModal.css";

interface Props {
  open: boolean;
  initial: RuntimeConfig;
  onClose: () => void;
  onSave: (partial: Partial<RuntimeConfig>) => Promise<void>;
}

export default function SettingsModal({ open, initial, onClose, onSave }: Props) {
  const [apiBase, setApiBase] = useState(initial.api_base);
  const [apiKey, setApiKey] = useState(initial.api_key);
  const [model, setModel] = useState(initial.model);
  const [allowedHosts, setAllowedHosts] = useState(initial.allowed_hosts.join(", "));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setApiBase(initial.api_base);
      setApiKey(initial.api_key);
      setModel(initial.model);
      setAllowedHosts(initial.allowed_hosts.join(", "));
      setError(null);
    }
  }, [open, initial]);

  if (!open) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      await onSave({
        api_base: apiBase.trim(),
        api_key: apiKey,
        model: model.trim(),
        allowed_hosts: allowedHosts
          .split(",")
          .map((h) => h.trim())
          .filter(Boolean),
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true">
      <div className="modal">
        <div className="modal-header">
          <span>模型网关设置</span>
          <button type="button" className="btn btn--ghost btn--xs" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="modal-body">
          <label className="field">
            <span className="field-label">API Base</span>
            <input
              className="field-input"
              value={apiBase}
              onChange={(e) => setApiBase(e.currentTarget.value)}
              placeholder="http://127.0.0.1:8000/v1"
            />
          </label>

          <label className="field">
            <span className="field-label">API Key</span>
            <input
              className="field-input"
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.currentTarget.value)}
            />
          </label>

          <label className="field">
            <span className="field-label">模型</span>
            <input
              className="field-input"
              value={model}
              onChange={(e) => setModel(e.currentTarget.value)}
            />
          </label>

          <label className="field">
            <span className="field-label">允许的主机（逗号分隔）</span>
            <input
              className="field-input"
              value={allowedHosts}
              onChange={(e) => setAllowedHosts(e.currentTarget.value)}
              placeholder="127.0.0.1, localhost"
            />
          </label>

          {error && <p className="field-error">{error}</p>}

          <p className="settings-notice">
            关于 / NOTICE：桌面壳基于 Tauri（Apache-2.0 / MIT）与 React；本地 Python 运行时主要使用
            FastAPI（MIT）、openai SDK（Apache-2.0）等宽松开源组件。完整第三方清单见发版包 NOTICE。
          </p>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn--ghost" onClick={onClose}>
            取消
          </button>
          <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
            {saving ? "保存中…" : "保存"}
          </button>
        </div>
      </div>
    </div>
  );
}
