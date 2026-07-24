import { useState } from "react";
import type { TreeEntry } from "../lib/types";
import { isTauriRuntime } from "../lib/tauri";
import "./WorkspaceTree.css";

interface Props {
  workspacePath: string | null;
  entries: TreeEntry[];
  error: string | null;
  onPickFolder: () => void;
  onOpenPath: (path: string) => void;
  onRefresh: () => void;
}

function FolderIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path
        d="M1.5 3.5A1 1 0 0 1 2.5 2.5h3.2l1 1.4h5.3a1 1 0 0 1 1 1V12a1 1 0 0 1-1 1H2.5a1 1 0 0 1-1-1V3.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
      />
    </svg>
  );
}

function FileIcon() {
  return (
    <svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">
      <path
        d="M4 1.5h5l2.5 2.5V14a.5.5 0 0 1-.5.5H4a.5.5 0 0 1-.5-.5V2a.5.5 0 0 1 .5-.5Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.1"
      />
    </svg>
  );
}

export default function WorkspaceTree({
  workspacePath,
  entries,
  error,
  onPickFolder,
  onOpenPath,
  onRefresh,
}: Props) {
  const [manualPath, setManualPath] = useState("");
  const showManualInput = !isTauriRuntime();

  return (
    <section className="pane workspace-pane">
      <div className="pane-header">
        <span className="pane-title">工作区</span>
        {workspacePath && (
          <button type="button" className="btn btn--ghost btn--xs" onClick={onRefresh}>
            刷新
          </button>
        )}
      </div>

      <div className="pane-body">
        {workspacePath ? (
          <div className="workspace-path" title={workspacePath}>
            {workspacePath}
          </div>
        ) : null}

        {!workspacePath && (
          <div className="empty-hint">
            尚未打开工作区。选择一个文件夹作为对话与工具操作的沙箱根目录。
          </div>
        )}

        {error && <div className="tree-error">{error}</div>}

        {workspacePath && (
          <ul className="tree-list">
            {entries.map((e) => (
              <li key={e.path} className="tree-row">
                <span className="tree-icon">{e.is_dir ? <FolderIcon /> : <FileIcon />}</span>
                <span className="tree-name">{e.name}</span>
              </li>
            ))}
            {entries.length === 0 && <li className="tree-empty">（空目录）</li>}
          </ul>
        )}

        {workspacePath && entries.length > 0 && (
          <div className="tree-footnote">仅显示工作区根目录内容</div>
        )}
      </div>

      <div className="workspace-actions">
        <button type="button" className="btn btn--primary btn--full" onClick={onPickFolder}>
          选择文件夹…
        </button>
        {showManualInput && (
          <form
            className="manual-open"
            onSubmit={(e) => {
              e.preventDefault();
              if (manualPath.trim()) onOpenPath(manualPath.trim());
            }}
          >
            <input
              className="manual-open-input"
              placeholder="/path/to/workspace（浏览器调试用）"
              value={manualPath}
              onChange={(e) => setManualPath(e.currentTarget.value)}
            />
            <button type="submit" className="btn btn--ghost btn--xs">
              打开
            </button>
          </form>
        )}
      </div>
    </section>
  );
}
