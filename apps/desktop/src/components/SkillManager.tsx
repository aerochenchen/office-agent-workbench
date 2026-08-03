import { useEffect, useState } from "react";
import type { SkillInspectResult, SkillMeta } from "../lib/types";
import {
  canUninstallSkill,
  isBundledSkill,
} from "../lib/skillUtils";
import { isTauriRuntime, pickFolder, pickSkillFile } from "../lib/tauri";
import "./SkillPanel.css";
import "./SkillManager.css";

export interface SkillManagerProps {
  open: boolean;
  skills: SkillMeta[];
  onClose: () => void;
  onToggle: (id: string, enabled: boolean) => void;
  onInspect: (path: string) => Promise<SkillInspectResult>;
  onConfirmInstall: (
    path: string,
    enabled: boolean,
    applyFixes?: boolean,
    forceOverwrite?: boolean,
  ) => Promise<void>;
  onUninstall: (id: string) => Promise<void>;
  onRestoreBundled: (id: string) => Promise<void>;
  onRefresh: () => void;
}

function shortDesc(text: string, max = 72): string {
  const t = text.trim().replace(/\s+/g, " ");
  if (t.length <= max) return t;
  return `${t.slice(0, max - 1)}…`;
}

function SkillManagerRow({
  skill,
  busy,
  onToggle,
  onUninstall,
  onRestore,
}: {
  skill: SkillMeta;
  busy: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onUninstall: (skill: SkillMeta) => void;
  onRestore: (skill: SkillMeta) => void;
}) {
  const title = skill.display_name || skill.name;
  const bundled = isBundledSkill(skill);
  const uninstallable = canUninstallSkill(skill);

  return (
    <li className={`skill-card${skill.enabled ? "" : " skill-card--off"}`}>
      <div className="skill-card-main">
        <div className="skill-card-head">
          <h3 className="skill-card-title">{title}</h3>
          {skill.version ? <span className="skill-card-version">v{skill.version}</span> : null}
          {bundled ? (
            <span className="skill-card-meta skill-card-meta--bundled" title="应用预置技能，不可卸载或导出">
              预置
            </span>
          ) : null}
          {bundled && skill.overridden ? (
            <span className="skill-card-meta skill-card-meta--overridden" title="已用本地包覆盖出厂版本">
              已本地更新
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
        {bundled ? (
          <button
            type="button"
            className="btn btn--ghost btn--xs"
            title={`恢复预置版本：${title}`}
            disabled={busy}
            onClick={() => onRestore(skill)}
          >
            恢复预置
          </button>
        ) : null}
        {uninstallable ? (
          <button
            type="button"
            className="btn btn--ghost btn--xs skill-uninstall-btn"
            title={`卸载 ${title}`}
            disabled={busy}
            onClick={() => onUninstall(skill)}
          >
            卸载
          </button>
        ) : null}
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
  onRestoreBundled,
  onRefresh,
}: SkillManagerProps) {
  const [pickMenuOpen, setPickMenuOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<SkillInspectResult | null>(null);
  const [forceOverwrite, setForceOverwrite] = useState(false);
  const [uninstallTarget, setUninstallTarget] = useState<SkillMeta | null>(null);
  const [restoreTarget, setRestoreTarget] = useState<SkillMeta | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  const enabledSkills = skills.filter((s) => s.enabled);
  const disabledSkills = skills.filter((s) => !s.enabled);
  const subDialogOpen = Boolean(preview || uninstallTarget || restoreTarget);

  useEffect(() => {
    if (!open) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "Escape") return;
      if (preview) {
        setPreview(null);
        setPreviewPath(null);
        setForceOverwrite(false);
        return;
      }
      if (uninstallTarget) {
        setUninstallTarget(null);
        return;
      }
      if (restoreTarget) {
        setRestoreTarget(null);
        return;
      }
      onClose();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, preview, uninstallTarget, restoreTarget, onClose]);

  useEffect(() => {
    if (!open) {
      setPickMenuOpen(false);
      setInstallError(null);
      setPreview(null);
      setPreviewPath(null);
      setForceOverwrite(false);
      setUninstallTarget(null);
      setRestoreTarget(null);
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
    setForceOverwrite(false);
    try {
      const result = await onInspect(trimmed);
      setPreview(result);
      setPreviewPath(trimmed);
      // Lower version over bundled requires explicit force; pre-check the box off.
      setForceOverwrite(false);
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

  async function confirmInstall(enable: boolean, applyFixes = false) {
    if (!previewPath) return;
    const replace = preview?.replace;
    if (replace?.requires_force && !forceOverwrite) {
      setInstallError("新包版本低于已安装的预置技能，请勾选「强制覆盖」后再安装");
      return;
    }
    setInstalling(true);
    setInstallError(null);
    try {
      await onConfirmInstall(previewPath, enable, applyFixes, forceOverwrite);
      setPreview(null);
      setPreviewPath(null);
      setForceOverwrite(false);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "安装失败");
    } finally {
      setInstalling(false);
    }
  }

  async function confirmUninstall() {
    if (!uninstallTarget) return;
    setActionBusy(true);
    setInstallError(null);
    try {
      await onUninstall(uninstallTarget.id);
      setUninstallTarget(null);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "卸载失败");
    } finally {
      setActionBusy(false);
    }
  }

  async function confirmRestore() {
    if (!restoreTarget) return;
    setActionBusy(true);
    setInstallError(null);
    try {
      await onRestoreBundled(restoreTarget.id);
      setRestoreTarget(null);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "恢复失败");
    } finally {
      setActionBusy(false);
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
                      busy={actionBusy}
                      onToggle={onToggle}
                      onUninstall={setUninstallTarget}
                      onRestore={setRestoreTarget}
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
                      busy={actionBusy}
                      onToggle={onToggle}
                      onUninstall={setUninstallTarget}
                      onRestore={setRestoreTarget}
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
            {preview.validation.errors.length > 0 && !preview.can_install_with_fixes && (
              <ul
                className="skill-preview-validation skill-preview-validation--error"
                aria-label="无法导入的问题"
              >
                {preview.validation.errors.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {(preview.auto_fixes?.length ?? 0) > 0 &&
              preview.validation.errors.length > 0 &&
              preview.can_install_with_fixes && (
              <ul
                className="skill-preview-validation skill-preview-validation--fix"
                aria-label="可自动修补"
              >
                {preview.auto_fixes!.map((msg) => (
                  <li key={msg}>{msg}</li>
                ))}
              </ul>
            )}
            {preview.validation.warnings.length > 0 &&
              !(preview.validation.errors.length > 0 && preview.can_install_with_fixes) && (
              <ul
                className="skill-preview-validation skill-preview-validation--warn"
                aria-label="规范提示"
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
            {preview.replace?.will_override_bundled ? (
              <p className="skill-preview-warn">
                将覆盖预置技能「{preview.replace.existing_id}」
                {preview.replace.existing_version
                  ? `（当前 v${preview.replace.existing_version} → 新包 v${preview.replace.incoming_version}）`
                  : `（新包 v${preview.replace.incoming_version}）`}
                。覆盖后可在列表中「恢复预置」。预置技能本身不可卸载、不可导出。
              </p>
            ) : null}
            {preview.replace?.requires_force ? (
              <label className="skill-preview-force">
                <input
                  type="checkbox"
                  checked={forceOverwrite}
                  onChange={(e) => setForceOverwrite(e.currentTarget.checked)}
                />
                强制覆盖（新包版本低于已安装版本）
              </label>
            ) : null}
            <p className="skill-preview-note">
              {preview.validation.errors.length > 0
                ? preview.can_install_with_fixes
                  ? "缺少部分可推断字段。可一键补全后导入（只写入本机技能区，不改动原文件）。"
                  : "技能包存在无法自动修补的问题，请按错误修正后重新导入。"
                : preview.validation.warnings.length > 0
                  ? "可以导入；下列为推荐规范提示，不影响安装。"
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
              {preview.validation.errors.length > 0 && preview.can_install_with_fixes ? (
                <>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={
                      installing ||
                      (Boolean(preview.replace?.requires_force) && !forceOverwrite)
                    }
                    onClick={() => void confirmInstall(false, true)}
                  >
                    修补并仅安装
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={
                      installing ||
                      (Boolean(preview.replace?.requires_force) && !forceOverwrite)
                    }
                    onClick={() => void confirmInstall(true, true)}
                  >
                    {installing ? "安装中…" : "修补并启用"}
                  </button>
                </>
              ) : (
                <>
                  <button
                    type="button"
                    className="btn btn--ghost"
                    disabled={
                      installing ||
                      preview.validation.errors.length > 0 ||
                      (Boolean(preview.replace?.requires_force) && !forceOverwrite)
                    }
                    onClick={() => void confirmInstall(false)}
                  >
                    仅安装
                  </button>
                  <button
                    type="button"
                    className="btn btn--primary"
                    disabled={
                      installing ||
                      preview.validation.errors.length > 0 ||
                      (Boolean(preview.replace?.requires_force) && !forceOverwrite)
                    }
                    onClick={() => void confirmInstall(true)}
                  >
                    {installing ? "安装中…" : "安装并启用"}
                  </button>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {uninstallTarget && (
        <div
          className="skill-preview-backdrop"
          role="presentation"
          onClick={() => {
            if (!actionBusy) setUninstallTarget(null);
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
            </p>
            <div className="skill-preview-actions">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={actionBusy}
                onClick={() => setUninstallTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={actionBusy}
                onClick={() => void confirmUninstall()}
              >
                {actionBusy ? "卸载中…" : "确认卸载"}
              </button>
            </div>
          </div>
        </div>
      )}

      {restoreTarget && (
        <div
          className="skill-preview-backdrop"
          role="presentation"
          onClick={() => {
            if (!actionBusy) setRestoreTarget(null);
          }}
        >
          <div
            className="skill-preview"
            role="dialog"
            aria-labelledby="skill-restore-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 id="skill-restore-title">恢复预置版本</h3>
            <p className="skill-preview-note">
              将用出厂预置包覆盖「{restoreTarget.display_name || restoreTarget.name}
              」的本机副本，本地更新会丢失。启用状态会保留。
            </p>
            <div className="skill-preview-actions">
              <button
                type="button"
                className="btn btn--ghost"
                disabled={actionBusy}
                onClick={() => setRestoreTarget(null)}
              >
                取消
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={actionBusy}
                onClick={() => void confirmRestore()}
              >
                {actionBusy ? "恢复中…" : "确认恢复"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
