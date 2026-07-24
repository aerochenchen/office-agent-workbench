from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from office_agent.audit import AuditLog
from office_agent.paths import app_data_dir
from office_agent.skills import SkillRegistry
from office_agent.workspace import (
    AGENT_OUTPUT_REL,
    AGENT_WORK_REL,
    DELIVERABLE_SUFFIXES,
    SandboxError,
    Workspace,
)


class ToolError(ValueError):
    pass


def _normalize_rel(rel: str) -> str:
    normalized = rel.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def relocate_write_path(rel: str) -> str:
    """Route agent writes: root .py → work/; root deliverables → output/."""
    normalized = _normalize_rel(rel)
    if normalized.startswith(f"{AGENT_WORK_REL}/") or normalized == AGENT_WORK_REL:
        return normalized
    if normalized.startswith(f"{AGENT_OUTPUT_REL}/") or normalized == AGENT_OUTPUT_REL:
        return normalized
    path = Path(normalized)
    if ".." in path.parts:
        return normalized
    if len(path.parts) != 1:
        return normalized
    suffix = path.suffix.lower()
    if suffix == ".py":
        return f"{AGENT_WORK_REL}/{path.name}"
    if suffix in DELIVERABLE_SUFFIXES:
        return f"{AGENT_OUTPUT_REL}/{path.name}"
    return normalized


# Back-compat alias used by older tests/imports
_relocate_process_path = relocate_write_path


class ToolExecutor:
    def __init__(
        self,
        workspace: Workspace,
        skills: SkillRegistry,
        *,
        permission_mode: str = "standard",
        audit: AuditLog | None = None,
        python_bin: str | None = None,
    ) -> None:
        self.workspace = workspace
        self.skills = skills
        self.permission_mode = permission_mode
        self.audit = audit
        self.python_bin = python_bin or sys.executable
        self._app_data = app_data_dir()

    def execute(self, name: str, args: dict) -> dict:
        handlers = {
            "workspace_list": self._workspace_list,
            "workspace_read": self._workspace_read,
            "workspace_write": self._workspace_write,
            "run_workspace_script": self._run_workspace_script,
            "run_skill_script": self._run_skill_script,
            "run_shared_script": self._run_shared_script,
            "ask_user": self._ask_user,
            "finish": self._finish,
        }
        if name not in handlers:
            result: dict = {"ok": False, "error": f"unknown tool: {name}"}
            self._audit(name, args, False, str(result.get("error", "")))
            return result

        try:
            result = handlers[name](args)
            ok = bool(result.get("ok", True))
            detail = str(result.get("error") or result.get("stderr") or "")[:500]
            self._audit(name, args, ok, detail)
            return result
        except (SandboxError, ToolError) as e:
            result = {"ok": False, "error": str(e)}
            self._audit(name, args, False, str(e)[:500])
            return result
        except Exception as e:
            result = {"ok": False, "error": f"tool failed: {e}"}
            self._audit(name, args, False, str(e)[:500])
            return result

    def _audit(self, tool: str, args: dict, ok: bool, detail: str) -> None:
        if self.audit is not None:
            self.audit.record(tool, args, ok, detail)

    def _workspace_list(self, args: dict) -> dict:
        rel = str(args.get("path", "."))
        entries = self.workspace.list_dir(rel)
        return {"ok": True, "entries": entries}

    def _workspace_read(self, args: dict) -> dict:
        content = self.workspace.read_text(str(args["path"]))
        return {"ok": True, "content": content}

    def _workspace_write(self, args: dict) -> dict:
        rel = relocate_write_path(str(args["path"]))
        if rel.startswith(f"{AGENT_WORK_REL}/") or rel.startswith(f"{AGENT_OUTPUT_REL}/"):
            self.workspace.ensure_layout()
        written = self.workspace.write_text(rel, str(args["content"]))
        return {"ok": True, "path": str(written.relative_to(self.workspace.root))}

    def _run_workspace_script(self, args: dict) -> dict:
        """Run a .py file that lives inside the workspace sandbox."""
        rel = relocate_write_path(str(args["path"]))
        argv = [str(a) for a in args.get("args", [])]
        script_path = self.workspace.resolve(rel)
        if not script_path.is_file():
            return {"ok": False, "error": f"script not found in workspace: {rel}"}
        if script_path.suffix.lower() != ".py":
            return {"ok": False, "error": "only .py scripts are allowed in workspace"}
        return self._run_python(script_path, argv, self.workspace.root)

    def _validate_script_name(self, script: str) -> None:
        if ".." in script or script.startswith(("/", "\\")):
            raise ToolError(f"invalid script name: {script}")

    def _run_skill_script(self, args: dict) -> dict:
        skill_id = str(args["skill_id"])
        script = str(args["script"])
        argv = [str(a) for a in args.get("args", [])]
        self._validate_script_name(script)
        scripts_dir = (self._app_data / "skills" / skill_id / "scripts").resolve()
        script_path = (scripts_dir / script).resolve()
        try:
            script_path.relative_to(scripts_dir)
        except ValueError as e:
            raise ToolError("script path escapes skill scripts directory") from e
        if not script_path.is_file():
            return {"ok": False, "error": f"script not found: {script}"}
        return self._run_python(script_path, argv, self.workspace.root)

    def _run_shared_script(self, args: dict) -> dict:
        name = str(args["name"])
        argv = [str(a) for a in args.get("args", [])]
        if ".." in name or "/" in name or "\\" in name:
            raise ToolError(f"invalid shared script name: {name}")
        script_path = self._app_data / "shared-scripts" / f"{name}.py"
        if not script_path.is_file():
            return {"ok": False, "error": f"shared script not found: {name}"}
        return self._run_python(script_path, argv, self.workspace.root)

    def _run_python(self, script: Path, argv: list[str], cwd: Path) -> dict:
        env = os.environ.copy()
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("TRANSFORMERS_OFFLINE", "1")
        # PyInstaller sidecar: sys.executable is office-agent-runtime.exe.
        # Re-enter via --run-script so scripts get a real interpreter context.
        if getattr(sys, "frozen", False):
            cmd = [self.python_bin, "--run-script", str(script), *argv]
        else:
            cmd = [self.python_bin, str(script), *argv]
        proc = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=600,
            env=env,
        )
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": proc.stdout,
            "stderr": proc.stderr,
        }

    def _ask_user(self, args: dict) -> dict:
        q = str(args.get("question") or args.get("prompt") or "")
        return {"ok": True, "pending": True, "question": q, "prompt": q}

    def _finish(self, args: dict) -> dict:
        return {"ok": True, "finished": True, "summary": str(args.get("summary", ""))}
