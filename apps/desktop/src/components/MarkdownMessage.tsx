import { useCallback, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  hasDeliverableSuffix,
  isPathUnderWorkspace,
  isRelativeDeliverablePath,
  isTauriRuntime,
  normalizeFsPath,
  openPath,
  resolveUnderWorkspace,
} from "../lib/tauri";

interface Props {
  content: string;
  workspacePath?: string | null;
}

function isSafeHref(href: string): boolean {
  try {
    const url = new URL(href, "https://example.invalid");
    return url.protocol === "http:" || url.protocol === "https:";
  } catch {
    return false;
  }
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Strip trailing punctuation that is not part of the file path. */
function trimPathNoise(raw: string): string {
  let cleaned = raw;
  while (cleaned.length > 0 && /[.,;:!?)]$/u.test(cleaned) && !hasDeliverableSuffix(cleaned)) {
    cleaned = cleaned.slice(0, -1);
  }
  return cleaned;
}

/** Split plain text, wrapping workspace absolute deliverable paths as interactive nodes. */
function linkifyAbsolutePaths(
  text: string,
  workspacePath: string | null | undefined,
  renderPath: (path: string, label: string) => ReactNode,
): ReactNode[] {
  if (!workspacePath) return [text];
  const root = normalizeFsPath(workspacePath);
  if (!root) return [text];

  const re = new RegExp(
    `${escapeRegExp(root)}/[^\\s\\\`"'<>\\]\\)]+\\.(?:docx|xlsx|pdf|md|txt|json)`,
    "gi",
  );

  const nodes: ReactNode[] = [];
  let last = 0;
  let match: RegExpExecArray | null;
  let guard = 0;
  while ((match = re.exec(text)) !== null) {
    const start = match.index;
    if (start > last) nodes.push(text.slice(last, start));
    const cleaned = normalizeFsPath(trimPathNoise(match[0]));
    if (isPathUnderWorkspace(cleaned, workspacePath) && hasDeliverableSuffix(cleaned)) {
      nodes.push(renderPath(cleaned, cleaned));
    } else {
      nodes.push(match[0]);
    }
    last = start + match[0].length;
    if (++guard > 200) break;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes.length > 0 ? nodes : [text];
}

function mapTextChildren(
  children: ReactNode,
  workspacePath: string | null | undefined,
  renderPath: (path: string, label: string) => ReactNode,
): ReactNode {
  if (typeof children === "string") {
    return linkifyAbsolutePaths(children, workspacePath, renderPath);
  }
  if (Array.isArray(children)) {
    return children.map((child, i) => (
      <span key={i}>{mapTextChildren(child, workspacePath, renderPath)}</span>
    ));
  }
  return children;
}

function PathAction({ path, label }: { path: string; label: string }) {
  const [status, setStatus] = useState<string | null>(null);
  const tauri = isTauriRuntime();

  const onClick = useCallback(async () => {
    setStatus(null);
    try {
      if (tauri) {
        await openPath(path);
      } else {
        await navigator.clipboard.writeText(path);
        setStatus("已复制路径");
        window.setTimeout(() => setStatus(null), 2000);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      setStatus(tauri ? `打开失败：${msg}` : `复制失败：${msg}`);
    }
  }, [path, tauri]);

  return (
    <span className="markdown-path">
      <button
        type="button"
        className="markdown-path-btn"
        title={tauri ? `用系统应用打开\n${path}` : `复制路径\n${path}`}
        onClick={() => void onClick()}
      >
        {label}
      </button>
      {status ? <span className="markdown-path-status">{status}</span> : null}
    </span>
  );
}

export default function MarkdownMessage({ content, workspacePath = null }: Props) {
  const renderPath = useCallback(
    (path: string, label: string) => <PathAction key={path} path={path} label={label} />,
    [],
  );

  return (
    <div className="markdown-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ href, children, ...props }) => {
            if (!href || !isSafeHref(href)) {
              return <span className="markdown-link--blocked">{children}</span>;
            }
            return (
              <a href={href} target="_blank" rel="noopener noreferrer" {...props}>
                {children}
              </a>
            );
          },
          code: ({ className, children, ...props }) => {
            const text = String(children).replace(/\n$/, "");
            const isBlock = Boolean(className) || text.includes("\n");
            if (!isBlock && workspacePath && isRelativeDeliverablePath(text)) {
              const abs = resolveUnderWorkspace(workspacePath, text);
              return <PathAction path={abs} label={text} />;
            }
            return (
              <code className={className} {...props}>
                {children}
              </code>
            );
          },
          p: ({ children, ...props }) => (
            <p {...props}>{mapTextChildren(children, workspacePath, renderPath)}</p>
          ),
          li: ({ children, ...props }) => (
            <li {...props}>{mapTextChildren(children, workspacePath, renderPath)}</li>
          ),
          td: ({ children, ...props }) => (
            <td {...props}>{mapTextChildren(children, workspacePath, renderPath)}</td>
          ),
          th: ({ children, ...props }) => (
            <th {...props}>{mapTextChildren(children, workspacePath, renderPath)}</th>
          ),
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
