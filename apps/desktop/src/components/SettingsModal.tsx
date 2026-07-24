import { useEffect, useState } from "react";
import { APP_NAME, APP_TAGLINE, APP_VERSION, OSS_CREDITS } from "../lib/brand";
import { GUIDE_PILLARS } from "../lib/guide";
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
          <div className="modal-header-brand">
            <img
              className="modal-logo"
              src="/logo-mark.png"
              width={20}
              height={20}
              alt=""
              aria-hidden="true"
            />
            <span>设置</span>
          </div>
          <button type="button" className="btn btn--ghost btn--xs" onClick={onClose}>
            关闭
          </button>
        </div>

        <div className="modal-body">
          <section className="settings-section" aria-labelledby="settings-gateway-title">
            <h3 id="settings-gateway-title" className="settings-section-title">
              模型网关
            </h3>

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
          </section>

          <section className="settings-guide" aria-labelledby="settings-guide-title">
            <h3 id="settings-guide-title" className="settings-section-title">
              使用说明
            </h3>
            <ul className="settings-guide-list">
              {GUIDE_PILLARS.map((p) => (
                <li key={p.id} className="settings-guide-item">
                  <div className="settings-guide-item-title">{p.title}</div>
                  <p className="settings-guide-item-body">{p.body}</p>
                </li>
              ))}
            </ul>
          </section>

          <section className="settings-about" aria-labelledby="settings-about-title">
            <h3 id="settings-about-title" className="settings-section-title">
              关于
            </h3>
            <div className="settings-about-product">
              <div className="settings-about-name">{APP_NAME}</div>
              <div className="settings-about-tagline">{APP_TAGLINE}</div>
              <div className="settings-about-version">版本 {APP_VERSION}</div>
            </div>

            <div className="settings-about-oss">
              <div className="settings-about-oss-label">开源致谢</div>
              <p className="settings-about-oss-lead">
                本产品基于以下开源组件构建（及更多依赖）：
              </p>
              <ul className="settings-about-oss-list">
                {OSS_CREDITS.map((item) => (
                  <li key={item.name}>
                    <span className="settings-about-oss-name">{item.name}</span>
                    <span className="settings-about-oss-license">{item.license}</span>
                  </li>
                ))}
              </ul>
              <p className="settings-about-oss-note">
                完整第三方清单与许可文本见发版包中的 NOTICE 文件。
              </p>
            </div>
          </section>
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
