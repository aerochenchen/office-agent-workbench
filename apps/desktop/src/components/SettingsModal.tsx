import { useEffect, useMemo, useState } from "react";
import { APP_NAME, APP_TAGLINE, APP_VERSION, OSS_CREDITS } from "../lib/brand";
import { GUIDE_PILLARS } from "../lib/guide";
import type { PermissionMode, RuntimeConfig } from "../lib/types";
import {
  applyUiFontScale,
  applyUiTheme,
  readUiFontScale,
  readUiTheme,
  UI_FONT_SCALE_OPTIONS,
  UI_THEME_OPTIONS,
  writeUiFontScale,
  writeUiTheme,
  type UiFontScale,
  type UiTheme,
} from "../lib/uiPreferences";
import "./SettingsModal.css";

interface Props {
  open: boolean;
  initial: RuntimeConfig;
  onClose: () => void;
  onSave: (partial: Partial<RuntimeConfig>) => Promise<void>;
}

type SettingsTab = "appearance" | "model" | "permission" | "guide" | "about";

const SETTINGS_TABS: ReadonlyArray<{ id: SettingsTab; label: string }> = [
  { id: "appearance", label: "外观" },
  { id: "model", label: "模型" },
  { id: "permission", label: "权限与安全" },
  { id: "guide", label: "使用说明" },
  { id: "about", label: "关于" },
];

const PERMISSION_MODE_OPTIONS: { value: PermissionMode; label: string; hint: string }[] = [
  { value: "cautious", label: "谨慎", hint: "每次写入/跑脚本都需确认" },
  { value: "standard", label: "标准（默认）", hint: "首次确认后，同会话同操作可记住" },
  { value: "trust_workspace", label: "信任此文件夹", hint: "本会话内自动允许写入与跑脚本" },
];

/** Common OpenAI-compatible model ids; unknown values fall back to「自定义」. */
const MODEL_PRESETS: ReadonlyArray<{ id: string; label: string }> = [
  { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
  { id: "deepseek-chat", label: "DeepSeek Chat" },
  { id: "deepseek-reasoner", label: "DeepSeek Reasoner" },
];

const MODEL_CUSTOM = "__custom__";

function resolveModelPreset(modelName: string): string {
  const trimmed = modelName.trim();
  if (MODEL_PRESETS.some((p) => p.id === trimmed)) return trimmed;
  return MODEL_CUSTOM;
}

export default function SettingsModal({ open, initial, onClose, onSave }: Props) {
  const [tab, setTab] = useState<SettingsTab>("model");
  const [apiBase, setApiBase] = useState(initial.api_base);
  const [apiKey, setApiKey] = useState(initial.api_key);
  const [model, setModel] = useState(initial.model);
  const [modelPreset, setModelPreset] = useState(() => resolveModelPreset(initial.model));
  const [permissionMode, setPermissionMode] = useState<PermissionMode>(
    initial.permission_mode ?? "standard",
  );
  const [fontScale, setFontScale] = useState<UiFontScale>(() => readUiFontScale());
  const [uiTheme, setUiTheme] = useState<UiTheme>(() => readUiTheme());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (open) {
      setTab("model");
      setApiBase(initial.api_base);
      setApiKey(initial.api_key);
      setModel(initial.model);
      setModelPreset(resolveModelPreset(initial.model));
      setPermissionMode(initial.permission_mode ?? "standard");
      setFontScale(readUiFontScale());
      setUiTheme(readUiTheme());
      setError(null);
    }
  }, [open, initial]);

  const editable = tab === "appearance" || tab === "model" || tab === "permission";

  const permissionHint = useMemo(
    () => PERMISSION_MODE_OPTIONS.find((o) => o.value === permissionMode)?.hint,
    [permissionMode],
  );

  if (!open) return null;

  function handleClose() {
    applyUiFontScale(readUiFontScale());
    applyUiTheme(readUiTheme());
    onClose();
  }

  function handleFontScaleChange(next: UiFontScale) {
    setFontScale(next);
    applyUiFontScale(next);
  }

  function handleThemeChange(next: UiTheme) {
    setUiTheme(next);
    applyUiTheme(next);
  }

  function handleModelPresetChange(value: string) {
    setModelPreset(value);
    if (value !== MODEL_CUSTOM) {
      setModel(value);
    }
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      writeUiFontScale(fontScale);
      applyUiFontScale(fontScale);
      writeUiTheme(uiTheme);
      applyUiTheme(uiTheme);
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
      await onSave(partial);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="modal-overlay" role="dialog" aria-modal="true" aria-label="设置">
      <div className="modal modal--settings">
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
          <button type="button" className="btn btn--ghost btn--xs" onClick={handleClose}>
            关闭
          </button>
        </div>

        <div className="settings-layout">
          <nav className="settings-nav" aria-label="设置分类">
            {SETTINGS_TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`settings-nav-item${tab === item.id ? " settings-nav-item--active" : ""}`}
                aria-current={tab === item.id ? "page" : undefined}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </nav>

          <div className="settings-pane modal-body">
            {tab === "appearance" && (
              <section className="settings-section" aria-labelledby="settings-appearance-title">
                <h3 id="settings-appearance-title" className="settings-section-title">
                  外观
                </h3>
                <label className="field">
                  <span className="field-label">界面主题</span>
                  <select
                    className="field-input"
                    value={uiTheme}
                    onChange={(e) => handleThemeChange(e.currentTarget.value as UiTheme)}
                  >
                    {UI_THEME_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="settings-permission-hint">
                  {UI_THEME_OPTIONS.find((o) => o.value === uiTheme)?.hint}
                  。切换后即时预览，点保存后记住偏好。
                </p>
                <label className="field">
                  <span className="field-label">界面文字大小</span>
                  <select
                    className="field-input"
                    value={fontScale}
                    onChange={(e) => handleFontScaleChange(e.currentTarget.value as UiFontScale)}
                  >
                    {UI_FONT_SCALE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                </label>
                <p className="settings-permission-hint">
                  {UI_FONT_SCALE_OPTIONS.find((o) => o.value === fontScale)?.hint}
                  。切换后即时预览，点保存后记住偏好。
                </p>
              </section>
            )}

            {tab === "model" && (
              <section className="settings-section" aria-labelledby="settings-model-title">
                <h3 id="settings-model-title" className="settings-section-title">
                  模型
                </h3>

                <label className="field">
                  <span className="field-label">选用模型</span>
                  <select
                    className="field-input"
                    value={modelPreset}
                    onChange={(e) => handleModelPresetChange(e.currentTarget.value)}
                  >
                    {MODEL_PRESETS.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.label}
                      </option>
                    ))}
                    <option value={MODEL_CUSTOM}>自定义…</option>
                  </select>
                </label>

                {modelPreset === MODEL_CUSTOM && (
                  <label className="field">
                    <span className="field-label">模型名称</span>
                    <input
                      className="field-input"
                      value={model}
                      onChange={(e) => setModel(e.currentTarget.value)}
                      placeholder="例如 deepseek-chat"
                    />
                  </label>
                )}

                <h4 className="settings-subsection-title">连接设置</h4>

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

                {error && <p className="field-error">{error}</p>}
              </section>
            )}

            {tab === "permission" && (
              <section className="settings-section" aria-labelledby="settings-permission-title">
                <h3 id="settings-permission-title" className="settings-section-title">
                  权限与安全
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
                <p className="settings-permission-hint">{permissionHint}</p>
              </section>
            )}

            {tab === "guide" && (
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
            )}

            {tab === "about" && (
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
                    完整第三方清单与许可文本见发版包根目录的 NOTICE 文件（由
                    scripts/generate_notice.sh 生成）。
                  </p>
                </div>
              </section>
            )}
          </div>
        </div>

        <div className="modal-footer">
          <button type="button" className="btn btn--ghost" onClick={handleClose}>
            {editable ? "取消" : "关闭"}
          </button>
          {editable ? (
            <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
              {saving ? "保存中…" : "保存"}
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
