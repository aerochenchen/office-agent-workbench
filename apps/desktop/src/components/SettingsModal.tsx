import { useEffect, useMemo, useState, type MouseEvent } from "react";
import {
  APP_NAME,
  APP_TAGLINE,
  APP_VERSION,
  OSS_CREDITS,
  STUDIO_NAME,
  STUDIO_WEBSITE_LABEL,
  STUDIO_WEBSITE_URL,
  SUPPORT_EMAIL,
} from "../lib/brand";
import { GUIDE_PILLARS } from "../lib/guide";
import type { PermissionMode, RuntimeConfig } from "../lib/types";
import { openHttpsUrl, readOssNoticeText } from "../lib/tauri";
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
import AiContentReportModal from "./AiContentReportModal";
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
  { value: "cautious", label: "谨慎", hint: "每次写入、跑脚本、读取未附加文件都需确认" },
  { value: "standard", label: "标准（默认）", hint: "首次确认后，同会话同操作可记住" },
  { value: "trust_workspace", label: "信任此文件夹", hint: "本会话内自动允许写入与跑技能脚本；工作区自定义脚本仍需单独开启" },
];

/** Common OpenAI-compatible model ids; unknown values fall back to「自定义」. */
const MODEL_PRESETS: ReadonlyArray<{ id: string; label: string }> = [
  { id: "deepseek-v4-flash", label: "DeepSeek V4 Flash" },
  { id: "deepseek-v4-pro", label: "DeepSeek V4 Pro" },
];

const MODEL_CUSTOM = "__custom__";

const MODEL_TAB_INTRO =
  "文书通不自带云模型。填写你自己的接口地址与密钥后即可对话；材料仍在本机。下列以 DeepSeek 为例便于开箱配置，也可换成单位内网或其它兼容接口。入口与步骤以各供应商官网当前说明为准。";

const MODEL_FIELD_HINTS = {
  model:
    "决定用哪套模型回答。DeepSeek 可选 Flash（更快）或 Pro（更强）；其它服务选「自定义」并填写对方提供的模型名。",
  apiBase:
    "模型服务地址。DeepSeek 官方为 https://api.deepseek.com；单位内网或其它服务请按对方说明填写（有的需带 /v1）。",
  apiKey:
    "访问该服务的密钥，仅保存在本机。DeepSeek：登录开放平台 → API Keys → 创建并复制后粘贴到此处。具体菜单名称与路径以官网为准。",
} as const;

function resolveModelPreset(modelName: string, localDeploy: boolean): string {
  if (localDeploy) return MODEL_CUSTOM;
  const trimmed = modelName.trim();
  if (MODEL_PRESETS.some((p) => p.id === trimmed)) return trimmed;
  return MODEL_CUSTOM;
}

export default function SettingsModal({ open, initial, onClose, onSave }: Props) {
  const [tab, setTab] = useState<SettingsTab>("model");
  const [apiBase, setApiBase] = useState(initial.api_base);
  const [apiKey, setApiKey] = useState(initial.api_key);
  const [model, setModel] = useState(initial.model);
  const isLocalDeploy = initial.deployment_profile === "local";
  const [modelPreset, setModelPreset] = useState(() =>
    resolveModelPreset(initial.model, initial.deployment_profile === "local"),
  );
  const [permissionMode, setPermissionMode] = useState<PermissionMode>(
    initial.permission_mode ?? "standard",
  );
  const [allowWorkspaceScripts, setAllowWorkspaceScripts] = useState(
    Boolean(initial.allow_workspace_scripts),
  );
  const [fontScale, setFontScale] = useState<UiFontScale>(() => readUiFontScale());
  const [uiTheme, setUiTheme] = useState<UiTheme>(() => readUiTheme());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [noticeBusy, setNoticeBusy] = useState(false);
  const [noticeError, setNoticeError] = useState<string | null>(null);
  const [noticeText, setNoticeText] = useState<string | null>(null);
  const [studioLinkError, setStudioLinkError] = useState<string | null>(null);
  const [reportOpen, setReportOpen] = useState(false);

  useEffect(() => {
    if (open) {
      setTab("model");
      setApiBase(initial.api_base);
      setApiKey(initial.api_key);
      setModel(initial.model);
      setModelPreset(resolveModelPreset(initial.model, initial.deployment_profile === "local"));
      setPermissionMode(initial.permission_mode ?? "standard");
      setAllowWorkspaceScripts(Boolean(initial.allow_workspace_scripts));
      setFontScale(readUiFontScale());
      setUiTheme(readUiTheme());
      setError(null);
      setNoticeError(null);
      setNoticeText(null);
      setStudioLinkError(null);
    }
  }, [open, initial]);

  const editable = tab === "appearance" || tab === "model" || tab === "permission";
  const viewingNotice = noticeText !== null;

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

  async function handleOpenNotice() {
    setNoticeBusy(true);
    setNoticeError(null);
    try {
      const text = await readOssNoticeText();
      setNoticeText(text);
    } catch (err) {
      setNoticeError(err instanceof Error ? err.message : "无法打开开源许可文件");
    } finally {
      setNoticeBusy(false);
    }
  }

  function handleCloseNotice() {
    setNoticeText(null);
    setNoticeError(null);
  }

  async function handleOpenStudioSite(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    setStudioLinkError(null);
    try {
      await openHttpsUrl(STUDIO_WEBSITE_URL);
    } catch (err) {
      setStudioLinkError(err instanceof Error ? err.message : "无法打开网站");
    }
  }

  function handleModelPresetChange(value: string) {
    setModelPreset(value);
    if (value !== MODEL_CUSTOM) {
      setModel(value);
    }
  }

  async function handleSave() {
    if (allowWorkspaceScripts && !initial.allow_workspace_scripts) {
      const ok = window.confirm(
        "开启后，助手可在工作区编写并运行临时 Python 程序，可能改动其中的文件。\n\n确定开启吗？",
      );
      if (!ok) {
        return;
      }
    }
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
        allow_workspace_scripts: allowWorkspaceScripts,
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
            <span>{viewingNotice ? "开源许可" : "设置"}</span>
          </div>
          <button type="button" className="btn btn--ghost btn--xs" onClick={viewingNotice ? handleCloseNotice : handleClose}>
            {viewingNotice ? "返回" : "关闭"}
          </button>
        </div>

        <div className="settings-layout">
          {!viewingNotice ? (
            <>
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
                <p className="settings-callout">
                  {initial.deployment_profile === "local"
                    ? "本地部署版本只连接本机或单位内网的模型服务。请填写内网地址（IP 或内网域名，如 http://127.0.0.1:8000/v1），公网 DeepSeek/OpenAI 等会被拒绝。"
                    : MODEL_TAB_INTRO}
                </p>

                {!isLocalDeploy && (
                  <div className="settings-field-block">
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
                    <p className="settings-field-hint">{MODEL_FIELD_HINTS.model}</p>
                  </div>
                )}

                {(isLocalDeploy || modelPreset === MODEL_CUSTOM) && (
                  <div className="settings-field-block">
                    <label className="field">
                      <span className="field-label">模型名称</span>
                      <input
                        className="field-input"
                        value={model}
                        onChange={(e) => setModel(e.currentTarget.value)}
                        placeholder={isLocalDeploy ? "内网服务提供的模型名" : "例如 deepseek-v4-flash"}
                      />
                    </label>
                    {isLocalDeploy && (
                      <p className="settings-field-hint">填写内网或本机 OpenAI 兼容服务给出的模型名。</p>
                    )}
                  </div>
                )}

                <div className="settings-subsection">
                  <h4 className="settings-subsection-title">连接设置</h4>

                  <div className="settings-field-block">
                    <label className="field">
                      <span className="field-label">API Base（接口地址）</span>
                      <input
                        className="field-input"
                        value={apiBase}
                        onChange={(e) => setApiBase(e.currentTarget.value)}
                        placeholder={
                          initial.deployment_profile === "local"
                            ? "http://127.0.0.1:8000/v1"
                            : "https://api.deepseek.com"
                        }
                      />
                    </label>
                    <p className="settings-field-hint">
                      {isLocalDeploy
                        ? "填写本机或单位内网地址（如 http://127.0.0.1:8000/v1 或专网 IP）。公网 DeepSeek/OpenAI 等会被拒绝。"
                        : MODEL_FIELD_HINTS.apiBase}
                    </p>
                  </div>

                  <div className="settings-field-block">
                    <label className="field">
                      <span className="field-label">API Key（密钥）</span>
                      <input
                        className="field-input"
                        type="password"
                        value={apiKey}
                        onChange={(e) => setApiKey(e.currentTarget.value)}
                        placeholder={
                          initial.api_key_set
                            ? `已保存 ${initial.api_key_masked || "***"}；留空不修改`
                            : isLocalDeploy
                              ? "可留空"
                              : "粘贴 API Key"
                        }
                      />
                    </label>
                    <p className="settings-field-hint">
                      {isLocalDeploy
                        ? "内网服务若不校验密钥可留空；填写后仅保存在本机。"
                        : MODEL_FIELD_HINTS.apiKey}
                    </p>
                  </div>
                </div>

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
                {initial.deployment_profile === "local" && (
                  <p className="settings-permission-hint">
                    本地部署版：模型地址限本机或内网；自定义脚本默认关闭，可手动开启。
                  </p>
                )}
                <label className="field field--checkbox">
                  <span className="field-label">允许运行工作区内的自定义脚本</span>
                  <input
                    type="checkbox"
                    checked={allowWorkspaceScripts}
                    onChange={(e) => setAllowWorkspaceScripts(e.currentTarget.checked)}
                  />
                </label>
                <p className="settings-permission-hint">
                  {allowWorkspaceScripts
                    ? "已开启：助手可在工作区写并运行临时脚本，能力更强，也可能改动工作区文件。技能脚本不受影响。"
                    : "默认关闭：助手不能自写自跑工作区脚本，复杂自动化会弱一些。技能功能不受影响。"}
                </p>
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
                  <div className="settings-about-studio">
                    {STUDIO_NAME}
                    <span className="settings-about-studio-sep" aria-hidden="true">
                      {" · "}
                    </span>
                    <a
                      className="settings-about-studio-link"
                      href={STUDIO_WEBSITE_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      aria-label={`${STUDIO_NAME}网站`}
                      onClick={(e) => void handleOpenStudioSite(e)}
                    >
                      {STUDIO_WEBSITE_LABEL}
                    </a>
                  </div>
                  {studioLinkError ? <p className="field-error">{studioLinkError}</p> : null}
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
                    本软件使用开源组件构建。上表为主要致谢；完整第三方清单与许可协议可点下方查看。
                  </p>
                  <button
                    type="button"
                    className="btn btn--ghost settings-about-notice-btn"
                    disabled={noticeBusy}
                    onClick={() => void handleOpenNotice()}
                  >
                    {noticeBusy ? "加载中…" : "查看开源许可"}
                  </button>
                  {noticeError ? <p className="field-error">{noticeError}</p> : null}
                </div>

                <div className="settings-about-report">
                  <div className="settings-about-oss-label">生成式 AI 内容</div>
                  <p className="settings-about-oss-lead">
                    助手回复由您配置的模型生成。若内容不当或有害，可向开发者举报（
                    {SUPPORT_EMAIL}）。
                  </p>
                  <button
                    type="button"
                    className="btn btn--ghost settings-about-notice-btn"
                    onClick={() => setReportOpen(true)}
                  >
                    举报不当 AI 内容
                  </button>
                </div>
              </section>
            )}
          </div>
            </>
          ) : (
            <div className="settings-notice-pane" role="region" aria-label="开源许可">
              {noticeError ? <p className="field-error">{noticeError}</p> : null}
              <pre className="settings-notice-text" tabIndex={0}>
                {noticeText}
              </pre>
            </div>
          )}
        </div>

        <div className="modal-footer">
          {viewingNotice ? (
            <button type="button" className="btn btn--ghost" onClick={handleCloseNotice}>
              返回关于
            </button>
          ) : (
            <>
              <button type="button" className="btn btn--ghost" onClick={handleClose}>
                {editable ? "取消" : "关闭"}
              </button>
              {editable ? (
                <button type="button" className="btn btn--primary" onClick={handleSave} disabled={saving}>
                  {saving ? "保存中…" : "保存"}
                </button>
              ) : null}
            </>
          )}
        </div>
      </div>
      <AiContentReportModal
        open={reportOpen}
        target={null}
        onClose={() => setReportOpen(false)}
      />
    </div>
  );
}
