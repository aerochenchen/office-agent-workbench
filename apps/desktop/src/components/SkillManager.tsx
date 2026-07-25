import { useEffect, useState } from "react";
import type { SkillInspectResult, SkillMeta } from "../lib/types";
import { isBundledSkillId } from "../lib/skillUtils";
import { isTauriRuntime, pickFolder, pickSkillFile } from "../lib/tauri";
import "./SkillPanel.css";
import "./SkillManager.css";

export interface SkillManagerProps {
  open: boolean;
  skills: SkillMeta[];
  onClose: () => void;
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

function SkillManagerRow({
  skill,
  uninstalling,
  onToggle,
  onUninstall,
}: {
  skill: SkillMeta;
  uninstalling: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onUninstall: (skill: SkillMeta) => void;
}) {
  const title = skill.display_name || skill.name;
  const bundled = isBundledSkillId(skill.id);

  return (
    <li className={`skill-card${skill.enabled ? "" : " skill-card--off"}`}>
      <div className="skill-card-main">
        <div className="skill-card-head">
          <h3 className="skill-card-title">{title}</h3>
          {skill.version ? <span className="skill-card-version">v{skill.version}</span> : null}
          {bundled ? (
            <span className="skill-card-meta skill-card-meta--bundled" title="应用预置技能">
              预置
            </span>
          ) : null}
          {skill.tier === "heavy" ? (
            <span
              className="skill-card-meta"
              title={skill.min_ram_gb ? `建议内存 ≥ ${skill.min_ram_gb}GB` : undefined}
            >
              增强
            </span>
          ) : null}
        </div>
        {skill.description ? (
          <p className="skill-card-desc" title={skill.description}>
            {shortDesc(skill.description)}
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
          onClick={() => onUninstall(skill)}
        >
          卸载
        </button>
        <label className="skill-switch" title={skill.enabled ? "已启用" : "已停用"}>
          <input
            type="checkbox"
            role="switch"
            checked={skill.enabled}
            aria-label={`${title}：${skill.enabled ? "已启用" : "已停用"}`}
            onChange={(e) => onToggle(skill.id, e.currentTarget.checked)}
          />
          <span className="skill-switch-ui" aria-hidden="true" />
        </label>
      </div>
    </li>
  );
}

export default function SkillManager({
  open,
  skills,
  onClose,
  onToggle,
  onInspect,
  onConfirmInstall,
  onUninstall,
  onRefresh,
}: SkillManagerProps) {
  const [pickMenuOpen, setPickMenuOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<SkillInspectResult | null>(null);
  const [uninstallTarget, setUninstallTarget] = useState<SkillMeta | null>(null);
  const [uninstalling, setUninstalling] = useState(false);

  const enabledSkills = skills.filter((s) => s.enabled);
  const disabledSkills = skills.filter((s) => !s.enabled);
  const subDialogOpen = Boolean(preview || uninstallTarget);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (preview) {
        setPreview(null);
        setPreviewPath(null);
        return;
      }
      if (uninstallTarget) {
        setUninstallTarget(null);
        return;
      }
      onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, preview, uninstallTarget, onClose]);

  useEffect(() => {
    if (!open) {
      setPickMenuOpen(false);
      setInstallError(null);
      setPreview(null);
      setPreviewPath(null);
      setUninstallTarget(null);
    }
  }, [open]);

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

  function handleBackdropClose() {
    if (subDialogOpen) return;
    onClose();
  }

  if (!open) return null;

  return (
    <>
      <div
        className="skill-manager-backdrop"
        role="presentation"
        onClick={handleBackdropClose}
      >
        <div
          className="skill-manager"
          role="dialog"
          aria-modal="true"
          aria-labelledby="skill-manager-title"
          onClick={(e) => e.stopPropagation()}
        >
          <header className="skill-manager-header">
            <h2 id="skill-manager-title" className="skill-manager-title">
              技能管理
            </h2>
            <div className="skill-manager-header-actions">
              <button type="button" className="btn btn--ghost btn--xs" onClick={onRefresh}>
                刷新
              </button>
              <button type="button" className="btn btn--ghost btn--xs" onClick={onClose}>
                关闭
              </button>
            </div>
          </header>

          <div className="skill-manager-body">
            <section className="skill-manager-section" aria-labelledby="skill-manager-enabled">
              <h3 id="skill-manager-enabled" className="skill-manager-section-title">
                已启用
              </h3>
              {enabledSkills.length === 0 ? (
                <p className="skill-manager-section-empty">暂无已启用技能</p>
              ) : (
                <ul className="skill-list">
                  {enabledSkills.map((s) => (
                    <SkillManagerRow
                      key={s.id}
                      skill={s}
                      uninstalling={uninstalling}
                      onToggle={onToggle}
                      onUninstall={setUninstallTarget}
                    />
                  ))}
                </ul>
              )}
            </section>

            <section className="skill-manager-section" aria-labelledby="skill-manager-disabled">
              <h3 id="skill-manager-disabled" className="skill-manager-section-title">
                已停用
              </h3>
              {disabledSkills.length === 0 ? (
                <p className="skill-manager-section-empty">暂无已停用技能</p>
              ) : (
                <ul className="skill-list">
                  {disabledSkills.map((s) => (
                    <SkillManagerRow
                      key={s.id}
                      skill={s}
                      uninstalling={uninstalling}
                      onToggle={onToggle}
                      onUninstall={setUninstallTarget}
                    />
                  ))}
                </ul>
              )}
            </section>
          </div>

          {(isTauriRuntime() || installError) && (
            <footer className="skill-manager-footer">
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
            </footer>
          )}
        </div>
      </div>

      {preview && previewPath && (
        <div
          className="skill-preview-backdrop"
          role="presentation"
          onClick={() => {
            if (!installing) {
              setPreview(null);
              setPreviewPath(null);
            }
          }}
        >
          <div
            className="skill-preview"
            role="dialog"
            aria-labelledby="skill-preview-title"
            onClick={(e) => e.stopPropagation()}
          >
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
              <ul
                className="skill-preview-validation skill-preview-validation--error"
                aria-label="校验错误"
              >
                {preview.validation.errors.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {preview.validation.warnings.length > 0 && (
              <ul
                className="skill-preview-validation skill-preview-validation--warn"
                aria-label="校验警告"
              >
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
        <div
          className="skill-preview-backdrop"
          role="presentation"
          onClick={() => {
            if (!uninstalling) setUninstallTarget(null);
          }}
        >
          <div
            className="skill-preview"
            role="dialog"
            aria-labelledby="skill-uninstall-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="skill-uninstall-title">确认卸载技能</h3>
            <p className="skill-preview-note">
              将永久删除「{uninstallTarget.display_name || uninstallTarget.name}
              」及其本地文件，此操作不可恢复。
              {isBundledSkillId(uninstallTarget.id)
                ? " 预置技能卸载后可经重新 seed 或重装应用包恢复。"
                : null}
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
    </>
  );
}
