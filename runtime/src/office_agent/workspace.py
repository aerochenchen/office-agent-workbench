from __future__ import annotations
from pathlib import Path


class SandboxError(ValueError):
    pass


# Platform scratch + user-facing deliverables under the workspace root.
# Root itself is reserved for the user's own source materials.
AGENT_WORK_REL = ".office-agent/work"
AGENT_OUTPUT_REL = "工作成果"

# Root-level writes with these suffixes are treated as deliverables → 工作成果/
DELIVERABLE_SUFFIXES = frozenset({
    ".docx",
    ".doc",
    ".pdf",
    ".xlsx",
    ".xls",
    ".pptx",
    ".ppt",
    ".wps",
    ".rtf",
    ".odt",
    ".ods",
    ".odp",
})


class Workspace:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise SandboxError(f"workspace root is not a directory: {self.root}")

    def resolve(self, rel_or_abs: str) -> Path:
        raw = Path(rel_or_abs)
        candidate = (self.root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        try:
            candidate.relative_to(self.root)
        except ValueError as e:
            raise SandboxError(f"path escapes workspace: {rel_or_abs}") from e
        return candidate

    def agent_work_dir(self) -> Path:
        """Process files: scripts, drafts, intermediates (created if missing)."""
        path = self.root / AGENT_WORK_REL
        path.mkdir(parents=True, exist_ok=True)
        readme = path / "README.txt"
        if not readme.is_file():
            readme.write_text(
                "本目录存放智能体运行过程中的脚本与中间文件。\n"
                "最终成果请查看工作区下的「工作成果」目录。\n"
                "工作区根目录请留给您自己的源材料。\n",
                encoding="utf-8",
            )
        return path

    def output_dir(self) -> Path:
        """Final deliverables for the user (created if missing)."""
        path = self.root / AGENT_OUTPUT_REL
        path.mkdir(parents=True, exist_ok=True)
        readme = path / "README.txt"
        if not readme.is_file():
            readme.write_text(
                "本目录存放智能体生成的最终成果（如 docx、pdf）。\n"
                "源材料请放在工作区根目录；过程文件在 .office-agent/work/。\n",
                encoding="utf-8",
            )
        return path

    def ensure_layout(self) -> None:
        """Create standard work + output directories when a workspace is opened."""
        self.agent_work_dir()
        self.output_dir()

    def list_dir(self, rel: str = ".") -> list[dict]:
        target = self.resolve(rel)
        if not target.is_dir():
            raise SandboxError(f"not a directory: {rel}")
        out: list[dict] = []
        for p in sorted(target.iterdir(), key=lambda x: x.name.lower()):
            out.append({
                "name": p.name,
                "path": str(p.relative_to(self.root)),
                "is_dir": p.is_dir(),
            })
        return out

    def read_text(self, rel: str, max_bytes: int = 512_000) -> str:
        path = self.resolve(rel)
        if not path.is_file():
            raise SandboxError(f"not a file: {rel}")
        data = path.read_bytes()
        if len(data) > max_bytes:
            raise SandboxError(f"file too large: {rel}")
        return data.decode("utf-8", errors="replace")

    def write_text(self, rel: str, content: str) -> Path:
        path = self.resolve(rel)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path
