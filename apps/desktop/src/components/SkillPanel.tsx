import { useMemo, useState } from "react";
import type { SkillInspectResult, SkillMeta } from "../lib/types";
import { CAPABILITY_TREE, GUIDE_HINTS } from "../lib/guide";
import SkillManager from "./SkillManager";
import "./SkillPanel.css";

interface Props {
  skills: SkillMeta[];
  collapsed: boolean;
  /** True when the active chat has no messages — hide the full tree to avoid duplicating the empty-chat chips. */
  chatEmpty?: boolean;
  pickDisabled?: boolean;
  onPickSaying: (saying: string) => void;
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

export default function SkillPanel({
  skills,
  collapsed,
  chatEmpty = false,
  pickDisabled = false,
  onPickSaying,
  onToggle,
  onInspect,
  onConfirmInstall,
  onUninstall,
  onRestoreBundled,
  onRefresh,
}: Props) {
  const [managerOpen, setManagerOpen] = useState(false);
  const defaultOpen = useMemo(
    () => new Set(CAPABILITY_TREE.map((b) => b.id)),
    [],
  );
  const [openBranches, setOpenBranches] = useState<Set<string>>(defaultOpen);

  function toggleBranch(id: string) {
    setOpenBranches((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  if (collapsed) {
    return <section className="pane skill-pane skill-pane--collapsed" aria-hidden="true" />;
  }

  return (
    <>
      <section className="pane skill-pane">
        <div className="pane-header">
          <span className="pane-title">办事能力</span>
        </div>

        <div className="pane-body capability-tree-scroll">
          {chatEmpty ? (
            <p className="capability-tree-idle">{GUIDE_HINTS.capabilityTreeIdle}</p>
          ) : (
            <>
              <ul className="capability-tree" aria-label="办事能力">
                {CAPABILITY_TREE.map((branch) => {
                  const open = openBranches.has(branch.id);
                  const beyond = branch.id === "beyond";
                  return (
                    <li
                      key={branch.id}
                      className={`capability-branch${beyond ? " capability-branch--beyond" : ""}`}
                    >
                      <button
                        type="button"
                        className="capability-branch-toggle"
                        aria-expanded={open}
                        onClick={() => toggleBranch(branch.id)}
                      >
                        <span
                          className={`capability-branch-seal${open ? " capability-branch-seal--open" : ""}`}
                          aria-hidden="true"
                        />
                        <span className="capability-branch-label">{branch.label}</span>
                      </button>
                      {open ? (
                        <ul className="capability-leaves">
                          {branch.children.map((leaf) => (
                            <li key={leaf.id}>
                              <button
                                type="button"
                                className="capability-leaf"
                                title={leaf.saying}
                                disabled={pickDisabled}
                                onClick={() => onPickSaying(leaf.saying)}
                              >
                                <span className="capability-leaf-dot" aria-hidden="true" />
                                <span className="capability-leaf-label">{leaf.label}</span>
                              </button>
                            </li>
                          ))}
                        </ul>
                      ) : null}
                    </li>
                  );
                })}
              </ul>
            </>
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
        onRestoreBundled={onRestoreBundled}
        onRefresh={onRefresh}
      />
    </>
  );
}
