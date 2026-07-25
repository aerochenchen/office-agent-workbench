import { useState } from "react";
import type { SkillInspectResult, SkillMeta } from "../lib/types";
import { GUIDE_HINTS } from "../lib/guide";
import { isTauriRuntime, pickFolder, pickSkillFile } from "../lib/tauri";
import "./SkillPanel.css";

interface Props {
  skills: SkillMeta[];
  collapsed: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onInspect: (path: string) => Promise<SkillInspectResult>;
  onConfirmInstall: (path: string, enabled: boolean) => Promise<void>;
  onUninstall: (id: string) => Promise<void>;
  onRefresh: () => void;
}

function shortDesc(text: string, max = 72): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

export default function SkillPanel({
  skills,
  collapsed,
  onToggle,
  onInspect,
  onConfirmInstall,
  onUninstall,
  onRefresh,
}: Props) {
  const [pickMenuOpen, setPickMenuOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<SkillInspectResult | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<SkillMeta | null>(null);
  const [uninstalling, setUninstalling] = useState(false);

  async function beginPreview(path: string) {
    const trimmed = path.trim();
    if (!trimmed) return;
    setPickMenuOpen(false);
    setInstalling(true);
    setInstallError(null);
    setPreview(null);
    setPreviewPath(null);
    try {
      const result = await onInspect(trimmed);
      setPreview(result);
      setPreviewPath(trimmed);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "无法读取技能包");
    } finally {
      setInstalling(false);
    }
  }

  async function handlePickFolder() {
    const path = await pickFolder();
    if (path) await beginPreview(path);
  }

  async function handlePickFile() {
    const path = await pickSkillFile();
    if (path) await beginPreview(path);
  }

  async function confirmInstall(enable: boolean) {
    if (!previewPath) return;
    setInstalling(true);
    setInstallError(null);
    try {
      await onConfirmInstall(previewPath, enable);
      setPreview(null);
      setPreviewPath(null);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "安装失败");
    } finally {
      setInstalling(false);
    }
  }

  async function confirmUninstall() {
    if (!uninstallTarget) return;
    setUninstalling(true);
    setInstallError(null);
    try {
      await onUninstall(uninstallTarget.id);
      setUninstallTarget(null);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "卸载失败");
    } finally {
      setUninstalling(false);
    }
  }

  if (collapsed) {
    return <section className="pane skill-pane skill-pane--collapsed" aria-hidden="true" />;
  }

  return (
    <section className="pane skill-pane">
      <div className="pane-header">
        <span className="pane-title">技能</span>
        <button type="button" className="btn btn--ghost btn--xs" onClick={onRefresh}>
          刷新
        </button>
      </div>

      <div className="pane-body">
        {skills.length === 0 && (
          <div className="empty-hint">{GUIDE_HINTS.noSkills}</div>
        )}
        <ul className="skill-list">
          {skills.map((s) => {
            const title = s.display_name || s.name;
            return (
              <li key={s.id} className={`skill-card${s.enabled ? "" : " skill-card--off"}`}>
                <div className="skill-card-main">
                  <div className="skill-card-head">
                    <h3 className="skill-card-title">{title}</h3>
                    {s.tier === "heavy" ? (
                      <span
                        className="skill-card-meta"
                        title={s.min_ram_gb ? `建议内存 ≥ ${s.min_ram_gb}GB` : undefined}
                      >
                        增强
                      </span>
                    ) : null}
                  </div>
                  {s.description ? (
                    <p className="skill-card-desc" title={s.description}>
                      {shortDesc(s.description)}
                    </p>
                  ) : (
                    <p className="skill-card-desc skill-card-desc--empty">暂无简介</p>
                  )}
                </div>
                <div className="skill-card-actions">
                  <button
                    type="button"
                    className="btn btn--ghost btn--xs skill-uninstall-btn"
                    title={`卸载 ${title}`}
                    disabled={uninstalling}
                    onClick={() => setUninstallTarget(s)}
                  >
                    卸载
                  </button>
                  <label className="skill-switch" title={s.enabled ? "已启用" : "已停用"}>
                    <input
                      type="checkbox"
                      role="switch"
                      checked={s.enabled}
                      aria-label={`${title}：${s.enabled ? "已启用" : "已停用"}`}
                      onChange={(e) => onToggle(s.id, e.currentTarget.checked)}
                    />
                    <span className="skill-switch-ui" aria-hidden="true" />
                  </label>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {(isTauriRuntime() || installError) && (
        <div className="skill-install">
          {isTauriRuntime() ? (
            <div className="skill-install-actions">
              <button
                type="button"
                className="btn btn--ghost btn--full"
                disabled={installing}
                onClick={() => setPickMenuOpen((v) => !v)}
                aria-expanded={pickMenuOpen}
              >
                {installing ? "读取中…" : "导入技能"}
              </button>
              {pickMenuOpen && !installing && (
                <div className="skill-pick-menu" role="menu">
                  <button
                    type="button"
                    className="skill-pick-menu-item"
                    role="menuitem"
                    onClick={() => {
                      setPickMenuOpen(false);
                      void handlePickFolder();
                    }}
                  >
                    文件夹（含 SKILL.md）
                  </button>
                  <button
                    type="button"
                    className="skill-pick-menu-item"
                    role="menuitem"
                    onClick={() => {
                      setPickMenuOpen(false);
                      void handlePickFile();
                    }}
                  >
                    zip / md 文件
                  </button>
                </div>
              )}
            </div>
          ) : null}

          {installError && <p className="skill-install-error">{installError}</p>}
        </div>
      )}

      {preview && previewPath && (
        <div className="skill-preview-backdrop" role="presentation">
          <div className="skill-preview" role="dialog" aria-labelledby="skill-preview-title">
            <h3 id="skill-preview-title">确认导入技能</h3>
            <div className="skill-preview-card">
              <div className="skill-preview-card-title">
                {preview.skill.display_name || preview.skill.name}
              </div>
              <p className="skill-preview-card-desc">{preview.skill.description || "暂无简介"}</p>
              <div className="skill-preview-card-meta">
                <span>v{preview.skill.version}</span>
                <span>{preview.skill.tier === "heavy" ? "增强" : "标准"}</span>
                {preview.skill.tier === "heavy" && preview.skill.min_ram_gb ? (
                  <span>建议 ≥ {preview.skill.min_ram_gb}GB 内存</span>
                ) : null}
              </div>
            </div>
            {preview.validation.errors.length > 0 && (
              <ul className="skill-preview-validation skill-preview-validation--error" aria-label="校验错误">
                {preview.validation.errors.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {preview.validation.warnings.length > 0 && (
              <ul className="skill-preview-validation skill-preview-validation--warn" aria-label="校验警告">
                {preview.validation.warnings.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {preview.skill.tier === "heavy" && (
              <p className="skill-preview-warn">
                该技能依赖较重，可能占用更多内存与磁盘，请确认本机配置后再启用。
              </p>
            )}
            <p className="skill-preview-note">
              {preview.validation.errors.length > 0
                ? "技能包存在校验错误，请修正后重新导入。"
                : "将安装到本机技能区。可选择「安装并启用」，或仅安装稍后启用。"}
            </p>
            <div className="skill-preview-actions">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={installing}
                onClick={() => {
                  setPreview(null);
                  setPreviewPath(null);
                }}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn--ghost"
                disabled={installing || preview.validation.errors.length > 0}
                onClick={() => void confirmInstall(false)}
              >
                仅安装
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={installing || preview.validation.errors.length > 0}
                onClick={() => void confirmInstall(true)}
              >
                {installing ? "安装中…" : "安装并启用"}
              </button>
            </div>
          </div>
        </div>
      )}

      {uninstallTarget && (
        <div className="skill-preview-backdrop" role="presentation">
          <div className="skill-preview" role="dialog" aria-labelledby="skill-uninstall-title">
            <h3 id="skill-uninstall-title">确认卸载技能</h3>
            <p className="skill-preview-note">
              将永久删除「{uninstallTarget.display_name || uninstallTarget.name}」及其本地文件，此操作不可恢复。
            </p>
            <div className="skill-preview-actions">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={uninstalling}
                onClick={() => setUninstallTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={uninstalling}
                onClick={() => void confirmUninstall()}
              >
                {uninstalling ? "卸载中…" : "确认卸载"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
