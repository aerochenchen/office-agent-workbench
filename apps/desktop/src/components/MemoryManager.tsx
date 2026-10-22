import { useCallback, useEffect, useState } from "react";
import type {
  MemoryCrystallized,
  MemoryHabit,
  MemoryRecent,
  MemorySnapshot,
} from "../lib/types";
import "./MemoryManager.css";

export interface MemoryManagerProps {
  open: boolean;
  onClose: () => void;
  load: () => Promise<MemorySnapshot>;
  save: (body: {
    habits: MemoryHabit[];
    recent: MemoryRecent[];
  }) => Promise<MemorySnapshot>;
  undo: () => Promise<MemorySnapshot>;
  onOpenSkills?: () => void;
}

type EditTarget =
  | { kind: "habit"; index: number; topic: string; text: string }
  | { kind: "recent"; index: number; text: string }
  | null;

export default function MemoryManager({
  open,
  onClose,
  load,
  save,
  undo,
  onOpenSkills,
}: MemoryManagerProps) {
  const [habits, setHabits] = useState<MemoryHabit[]>([]);
  const [recent, setRecent] = useState<MemoryRecent[]>([]);
  const [crystallized, setCrystallized] = useState<MemoryCrystallized[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditTarget>(null);

  const applySnap = useCallback((snap: MemorySnapshot) => {
    setHabits(snap.habits ?? []);
    setRecent(snap.recent ?? []);
    setCrystallized(snap.crystallized ?? []);
    setCanUndo(Boolean(snap.can_undo));
  }, []);

  useEffect(() => {
    if (!open) return;
    setError(null);
    setEdit(null);
    let cancelled = false;
    void (async () => {
      try {
        const snap = await load();
        if (!cancelled) applySnap(snap);
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "无法读取记忆");
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, load, applySnap]);

  async function persist(nextHabits: MemoryHabit[], nextRecent: MemoryRecent[]) {
    setBusy(true);
    setError(null);
    try {
      const snap = await save({ habits: nextHabits, recent: nextRecent });
      applySnap(snap);
      setEdit(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUndo() {
    setBusy(true);
    setError(null);
    try {
      const snap = await undo();
      applySnap(snap);
      setEdit(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "撤销失败");
    } finally {
      setBusy(false);
    }
  }

  function deleteHabit(index: number) {
    const next = habits.filter((_, i) => i !== index);
    void persist(next, recent);
  }

  function deleteRecent(index: number) {
    const next = recent.filter((_, i) => i !== index);
    void persist(habits, next);
  }

  function commitEdit() {
    if (!edit) return;
    if (edit.kind === "habit") {
      const topic = edit.topic.trim();
      const text = edit.text.trim();
      if (!topic || !text) {
        setError("主题和内容都不能为空");
        return;
      }
      const next = habits.map((h, i) =>
        i === edit.index ? { ...h, topic, text } : h,
      );
      void persist(next, recent);
      return;
    }
    const text = edit.text.trim();
    if (!text) {
      setError("近况不能为空");
      return;
    }
    const next = recent.map((r, i) => (i === edit.index ? { ...r, text } : r));
    void persist(habits, next);
  }

  if (!open) return null;

  const empty = habits.length === 0 && recent.length === 0;

  return (
    <div
      className="memory-manager-backdrop"
      role="presentation"
      onClick={() => {
        if (!busy) onClose();
      }}
    >
      <div
        className="memory-manager"
        role="dialog"
        aria-modal="true"
        aria-labelledby="memory-manager-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="memory-manager-header">
          <h2 id="memory-manager-title" className="memory-manager-title">
            记忆
          </h2>
          <div className="memory-manager-header-actions">
            <button
              type="button"
              className="btn btn--ghost btn--xs"
              disabled={busy || !canUndo}
              onClick={() => void handleUndo()}
            >
              撤销上一笔
            </button>
            <button
              type="button"
              className="btn btn--ghost btn--xs"
              disabled={busy}
              onClick={onClose}
            >
              关闭
            </button>
          </div>
        </header>

        <p className="memory-manager-intro">
          办完事后自动记下，下次办事会参考。可改、可删。
        </p>

        {error ? <p className="memory-manager-error">{error}</p> : null}

        <div className="memory-manager-body">
          {empty ? (
            <p className="memory-manager-section-empty">
              暂无记录。办完事后会出现在这里。
            </p>
          ) : null}

          <section aria-labelledby="memory-habits-title">
            <h3 id="memory-habits-title" className="memory-manager-section-title">
              习惯
            </h3>
            {habits.length === 0 ? (
              <p className="memory-manager-section-empty">暂无习惯记录</p>
            ) : (
              <ul className="memory-list">
                {habits.map((h, index) => (
                  <li key={`${h.topic}-${index}`} className="memory-card">
                    {edit?.kind === "habit" && edit.index === index ? (
                      <>
                        <input
                          className="memory-edit-field"
                          value={edit.topic}
                          disabled={busy}
                          onChange={(e) =>
                            setEdit({ ...edit, topic: e.currentTarget.value })
                          }
                          aria-label="习惯主题"
                        />
                        <textarea
                          className="memory-edit-field"
                          value={edit.text}
                          disabled={busy}
                          rows={3}
                          onChange={(e) =>
                            setEdit({ ...edit, text: e.currentTarget.value })
                          }
                          aria-label="习惯内容"
                        />
                        <div className="memory-card-actions">
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() => setEdit(null)}
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            className="btn btn--primary btn--xs"
                            disabled={busy}
                            onClick={() => commitEdit()}
                          >
                            保存
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="memory-card-topic">{h.topic}</p>
                        <p className="memory-card-text">{h.text}</p>
                        <div className="memory-card-actions">
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() =>
                              setEdit({
                                kind: "habit",
                                index,
                                topic: h.topic,
                                text: h.text,
                              })
                            }
                          >
                            改
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() => deleteHabit(index)}
                          >
                            删
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          <section aria-labelledby="memory-recent-title">
            <h3 id="memory-recent-title" className="memory-manager-section-title">
              近况
            </h3>
            {recent.length === 0 ? (
              <p className="memory-manager-section-empty">暂无近况</p>
            ) : (
              <ul className="memory-list">
                {recent.map((r, index) => (
                  <li key={`${r.text}-${index}`} className="memory-card">
                    {edit?.kind === "recent" && edit.index === index ? (
                      <>
                        <textarea
                          className="memory-edit-field"
                          value={edit.text}
                          disabled={busy}
                          rows={3}
                          onChange={(e) =>
                            setEdit({ ...edit, text: e.currentTarget.value })
                          }
                          aria-label="近况内容"
                        />
                        <div className="memory-card-actions">
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() => setEdit(null)}
                          >
                            取消
                          </button>
                          <button
                            type="button"
                            className="btn btn--primary btn--xs"
                            disabled={busy}
                            onClick={() => commitEdit()}
                          >
                            保存
                          </button>
                        </div>
                      </>
                    ) : (
                      <>
                        <p className="memory-card-text">{r.text}</p>
                        <div className="memory-card-actions">
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() =>
                              setEdit({ kind: "recent", index, text: r.text })
                            }
                          >
                            改
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost btn--xs"
                            disabled={busy}
                            onClick={() => deleteRecent(index)}
                          >
                            删
                          </button>
                        </div>
                      </>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>

          {crystallized.length > 0 ? (
            <section aria-labelledby="memory-skills-title">
              <h3 id="memory-skills-title" className="memory-manager-section-title">
                已固化流程
              </h3>
              <ul className="memory-list">
                {crystallized.map((c) => (
                  <li key={c.skill_id} className="memory-card">
                    <button
                      type="button"
                      className="memory-crystallized-link"
                      onClick={() => {
                        onClose();
                        onOpenSkills?.();
                      }}
                    >
                      {c.display_name || c.skill_id}
                      {c.version ? ` · v${c.version}` : ""}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      </div>
    </div>
  );
}
