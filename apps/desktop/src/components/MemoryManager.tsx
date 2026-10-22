import { useCallback, useEffect, useState } from "react";
import type { MemoryCrystallized, MemoryHabit, MemorySnapshot } from "../lib/types";
import { EditIcon, PlusIcon, TrashIcon } from "./icons";
import "./MemoryManager.css";

export interface MemoryManagerProps {
  active: boolean;
  load: () => Promise<MemorySnapshot>;
  save: (body: {
    habits: MemoryHabit[];
    recent: Array<{ text: string; updated_at?: number }>;
  }) => Promise<MemorySnapshot>;
  onOpenSkills?: () => void;
}

const MAX_ENTRIES = 12;

type EditTarget =
  | { kind: "edit"; index: number; text: string }
  | { kind: "new"; text: string }
  | null;

/** 列表只展示一句话，不拼主题。 */
export function habitLine(h: MemoryHabit): string {
  return (h.text || "").trim();
}

/** 整句写入 text；topic 仅作后台去重键，界面不展示。 */
export function habitFromLine(line: string, usedTopics: Set<string>): MemoryHabit {
  const text = line.trim();
  const base = text.slice(0, 12) || "记忆";
  return { topic: uniqueTopic(base, usedTopics), text };
}

function uniqueTopic(base: string, used: Set<string>): string {
  if (!used.has(base)) return base;
  let n = 2;
  while (used.has(`${base}${n}`)) n += 1;
  return `${base}${n}`;
}

export default function MemoryManager({
  active,
  load,
  save,
  onOpenSkills,
}: MemoryManagerProps) {
  const [entries, setEntries] = useState<MemoryHabit[]>([]);
  const [crystallized, setCrystallized] = useState<MemoryCrystallized[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [edit, setEdit] = useState<EditTarget>(null);

  const applySnap = useCallback((snap: MemorySnapshot) => {
    setEntries(snap.habits ?? []);
    setCrystallized(snap.crystallized ?? []);
  }, []);

  useEffect(() => {
    if (!active) return;
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
  }, [active, load, applySnap]);

  async function persist(next: MemoryHabit[]) {
    setBusy(true);
    setError(null);
    try {
      const snap = await save({ habits: next, recent: [] });
      applySnap(snap);
      setEdit(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    } finally {
      setBusy(false);
    }
  }

  function startAdd() {
    if (busy) return;
    if (entries.length >= MAX_ENTRIES) {
      setError(`记忆最多 ${MAX_ENTRIES} 条，请先删掉不需要的`);
      return;
    }
    setError(null);
    setEdit({ kind: "new", text: "" });
  }

  function deleteEntry(index: number) {
    void persist(entries.filter((_, i) => i !== index));
  }

  function commitEdit() {
    if (!edit) return;
    const text = edit.text.trim();
    if (!text) {
      setError("内容不能为空");
      return;
    }
    if (edit.kind === "new") {
      if (entries.length >= MAX_ENTRIES) {
        setError(`记忆最多 ${MAX_ENTRIES} 条，请先删掉不需要的`);
        return;
      }
      const used = new Set(entries.map((h) => h.topic));
      void persist([habitFromLine(text, used), ...entries]);
      return;
    }
    void persist(
      entries.map((h, i) => (i === edit.index ? { ...h, text } : h)),
    );
  }

  return (
    <section className="memory-panel" aria-labelledby="settings-memory-title">
      <div className="memory-panel-head">
        <h3 id="settings-memory-title" className="settings-section-title">
          记忆
        </h3>
        <div className="memory-panel-head-actions">
          <button
            type="button"
            className="btn btn--ghost btn--icon"
            disabled={busy || edit?.kind === "new"}
            onClick={startAdd}
            aria-label="添加"
            title="添加"
          >
            <PlusIcon />
          </button>
        </div>
      </div>

      <p className="memory-panel-intro">
        记下你的偏好，之后都会按这个办。点添加，或说「记住……」。
      </p>

      {error ? <p className="memory-manager-error">{error}</p> : null}

      {entries.length === 0 && edit?.kind !== "new" ? (
        <p className="memory-manager-section-empty">暂无记忆。可点「添加」，或说「记住……」。</p>
      ) : null}

      {edit?.kind === "new" || entries.length > 0 ? (
        <ul className="memory-list">
          {edit?.kind === "new" ? (
            <li className="memory-card memory-card--new">
              <div className="memory-card-edit">
                <input
                  className="memory-edit-field"
                  value={edit.text}
                  disabled={busy}
                  placeholder="一句话，如「少问确认，直接做」"
                  autoFocus
                  onChange={(e) => setEdit({ ...edit, text: e.currentTarget.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitEdit();
                    }
                  }}
                  aria-label="新记忆"
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
              </div>
            </li>
          ) : null}
          {entries.map((h, index) => (
            <li key={`${h.topic}-${index}`} className="memory-card">
              {edit?.kind === "edit" && edit.index === index ? (
                <div className="memory-card-edit">
                  <input
                    className="memory-edit-field"
                    value={edit.text}
                    disabled={busy}
                    autoFocus
                    onChange={(e) => setEdit({ ...edit, text: e.currentTarget.value })}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        commitEdit();
                      }
                    }}
                    aria-label="记忆内容"
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
                </div>
              ) : (
                <div className="memory-card-view">
                  <p className="memory-card-text">{habitLine(h)}</p>
                  <div className="memory-card-actions">
                    <button
                      type="button"
                      className="btn btn--ghost btn--icon"
                      disabled={busy}
                      onClick={() =>
                        setEdit({
                          kind: "edit",
                          index,
                          text: habitLine(h),
                        })
                      }
                      aria-label="改"
                      title="改"
                    >
                      <EditIcon />
                    </button>
                    <button
                      type="button"
                      className="btn btn--ghost btn--icon"
                      disabled={busy}
                      onClick={() => deleteEntry(index)}
                      aria-label="删"
                      title="删"
                    >
                      <TrashIcon />
                    </button>
                  </div>
                </div>
              )}
            </li>
          ))}
        </ul>
      ) : null}

      {crystallized.length > 0 ? (
        <div className="memory-panel-crystallized">
          <h4 className="memory-manager-section-title">已固化流程</h4>
          <ul className="memory-list">
            {crystallized.map((c) => (
              <li key={c.skill_id} className="memory-card">
                <button
                  type="button"
                  className="memory-crystallized-link"
                  onClick={() => onOpenSkills?.()}
                >
                  {c.display_name || c.skill_id}
                  {c.version ? ` · v${c.version}` : ""}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
