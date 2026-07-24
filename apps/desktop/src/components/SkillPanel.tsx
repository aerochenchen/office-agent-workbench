import { useState, type FormEvent } from "react";
import type { SkillMeta } from "../lib/types";
import "./SkillPanel.css";

interface Props {
  skills: SkillMeta[];
  collapsed: boolean;
  onToggle: (id: string, enabled: boolean) => void;
  onInstall: (path: string) => Promise<void>;
  onRefresh: () => void;
}

export default function SkillPanel({ skills, collapsed, onToggle, onInstall, onRefresh }: Props) {
  const [installPath, setInstallPath] = useState("");
  const [installing, setInstalling] = useState(false);
  const [installError, setInstallError] = useState<string | null>(null);

  async function handleInstall(e: FormEvent) {
    e.preventDefault();
    if (!installPath.trim()) return;
    setInstalling(true);
    setInstallError(null);
    try {
      await onInstall(installPath.trim());
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

      <form className="skill-install" onSubmit={handleInstall}>
        <input
          className="skill-install-input"
          placeholder="Skill 目录路径（含 SKILL.md）"
          value={installPath}
          onChange={(e) => setInstallPath(e.currentTarget.value)}
        />
        <button type="submit" className="btn btn--ghost btn--full" disabled={installing}>
          {installing ? "安装中…" : "安装 Skill"}
        </button>
        {installError && <p className="skill-install-error">{installError}</p>}
      </form>
    </section>
  );
}
