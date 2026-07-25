import { useEffect, useState } from "react";
import { APP_NAME, APP_TAGLINE, APP_VERSION, OSS_CREDITS } from "../lib/brand";
import { GUIDE_PILLARS } from "../lib/guide";
import type { PermissionMode, RuntimeConfig } from "../lib/types";
import "./SettingsModal.css";

interface Props {
  open: boolean;
  initial: RuntimeConfig;
  onClose: () => void;
  onSave: (partial: Partial<RuntimeConfig>) => Promise<void>;
}

const PERMISSION_MODE_OPTIONS: { value: PermissionMode; label: string; hint: string }[] = [
  { value: "cautious", label: "谨慎", hint: "每次写入/跑脚本都需确认" },
  { value: "standard", label: "标准（默认）", hint: "首次确认后，同会话同操作可记住" },
  { value: "trust_workspace", label: "信任工作区", hint: "本会话内自动允许写入与跑脚本" },
];

export default function SettingsModal({ open, initial, onClose, onSave }: Props) {
  const [apiBase, setApiBase] = useState(initial.api_base);
  const [apiKey, setApiKey] = useState(initial.api_key);
  const [model, setModel] = useState(initial.model);
  const [permissionMode, setPermissionMode] = useState<PermissionMode>(
    initial.permission_mode ?? "standard",
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setApiBase(initial.api_base);
      setApiKey(initial.api_key);
      setModel(initial.model);
      setPermissionMode(initial.permission_mode ?? "standard");
      setError(null);
    }
  }, [open, initial]);

  if (!open) return null;

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const partial: Partial<RuntimeConfig> = {
        api_base: apiBase.trim(),
        model: model.trim(),
        permission_mode: permissionMode,
      };
      const trimmedKey = apiKey.trim();
      if (trimmedKey) {
        partial.api_key = trimmedKey;
      } else if (!initial.api_key_set) {
        partial.api_key = "";
      }
      // api_key_set && 空输入 → 不传 api_key，保留服务端原值
      await onSave(partial);
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
                placeholder={
                  initial.api_key_set
                    ? `已保存 ${initial.api_key_masked || "***"}；留空不修改`
                    : "粘贴 API Key"
                }
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

            {error && <p className="field-error">{error}</p>}
          </section>

          <section className="settings-section" aria-labelledby="settings-permission-title">
            <h3 id="settings-permission-title" className="settings-section-title">
              权限模式
            </h3>
            <label className="field">
              <span className="field-label">工具确认策略</span>
              <select
                className="field-input"
                value={permissionMode}
                onChange={(e) => setPermissionMode(e.currentTarget.value as PermissionMode)}
              >
                {PERMISSION_MODE_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
            <p className="settings-permission-hint">
              {PERMISSION_MODE_OPTIONS.find((o) => o.value === permissionMode)?.hint}
            </p>
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
                完整第三方清单与许可文本见发版包根目录的 NOTICE 文件（由 scripts/generate_notice.sh 生成）。
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
