from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from office_agent.audit import AuditLog
from office_agent.doc_io import extract_file
from office_agent.paths import app_data_dir
from office_agent.plan_store import (
    PLAN_HTML_REL,
    PLAN_REL,
    PlanValidationError,
    apply_step_update,
    load_plan,
    render_plan_html,
    save_plan,
    set_plan_approval,
    set_plan_status,
)
from office_agent.script_policy import assert_argv_within_roots, build_script_env
from office_agent.script_sandbox import (
    SCRIPT_TIMEOUT_SEC,
    preexec_isolate,
    sandbox_available,
    truncate_output,
    wrap_isolated_cmd,
)
from office_agent.permissions import (
    GATED_TOOLS,
    NeedsInteractivePermission,
    PermissionDenied,
    PermissionGate,
)
from office_agent.skills import SkillRegistry, parse_skill_md
from office_agent.workspace import (
    AGENT_OUTPUT_REL,
    AGENT_WORK_REL,
    DELIVERABLE_SUFFIXES,
    SandboxError,
    Workspace,
)


class ToolError(ValueError):
    pass


def list_shared_script_names(app_data: Path | None = None) -> list[str]:
    """Installed shared-script logical names (no .py), sorted."""
    root = Path(app_data or app_data_dir()) / "shared-scripts"
    if not root.is_dir():
        return []
    names: list[str] = []
    for path in sorted(root.glob("*.py")):
        if not path.is_file() or path.name.startswith("_"):
            continue
        names.append(path.stem)
    return names


def script_jail_roots(
    workspace_root: Path,
    app_data: Path,
    extra: list[Path] | None = None,
) -> list[Path]:
    """Allowed filesystem roots for script subprocesses.

    The app data root itself is excluded so scripts cannot read config.json.
    """
    roots: list[Path] = []
    seen: set[Path] = set()
    candidates = [
        Path(workspace_root).resolve(),
        (Path(app_data) / "skills").resolve(),
        (Path(app_data) / "shared-scripts").resolve(),
        Path(tempfile.gettempdir()).resolve(),
    ]
    if extra:
        candidates.extend(Path(p).resolve() for p in extra)
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        roots.append(path)
    return roots


# Files an installed Skill may expose to the agent via read_skill.
SKILL_TEXT_SUFFIXES = frozenset(
    {".md", ".txt", ".json", ".py", ".yaml", ".yml", ".csv", ".tmpl"}
)
MAX_SKILL_FILE_BYTES = 64 * 1024
MAX_SKILL_FILE_ENTRIES = 60


def _normalize_rel(rel: str) -> str:
    normalized = rel.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized


def relocate_write_path(rel: str) -> str:
    """Route agent writes: root .py → work/; root deliverables → 工作成果/."""
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
        turn_id: str | None = None,
        python_bin: str | None = None,
        gate: PermissionGate | None = None,
        attached_paths: list[str] | None = None,
        allow_workspace_scripts: bool = False,
        require_script_sandbox: bool = False,
        destination_host: str = "",
    ) -> None:
        self.workspace = workspace
        self.skills = skills
        self.permission_mode = permission_mode
        self.audit = audit
        self.turn_id = turn_id
        self.python_bin = python_bin or sys.executable
        self._app_data = app_data_dir()
        self.allow_workspace_scripts = allow_workspace_scripts
        self.require_script_sandbox = require_script_sandbox
        self.destination_host = destination_host
        if gate is not None:
            self.gate = gate
        else:
            # Fail-closed: tests that need auto-allow must pass a gate or use trust mode.
            self.gate = PermissionGate(permission_mode, destination_host=destination_host)
            self.gate.set_auto(False)
        if destination_host and not self.gate.destination_host:
            self.gate.destination_host = destination_host
        for rel in attached_paths or []:
            self.gate.allow_read_path(rel)

    def execute(self, name: str, args: dict) -> dict:
        handlers = {
            "workspace_list": self._workspace_list,
            "workspace_read": self._workspace_read,
            "workspace_write": self._workspace_write,
            "workspace_extract": self._workspace_extract,
            "run_workspace_script": self._run_workspace_script,
            "read_skill": self._read_skill,
            "run_skill_script": self._run_skill_script,
            "run_shared_script": self._run_shared_script,
            "plan_get": self._plan_get,
            "plan_create": self._plan_create,
            "plan_update_step": self._plan_update_step,
            "plan_set_status": self._plan_set_status,
            "plan_set_approval": self._plan_set_approval,
            "ask_user": self._ask_user,
            "finish": self._finish,
        }
        if name not in handlers:
            result: dict = {"ok": False, "error": f"unknown tool: {name}"}
            self._audit(name, args, False, str(result.get("error", "")))
            return result

        try:
            self._enforce_skill_permissions(name, args)
            if name == "run_workspace_script" and not self.allow_workspace_scripts:
                raise PermissionDenied("workspace scripts are disabled")
            if self.gate is not None and name in GATED_TOOLS:
                self.gate.check(name, args)
            result = handlers[name](args)
            ok = bool(result.get("ok", True))
            detail = str(
                result.get("error") or result.get("reason") or result.get("stderr") or ""
            )[:500]
            self._audit(name, args, ok, detail)
            return result
        except NeedsInteractivePermission:
            raise
        except PermissionDenied as e:
            result = {"ok": False, "error": f"permission denied: {e}"}
            self._audit(name, args, False, str(result["error"])[:500])
            return result
        except (SandboxError, ToolError) as e:
            result = {"ok": False, "error": str(e)}
            self._audit(name, args, False, str(e)[:500])
            return result
        except Exception as e:
            result = {"ok": False, "error": f"tool failed: {e}"}
            self._audit(name, args, False, str(e)[:500])
            return result

    def _skill_meta_for(self, skill_id: str):
        for meta in self.skills.scan():
            if meta.id == skill_id:
                return meta
        try:
            skill_dir = self._skill_dir(skill_id)
        except ToolError:
            return None
        md = skill_dir / "SKILL.md"
        if not md.is_file():
            return None
        return parse_skill_md(md.read_text(encoding="utf-8"), skill_dir)

    def _enforce_skill_permissions(self, name: str, args: dict) -> None:
        """Skill frontmatter ACL. Empty permissions list = legacy compat (mode gate only)."""
        if name == "run_skill_script":
            skill_id = str(args.get("skill_id") or "")
            meta = self._skill_meta_for(skill_id)
            if meta is not None and meta.permissions and "run_python" not in meta.permissions:
                raise PermissionDenied(
                    f"skill {skill_id} missing run_python in permissions"
                )
            return

        if name == "run_shared_script":
            script_name = str(args.get("name") or "")
            for meta in self.skills.scan():
                if script_name not in (meta.shared_scripts or []):
                    continue
                if meta.permissions and "run_python" not in meta.permissions:
                    raise PermissionDenied(
                        f"skill {meta.id} missing run_python in permissions"
                    )
            return

        if name == "workspace_write":
            # No skill_id on bare writes; skill ACL applies when skill_id is provided.
            skill_id = args.get("skill_id")
            if not skill_id:
                return
            meta = self._skill_meta_for(str(skill_id))
            if meta is not None and meta.permissions and "workspace_write" not in meta.permissions:
                raise PermissionDenied(
                    f"skill {skill_id} missing workspace_write in permissions"
                )

    def _audit(self, tool: str, args: dict, ok: bool, detail: str) -> None:
        if self.audit is not None:
            self.audit.record(tool, args, ok, detail, turn_id=self.turn_id)

    def _workspace_list(self, args: dict) -> dict:
        rel = str(args.get("path", "."))
        entries = self.workspace.list_dir(rel)
        return {"ok": True, "entries": entries}

    def _workspace_read(self, args: dict) -> dict:
        content = self.workspace.read_text(str(args["path"]))
        return {"ok": True, "content": content}

    def _workspace_extract(self, args: dict) -> dict:
        """Normalize .doc/.xls if needed, then extract text units from Office files."""
        rel = str(args["path"])
        path = self.workspace.resolve(rel)
        if not path.is_file():
            return {"ok": False, "error": f"not a file: {rel}"}
        max_chars = int(args.get("max_chars") or 80_000)
        max_units = int(args.get("max_units") or 200)
        force = bool(args.get("force_normalize") or False)
        granularity = str(args.get("granularity") or "section")
        result = extract_file(
            path,
            self.workspace.root,
            max_chars=max_chars,
            max_units=max_units,
            force_normalize=force,
            granularity=granularity,
        )
        payload = result.to_dict()
        # Prefer workspace-relative path in response
        try:
            payload["path"] = str(path.relative_to(self.workspace.root))
        except ValueError:
            pass
        return payload

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

    def _skill_dir(self, skill_id: str) -> Path:
        self._validate_script_name(skill_id)
        skills_root = (self._app_data / "skills").resolve()
        skill_dir = (skills_root / skill_id).resolve()
        try:
            skill_dir.relative_to(skills_root)
        except ValueError as e:
            raise ToolError(f"invalid skill_id: {skill_id}") from e
        return skill_dir

    def _list_skill_files(self, skill_dir: Path) -> list[str]:
        out: list[str] = []
        for p in sorted(skill_dir.rglob("*")):
            if "__pycache__" in p.parts:
                continue
            if not p.is_file() or p.suffix.lower() not in SKILL_TEXT_SUFFIXES:
                continue
            out.append(p.relative_to(skill_dir).as_posix())
            if len(out) >= MAX_SKILL_FILE_ENTRIES:
                break
        return out

    def _read_skill(self, args: dict) -> dict:
        """Read one text file from an installed Skill; defaults to SKILL.md."""
        skill_id = str(args["skill_id"])
        rel = str(args.get("file") or "SKILL.md").replace("\\", "/")
        skill_dir = self._skill_dir(skill_id)
        if not skill_dir.is_dir():
            return {"ok": False, "error": f"skill not installed: {skill_id}"}
        self._validate_script_name(rel)
        target = (skill_dir / rel).resolve()
        try:
            target.relative_to(skill_dir)
        except ValueError as e:
            raise ToolError("file path escapes skill directory") from e
        files = self._list_skill_files(skill_dir)
        if not target.is_file():
            return {"ok": False, "error": f"file not found in skill: {rel}", "files": files}
        if target.suffix.lower() not in SKILL_TEXT_SUFFIXES:
            return {"ok": False, "error": f"not a readable text file: {rel}", "files": files}
        raw = target.read_bytes()
        return {
            "ok": True,
            "skill_id": skill_id,
            "file": rel,
            "content": raw[:MAX_SKILL_FILE_BYTES].decode("utf-8", errors="replace"),
            "truncated": len(raw) > MAX_SKILL_FILE_BYTES,
            "files": files,
        }

    def _run_skill_script(self, args: dict) -> dict:
        skill_id = str(args["skill_id"])
        script = str(args["script"])
        argv = [str(a) for a in args.get("args", [])]
        self._validate_script_name(script)
        scripts_dir = (self._skill_dir(skill_id) / "scripts").resolve()
        script_path = (scripts_dir / script).resolve()
        try:
            script_path.relative_to(scripts_dir)
        except ValueError as e:
            raise ToolError("script path escapes skill scripts directory") from e
        if not script_path.is_file():
            return {"ok": False, "error": f"script not found: {script}"}
        skill_dir = self._skill_dir(skill_id)
        return self._run_python(
            script_path,
            argv,
            self.workspace.root,
            allowed_roots=[skill_dir, scripts_dir],
        )

    def _run_shared_script(self, args: dict) -> dict:
        name = str(args["name"])
        argv = [str(a) for a in args.get("args", [])]
        if ".." in name or "/" in name or "\\" in name:
            raise ToolError(f"invalid shared script name: {name}")
        script_path = self._app_data / "shared-scripts" / f"{name}.py"
        if not script_path.is_file():
            installed = list_shared_script_names(self._app_data)
            avail = "、".join(installed) if installed else "（无）"
            return {
                "ok": False,
                "error": (
                    f"shared script not found: {name}; 已安装: {avail}。"
                    "run_shared_script 不能跑工作区 .py，也没有 python/run_python 这类通用入口。"
                ),
            }
        return self._run_python(
            script_path,
            argv,
            self.workspace.root,
            allowed_roots=[script_path.parent],
        )

    def _run_python(
        self,
        script: Path,
        argv: list[str],
        cwd: Path,
        *,
        allowed_roots: list[Path] | None = None,
    ) -> dict:
        argv_roots = [self.workspace.root.resolve()]
        jail_roots = script_jail_roots(
            self.workspace.root,
            self._app_data,
            extra=list(allowed_roots or []),
        )
        if allowed_roots:
            seen_argv = {argv_roots[0]}
            for root in allowed_roots:
                resolved = Path(root).resolve()
                if resolved not in seen_argv:
                    argv_roots.append(resolved)
                    seen_argv.add(resolved)
        assert_argv_within_roots(argv, argv_roots)
        env = build_script_env()
        script_home = self.workspace.root / AGENT_WORK_REL / "script-home"
        script_home.mkdir(parents=True, exist_ok=True)
        env["HOME"] = str(script_home)
        env["USERPROFILE"] = str(script_home)
        env["OFFICE_AGENT_SCRIPT_JAIL"] = "1"
        src_root = Path(__file__).resolve().parent.parent
        existing_pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = (
            str(src_root)
            if not existing_pp
            else str(src_root) + os.pathsep + existing_pp
        )
        # PyInstaller sidecar: sys.executable is office-agent-runtime.exe.
        # Re-enter via --run-script so scripts get a real interpreter context.
        jail_args: list[str] = []
        for root in jail_roots:
            jail_args.extend(["--jail-root", str(Path(root).resolve())])
        if getattr(sys, "frozen", False):
            cmd = [self.python_bin, "--run-script", *jail_args, "--", str(script), *argv]
        else:
            cmd = [
                self.python_bin,
                "-m",
                "office_agent.script_jail_main",
                *jail_args,
                "--",
                str(script),
                *argv,
            ]
        isolate = bool(self.require_script_sandbox)
        if isolate and not sandbox_available() and sys.platform != "win32":
            raise ToolError(
                "本地部署要求脚本在隔离进程中运行，当前系统缺少 unshare/sandbox-exec"
            )
        if isolate and sandbox_available():
            cmd = wrap_isolated_cmd(cmd, workspace=self.workspace.root)
        run_kwargs: dict = {
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": SCRIPT_TIMEOUT_SEC,
            "env": env,
        }
        if os.name == "posix" and isolate:
            run_kwargs["preexec_fn"] = preexec_isolate
        try:
            proc = subprocess.run(cmd, **run_kwargs)
        except subprocess.TimeoutExpired as e:
            stdout, _ = truncate_output(e.stdout if isinstance(e.stdout, str) else "")
            stderr, _ = truncate_output(e.stderr if isinstance(e.stderr, str) else "")
            return {
                "ok": False,
                "exit_code": -1,
                "stdout": stdout,
                "stderr": (stderr + "\nscript timed out").strip(),
                "error": f"script timed out after {SCRIPT_TIMEOUT_SEC}s",
            }
        stdout, out_cut = truncate_output(proc.stdout)
        stderr, err_cut = truncate_output(proc.stderr)
        return {
            "ok": proc.returncode == 0,
            "exit_code": proc.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "truncated": out_cut or err_cut,
        }

    def _plan_path(self) -> Path:
        return self.workspace.root / PLAN_REL

    def _write_plan_html(self, plan: dict) -> None:
        self.workspace.ensure_layout()
        self.workspace.write_text(PLAN_HTML_REL, render_plan_html(plan))

    def _plan_get(self, args: dict) -> dict:
        plan = load_plan(self._plan_path())
        if plan is None:
            return {"ok": False, "reason": "missing"}
        return {"ok": True, "plan": plan}

    def _plan_create(self, args: dict) -> dict:
        path = self._plan_path()
        existing = load_plan(path)
        if existing is not None and existing.get("status") == "active":
            return {"ok": False, "error": "active plan already exists"}

        goal = str(args.get("goal") or "").strip()
        if not goal:
            return {"ok": False, "error": "goal is required"}

        raw_steps = args.get("steps")
        if not isinstance(raw_steps, list) or len(raw_steps) < 2:
            return {"ok": False, "error": "steps must contain at least 2 items"}

        steps: list[dict] = []
        for i, raw in enumerate(raw_steps):
            if not isinstance(raw, dict):
                return {"ok": False, "error": f"step {i} must be a dict"}
            step_id = raw.get("id")
            title = raw.get("title")
            if not isinstance(step_id, str) or not step_id:
                return {"ok": False, "error": f"step {i} missing id"}
            if not isinstance(title, str) or not title:
                return {"ok": False, "error": f"step {i} missing title"}
            steps.append(
                {
                    "id": step_id,
                    "title": title,
                    "detail": str(raw.get("detail") or ""),
                    "status": "pending",
                    "depends_on": list(raw.get("depends_on") or []),
                    "inputs": list(raw.get("inputs") or []),
                    "outputs": list(raw.get("outputs") or []),
                    "needs_user": bool(raw.get("needs_user") or False),
                    "notes": str(raw.get("notes") or ""),
                }
            )

        now = datetime.now(timezone.utc).isoformat()
        plan = {
            "version": 1,
            "id": f"plan_{uuid.uuid4().hex}",
            "goal": goal,
            "status": "active",
            "approval": "pending",
            "created_at": now,
            "updated_at": now,
            "steps": steps,
            "resume_hint": str(args.get("resume_hint") or "按工作计划未完成项继续"),
        }
        try:
            save_plan(path, plan)
            self._write_plan_html(plan)
        except PlanValidationError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "plan": plan}

    def _plan_update_step(self, args: dict) -> dict:
        path = self._plan_path()
        plan = load_plan(path)
        if plan is None:
            return {"ok": False, "error": "no plan found"}
        step_id = str(args.get("step_id") or "")
        if not step_id:
            return {"ok": False, "error": "step_id is required"}
        try:
            updated = apply_step_update(
                plan,
                step_id,
                status=args.get("status"),
                notes=args.get("notes"),
                outputs=args.get("outputs"),
            )
            save_plan(path, updated)
        except PlanValidationError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "plan": updated}

    def _plan_set_status(self, args: dict) -> dict:
        path = self._plan_path()
        plan = load_plan(path)
        if plan is None:
            return {"ok": False, "error": "no plan found"}
        status = str(args.get("status") or "")
        if not status:
            return {"ok": False, "error": "status is required"}
        try:
            updated = set_plan_status(plan, status)
            save_plan(path, updated)
        except PlanValidationError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "plan": updated}

    def _plan_set_approval(self, args: dict) -> dict:
        path = self._plan_path()
        plan = load_plan(path)
        if plan is None:
            return {"ok": False, "error": "no plan found"}
        approval = str(args.get("approval") or "")
        if not approval:
            return {"ok": False, "error": "approval is required"}
        try:
            updated = set_plan_approval(plan, approval)
            save_plan(path, updated)
            self._write_plan_html(updated)
        except PlanValidationError as e:
            return {"ok": False, "error": str(e)}
        return {"ok": True, "plan": updated}

    def _ask_user(self, args: dict) -> dict:
        q = str(args.get("question") or args.get("prompt") or "")
        return {"ok": True, "pending": True, "question": q, "prompt": q}

    def _finish(self, args: dict) -> dict:
        summary = str(args.get("summary", ""))
        raw = args.get("deliverables")
        if raw is None:
            return {"ok": True, "finished": True, "summary": summary}
        if not isinstance(raw, list):
            return {
                "ok": False,
                "error": "deliverables 须为字符串路径列表",
                "summary": summary,
            }
        paths: list[str] = []
        for item in raw:
            rel = _normalize_rel(str(item or "").strip())
            if not rel:
                continue
            paths.append(rel)
        if not paths:
            return {
                "ok": False,
                "error": "deliverables 为空；有文件产出时须列出工作成果路径",
                "summary": summary,
            }
        missing: list[str] = []
        empty: list[str] = []
        for rel in paths:
            try:
                path = self.workspace.resolve(rel)
            except SandboxError:
                missing.append(rel)
                continue
            if not path.is_file():
                missing.append(rel)
                continue
            if path.stat().st_size <= 0:
                empty.append(rel)
        if missing or empty:
            parts: list[str] = []
            if missing:
                parts.append("缺失: " + ", ".join(missing))
            if empty:
                parts.append("空文件: " + ", ".join(empty))
            return {
                "ok": False,
                "error": "交付物校验失败（" + "；".join(parts) + "）。请先写出文件再 finish。",
                "summary": summary,
                "missing": missing,
                "empty": empty,
            }
        return {
            "ok": True,
            "finished": True,
            "summary": summary,
            "deliverables": paths,
        }
