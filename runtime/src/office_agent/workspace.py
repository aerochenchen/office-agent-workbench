from __future__ import annotations
from pathlib import Path


class SandboxError(ValueError):
    pass


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
