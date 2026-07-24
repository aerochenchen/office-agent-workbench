import { useState, type FormEvent } from "react";
import type { SkillInspect, SkillMeta } from "../lib/types";
import { isTauriRuntime, pickFolder, pickSkillFile } from "../lib/tauri";
import "./SkillPanel.css";

const PERMISSION_LABELS: Record<string, string> = {
  workspace_list: "列出工作区文件",
  workspace_read: "读取工作区文件",
  workspace_write: "写入工作区文件",
  run_python: "运行 Python 脚本",
  run_skill_script: "运行 Skill 脚本",
  run_shared_script: "运行共享脚本",
  run_workspace_script: "运行工作区脚本",
};

interface Props {
  skills: SkillMeta[];
  collapsed: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onInspect: (path: string) => Promise<SkillInspect>;
  onConfirmInstall: (path: string, enabled: boolean) => Promise<void>;
  onRefresh: () => void;
}

export default function SkillPanel({
  skills,
  collapsed,
  onToggle,
  onInspect,
  onConfirmInstall,
  onRefresh,
}: Props) {
  const [installPath, setInstallPath] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(!isTauriRuntime());
  const [pickMenuOpen, setPickMenuOpen] = useState(false);
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);
  const [previewPath, setPreviewPath] = useState<string | null>(null);
  const [preview, setPreview] = useState<SkillInspect | null>(null);

  async function beginPreview(path: string) {
    const trimmed = path.trim();
    if (!trimmed) return;
    setPickMenuOpen(false);
    setInstalling(true);
    setInstallError(null);
    setPreview(null);
    setPreviewPath(null);
    try {
      const skill = await onInspect(trimmed);
      setPreview(skill);
      setPreviewPath(trimmed);
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "无法读取 Skill 包");
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

  async function handleAdvancedSubmit(e: FormEvent) {
    e.preventDefault();
    await beginPreview(installPath);
  }

  async function confirmInstall(enable: boolean) {
    if (!previewPath) return;
    setInstalling(true);
    setInstallError(null);
    try {
      await onConfirmInstall(previewPath, enable);
      setPreview(null);
      setPreviewPath(null);
      setInstallPath("");
    } catch (err) {
      setInstallError(err instanceof Error ? err.message : "安装失败");
    } finally {
      setInstalling(false);
    }
  }

  if (collapsed) {
    return <section className="pane skill-pane skill-pane--collapsed" aria-hidden="true" />;
  }

  return (
    <section className="pane skill-pane">
      <div className="pane-header">
        <span className="pane-title">Skill</span>
        <button type="button" className="btn btn--ghost btn--xs" onClick={onRefresh}>
          刷新
        </button>
      </div>

      <div className="pane-body">
        {skills.length === 0 && <div className="empty-hint">尚未安装任何 Skill。</div>}
        <ul className="skill-list">
          {skills.map((s) => (
            <li key={s.id} className="skill-row">
              <div className="skill-row-head">
                <span className="skill-name">{s.name}</span>
                <span className={`tier-badge tier-badge--${s.tier}`}>
                  {s.tier === "heavy" ? "重量" : "轻量"}
                </span>
              </div>
              <p className="skill-desc">{s.description}</p>
              {s.tier === "heavy" && s.min_ram_gb ? (
                <p className="skill-ram">建议内存 ≥ {s.min_ram_gb}GB</p>
              ) : null}
              {s.permissions && s.permissions.length > 0 ? (
                <p className="skill-perms">
                  权限：
                  {s.permissions.map((p) => PERMISSION_LABELS[p] ?? p).join("、")}
                </p>
              ) : null}
              <label className="skill-toggle">
                <input
                  type="checkbox"
                  checked={s.enabled}
                  onChange={(e) => onToggle(s.id, e.currentTarget.checked)}
                />
                <span>{s.enabled ? "已启用" : "已停用"}</span>
              </label>
            </li>
          ))}
        </ul>
      </div>

      <div className="skill-install">
        {isTauriRuntime() && (
          <div className="skill-install-actions">
            <button
              type="button"
              className="btn btn--primary btn--full"
              disabled={installing}
              onClick={() => setPickMenuOpen((v) => !v)}
              aria-expanded={pickMenuOpen}
            >
              {installing ? "读取中…" : "选择安装包"}
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
        )}

        <button
          type="button"
          className="skill-advanced-toggle"
          onClick={() => setShowAdvanced((v) => !v)}
        >
          {showAdvanced ? "收起路径输入" : "高级：粘贴路径"}
        </button>

        {showAdvanced && (
          <form className="skill-advanced-form" onSubmit={(e) => void handleAdvancedSubmit(e)}>
            <input
              className="skill-install-input"
              placeholder="文件夹 / .zip / .md 路径"
              value={installPath}
              onChange={(e) => setInstallPath(e.currentTarget.value)}
            />
            <button
              type="submit"
              className="btn btn--ghost btn--full"
              disabled={installing || !installPath.trim()}
            >
              {installing ? "读取中…" : "预览并安装"}
            </button>
          </form>
        )}

        {installError && <p className="skill-install-error">{installError}</p>}
      </div>

      {preview && previewPath && (
        <div className="skill-preview-backdrop" role="presentation">
          <div className="skill-preview" role="dialog" aria-labelledby="skill-preview-title">
            <h3 id="skill-preview-title">确认安装 Skill</h3>
            <dl className="skill-preview-meta">
              <div>
                <dt>名称</dt>
                <dd>{preview.name}</dd>
              </div>
              <div>
                <dt>说明</dt>
                <dd>{preview.description || "（无）"}</dd>
              </div>
              <div>
                <dt>版本</dt>
                <dd>{preview.version}</dd>
              </div>
              <div>
                <dt>类型</dt>
                <dd>
                  {preview.tier === "heavy" ? "重量" : "轻量"}
                  {preview.tier === "heavy" && preview.min_ram_gb
                    ? ` · 建议 ≥ ${preview.min_ram_gb}GB 内存`
                    : ""}
                </dd>
              </div>
              <div>
                <dt>权限</dt>
                <dd>
                  {preview.permissions.length === 0
                    ? "无额外权限声明"
                    : preview.permissions.map((p) => PERMISSION_LABELS[p] ?? p).join("、")}
                </dd>
              </div>
            </dl>
            {preview.tier === "heavy" && (
              <p className="skill-preview-warn">
                重量级 Skill 可能占用较多内存与磁盘。确认本机配置足够后再启用。
              </p>
            )}
            <p className="skill-preview-note">
              将安装到本机 Skill 区。请确认权限后选择「安装并启用」；也可仅安装稍后启用。
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
                disabled={installing}
                onClick={() => void confirmInstall(false)}
              >
                仅安装
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={installing}
                onClick={() => void confirmInstall(true)}
              >
                {installing ? "安装中…" : "安装并启用"}
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  );
}
