import { useState } from "react";
import type { SkillInspectResult, SkillMeta } from "../lib/types";
import { GUIDE_HINTS } from "../lib/guide";
import { filterEnabledSkills } from "../lib/skillUtils";
import SkillManager from "./SkillManager";
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

export default function SkillPanel({
  skills,
  collapsed,
  onToggle,
  onInspect,
  onConfirmInstall,
  onUninstall,
  onRefresh,
}: Props) {
  const [managerOpen, setManagerOpen] = useState(false);
  const enabled = filterEnabledSkills(skills);

  if (collapsed) {
    return <section className="pane skill-pane skill-pane--collapsed" aria-hidden="true" />;
  }

  return (
    <>
      <section className="pane skill-pane">
        <div className="pane-header">
          <span className="pane-title">技能</span>
        </div>

        <div className="pane-body">
          {enabled.length === 0 ? (
            <div className="skill-empty">
              <p className="empty-hint">{GUIDE_HINTS.noEnabledSkills}</p>
              <button
                type="button"
                className="btn btn--ghost btn--full"
                onClick={() => setManagerOpen(true)}
              >
                技能管理
              </button>
            </div>
          ) : (
            <ul className="skill-list">
              {enabled.map((s) => {
                const title = s.display_name || s.name;
                return (
                  <li
                    key={s.id}
                    className="skill-card skill-card--display"
                    title={s.description || undefined}
                  >
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
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        <div className="skill-panel-footer">
          <button
            type="button"
            className="btn btn--ghost btn--full"
            onClick={() => setManagerOpen(true)}
          >
            技能管理
          </button>
        </div>
      </section>

      <SkillManager
        open={managerOpen}
        skills={skills}
        onClose={() => setManagerOpen(false)}
        onToggle={onToggle}
        onInspect={onInspect}
        onConfirmInstall={onConfirmInstall}
        onUninstall={onUninstall}
        onRefresh={onRefresh}
      />
    </>
  );
}
