from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from office_agent.agent_loop import run_agent
from office_agent.auth import install_api_token_middleware
from office_agent.audit import AuditLog, workspace_hash
from office_agent.bundled_seed import seed_bundled_assets
from office_agent.cancel import CancelToken
from office_agent.config import AppConfig, merge_allowed_hosts
from office_agent.deployment import (
    PROFILE_LOCAL,
    PROFILE_STANDARD,
    is_intranet_model_host,
    is_known_public_ai_host,
    is_local_profile,
    model_host_from_api_base,
    resolve_deployment_profile,
)
from office_agent.diagnostic import configure as diagnostic_configure
from office_agent.diagnostic import emit as diag_emit
from office_agent.gateway import GatewayError, ModelGateway
from office_agent.paths import app_data_dir, write_private_text
from office_agent.secret_store import SEAL_PREFIX, seal_secret, unseal_secret
from office_agent.permissions import (
    NeedsInteractivePermission,
    PermissionGate,
    PermissionRequest,
)
from office_agent.session_store import SessionStore, history_to_ui_messages
from office_agent.skill_localize import needs_zh_display, try_localize_installed_skill
from office_agent.skill_validate import validate_skill_dir
from office_agent.skills import SkillError, SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import SandboxError, Workspace

logger = logging.getLogger(__name__)

def _default_config() -> AppConfig:
    if is_local_profile():
        return AppConfig(
            api_base="",
            api_key="",
            model="",
            allowed_hosts=["127.0.0.1", "localhost"],
            permission_mode="cautious",
            deployment_profile=PROFILE_LOCAL,
            allow_workspace_scripts=False,
            require_script_sandbox=True,
        )
    return AppConfig(
        api_base="https://api.deepseek.com",
        api_key="",
        model="deepseek-v4-flash",
        allowed_hosts=["api.deepseek.com", "127.0.0.1", "localhost"],
        deployment_profile=PROFILE_STANDARD,
        allow_workspace_scripts=False,
        require_script_sandbox=False,
    )


DEFAULT_CONFIG = _default_config()

# When False (tests), /shutdown returns ok but does not terminate the process.
ALLOW_PROCESS_EXIT = True


def _validate_attached_paths(ws: Workspace, paths: list[str]) -> list[str]:
    """Resolve each path inside the workspace; return workspace-relative strings."""
    validated: list[str] = []
    for p in paths:
        try:
            resolved = ws.resolve(p)
        except SandboxError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        validated.append(str(resolved.relative_to(ws.root)))
    return validated


def _config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> AppConfig:
    path = _config_path()
    if not path.is_file():
        return DEFAULT_CONFIG
    # PowerShell / Notepad may write UTF-8 BOM; utf-8-sig strips it.
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    api_base = str(data.get("api_base", DEFAULT_CONFIG.api_base))
    allowed = list(data.get("allowed_hosts", DEFAULT_CONFIG.allowed_hosts))
    profile = resolve_deployment_profile(str(data.get("deployment_profile", DEFAULT_CONFIG.deployment_profile)))
    allow_scripts = bool(data.get("allow_workspace_scripts", DEFAULT_CONFIG.allow_workspace_scripts))
    require_sandbox = bool(data.get("require_script_sandbox", DEFAULT_CONFIG.require_script_sandbox))
    if profile == PROFILE_LOCAL:
        allow_scripts = False
        require_sandbox = True
        host = model_host_from_api_base(api_base)
        if host and is_known_public_ai_host(host):
            api_base = ""
            allowed = ["127.0.0.1", "localhost"]
    permission_mode = str(data.get("permission_mode", DEFAULT_CONFIG.permission_mode))
    if profile == PROFILE_LOCAL and permission_mode == "standard" and "permission_mode" not in data:
        permission_mode = "cautious"
    raw_key = str(data.get("api_key", DEFAULT_CONFIG.api_key))
    cfg = AppConfig(
        api_base=api_base,
        api_key=unseal_secret(raw_key),
        model=str(data.get("model", DEFAULT_CONFIG.model)),
        allowed_hosts=merge_allowed_hosts(api_base, allowed),
        permission_mode=permission_mode,
        max_tool_steps=int(data.get("max_tool_steps", DEFAULT_CONFIG.max_tool_steps)),
        deployment_profile=profile,
        allow_workspace_scripts=allow_scripts,
        require_script_sandbox=require_sandbox,
    )
    if raw_key and not raw_key.startswith(SEAL_PREFIX):
        try:
            save_config(cfg)
        except OSError:
            logger.warning("could not re-seal legacy api_key on disk")
    return cfg


def save_config(cfg: AppConfig) -> None:
    payload = {
        "api_base": cfg.api_base,
        "api_key": seal_secret(cfg.api_key),
        "model": cfg.model,
        "allowed_hosts": cfg.allowed_hosts,
        "permission_mode": cfg.permission_mode,
        "max_tool_steps": cfg.max_tool_steps,
        "deployment_profile": cfg.resolved_profile(),
        "allow_workspace_scripts": cfg.allow_workspace_scripts,
        "require_script_sandbox": cfg.require_script_sandbox,
    }
    write_private_text(_config_path(), json.dumps(payload, ensure_ascii=False, indent=2))


def _default_audit() -> AuditLog:
    return AuditLog(app_data_dir() / "db" / "audit.sqlite")


@dataclass
class ProcessState:
    config: AppConfig = field(default_factory=load_config)
    registry: SkillRegistry = field(default_factory=SkillRegistry)
    sessions: SessionStore = field(default_factory=SessionStore)
    audit: AuditLog = field(default_factory=_default_audit)
    workspace: Workspace | None = None
    gateway_factory: Callable[[AppConfig], Any] = ModelGateway
    # Soft-fail localize attempts this process (avoid re-calling LLM on every refresh)
    zh_locale_tried: set[str] = field(default_factory=set)
    # request_id → interactive PermissionGate awaiting resolve
    gates: dict[str, PermissionGate] = field(default_factory=dict)
    # session_id → CancelToken for the in-flight agent turn
    active_cancel: dict[str, CancelToken] = field(default_factory=dict)
    # session_id → PermissionGate for the in-flight stream turn
    active_gates: dict[str, PermissionGate] = field(default_factory=dict)

    @classmethod
    def load(cls) -> ProcessState:
        return cls(config=load_config())

    def require_workspace(self) -> Workspace:
        if self.workspace is None:
            raise HTTPException(status_code=400, detail="workspace not open")
        return self.workspace

    def maybe_localize_skill(self, meta: Any) -> Any:
        """Translate UI fields into installed SKILL.md when needed; never raises."""
        if not needs_zh_display(meta):
            return meta
        if meta.id in self.zh_locale_tried:
            return meta
        self.zh_locale_tried.add(meta.id)
        return try_localize_installed_skill(meta, self.gateway_factory, self.config)


class OpenWorkspaceBody(BaseModel):
    path: str


class InstallSkillBody(BaseModel):
    path: str
    enabled: bool = True
    apply_fixes: bool = False
    force_overwrite: bool = False


class SetEnabledBody(BaseModel):
    enabled: bool


class ConfigBody(BaseModel):
    api_base: str | None = None
    allowed_hosts: list[str] | None = None
    api_key: str | None = None
    model: str | None = None
    permission_mode: str | None = None
    allow_workspace_scripts: bool | None = None


class ChatBody(BaseModel):
    message: str
    attached_paths: list[str] = Field(default_factory=list)
    session_id: str | None = None


class PermissionBody(BaseModel):
    allow: bool


class CancelChatBody(BaseModel):
    session_id: str


class CreateSessionBody(BaseModel):
    workspace_path: str | None = None


@asynccontextmanager
async def _app_lifespan(app: FastAPI):
    t = threading.Thread(target=seed_bundled_assets, name="seed-bundled", daemon=True)
    t.start()
    yield


def create_app(state: ProcessState | None = None) -> FastAPI:
    diagnostic_configure()
    office = state if state is not None else ProcessState.load()
    app = FastAPI(title="Office Agent Runtime", lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:1420",
            "http://localhost:1420",
            "http://tauri.localhost",
            "https://tauri.localhost",
            "tauri://localhost",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_api_token_middleware(app)
    app.state.office = office

    @app.get("/health")
    def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/shutdown")
    async def shutdown(request: Request) -> dict[str, bool]:
        """Graceful stop for the packaged sidecar (localhost only)."""
        client = request.client.host if request.client else ""
        if client not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(status_code=403, detail="localhost only")

        async def _exit_soon() -> None:
            await asyncio.sleep(0.25)
            if ALLOW_PROCESS_EXIT:
                os._exit(0)

        asyncio.create_task(_exit_soon())
        return {"ok": True}

    @app.get("/config")
    def get_config() -> dict[str, Any]:
        cfg = office.config
        key = cfg.api_key or ""
        masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("***" if key else "")
        return {
            "api_base": cfg.api_base,
            "api_key_masked": masked,
            "api_key_set": bool(key),
            "model": cfg.model,
            "allowed_hosts": cfg.allowed_hosts,
            "permission_mode": cfg.permission_mode,
            "max_tool_steps": cfg.max_tool_steps,
            "deployment_profile": cfg.resolved_profile(),
            "allow_workspace_scripts": cfg.allow_workspace_scripts,
            "require_script_sandbox": cfg.require_script_sandbox,
        }

    @app.post("/workspace/open")
    def workspace_open(body: OpenWorkspaceBody) -> dict[str, Any]:
        root = Path(body.path).expanduser()
        try:
            office.workspace = Workspace(root)
            office.workspace.ensure_layout()
        except SandboxError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "path": str(office.workspace.root)}

    @app.get("/workspace/tree")
    def workspace_tree() -> dict[str, Any]:
        ws = office.require_workspace()
        return {"entries": ws.list_dir(".")}

    @app.get("/sessions")
    def list_sessions(workspace_path: str | None = None) -> dict[str, Any]:
        if workspace_path:
            path = str(Path(workspace_path).expanduser().resolve())
        else:
            ws = office.require_workspace()
            path = str(ws.root)
        return {"sessions": office.sessions.list_sessions(path)}

    @app.post("/sessions")
    def create_session(body: CreateSessionBody | None = None) -> dict[str, Any]:
        body = body or CreateSessionBody()
        if body.workspace_path:
            path = str(Path(body.workspace_path).expanduser().resolve())
        else:
            ws = office.require_workspace()
            path = str(ws.root)
        sid = office.sessions.create_session(path)
        meta = office.sessions.get_session(sid)
        return {"ok": True, "session": meta}

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> dict[str, Any]:
        meta = office.sessions.get_session(session_id)
        if not meta:
            raise HTTPException(status_code=404, detail="session not found")
        return {"session": meta}

    @app.get("/sessions/{session_id}/messages")
    def get_session_messages(session_id: str) -> dict[str, Any]:
        if not office.sessions.session_exists(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        raw = office.sessions.get_messages(session_id)
        return {
            "messages": history_to_ui_messages(raw),
            "raw_count": len(raw),
        }

    @app.delete("/sessions/{session_id}")
    def delete_session(session_id: str) -> dict[str, Any]:
        if not office.sessions.delete_session(session_id):
            raise HTTPException(status_code=404, detail="session not found")
        return {"ok": True, "id": session_id}

    @app.get("/skills")
    def list_skills() -> dict[str, Any]:
        skills = []
        for m in office.registry.scan():
            m = office.maybe_localize_skill(m)
            skills.append(office.registry.meta_payload(m))
        return {"skills": skills}

    def _skill_error_detail(exc: SkillError) -> dict[str, Any] | str:
        validation = getattr(exc, "validation", None)
        if not validation:
            return str(exc)
        return {
            "error": str(exc),
            "errors": list(validation.get("errors") or []),
            "warnings": list(validation.get("warnings") or []),
            "validation": {
                "ok": bool(validation.get("ok")),
                "errors": list(validation.get("errors") or []),
                "warnings": list(validation.get("warnings") or []),
            },
        }

    @app.post("/skills/inspect")
    def inspect_skill(body: InstallSkillBody) -> dict[str, Any]:
        src = Path(body.path).expanduser()
        try:
            meta, validation = office.registry.inspect_with_validation(src)
        except SkillError as e:
            raise HTTPException(status_code=400, detail=_skill_error_detail(e)) from e
        return {
            "skill": office.registry.meta_payload(meta),
            "validation": {
                "ok": bool(validation.get("ok")),
                "errors": list(validation.get("errors") or []),
                "warnings": list(validation.get("warnings") or []),
            },
            "auto_fixes": list(validation.get("auto_fixes") or []),
            "can_install_with_fixes": bool(
                validation.get("can_install_with_fixes")
                if "can_install_with_fixes" in validation
                else validation.get("ok")
            ),
            "replace": office.registry.replace_info(meta),
        }

    @app.post("/skills/install")
    def install_skill(body: InstallSkillBody) -> dict[str, Any]:
        src = Path(body.path).expanduser()
        try:
            meta = office.registry.install_path(
                src,
                enabled=body.enabled,
                apply_fixes=body.apply_fixes,
                force_overwrite=body.force_overwrite,
            )
        except SkillError as e:
            raise HTTPException(status_code=400, detail=_skill_error_detail(e)) from e
        # Allow a fresh localize attempt after (re)install
        office.zh_locale_tried.discard(meta.id)
        meta = office.maybe_localize_skill(meta)
        # Install already gated on ok; re-check for warnings in the response body.
        installed = office.registry.skills_dir / meta.id
        validation = (
            validate_skill_dir(installed)
            if installed.is_dir()
            else {"ok": True, "errors": [], "warnings": []}
        )
        return {
            "ok": True,
            "skill": office.registry.meta_payload(meta),
            "validation": {
                "ok": bool(validation.get("ok")),
                "errors": list(validation.get("errors") or []),
                "warnings": list(validation.get("warnings") or []),
            },
        }

    @app.post("/skills/{skill_id}/enabled")
    def set_skill_enabled(skill_id: str, body: SetEnabledBody) -> dict[str, Any]:
        known = {m.id for m in office.registry.scan()}
        if skill_id not in known:
            raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
        office.registry.set_enabled(skill_id, body.enabled)
        return {"ok": True, "id": skill_id, "enabled": body.enabled}

    @app.post("/skills/{skill_id}/restore-bundled")
    def restore_bundled_skill(skill_id: str) -> dict[str, Any]:
        try:
            meta = office.registry.restore_bundled(skill_id)
        except SkillError as e:
            raise HTTPException(status_code=400, detail=_skill_error_detail(e)) from e
        office.zh_locale_tried.discard(meta.id)
        meta = office.maybe_localize_skill(meta)
        return {"ok": True, "skill": office.registry.meta_payload(meta)}

    @app.delete("/skills/{skill_id}")
    def uninstall_skill(skill_id: str) -> dict[str, Any]:
        try:
            office.registry.uninstall(skill_id)
        except SkillError as e:
            # Bundled policy / not found → 400 so UI can show the message
            raise HTTPException(status_code=400, detail=_skill_error_detail(e)) from e
        office.zh_locale_tried.discard(skill_id)
        return {"ok": True, "id": skill_id}

    @app.post("/config")
    def update_config(body: ConfigBody) -> dict[str, Any]:
        cfg = office.config
        old = {
            "api_base": cfg.api_base,
            "allowed_hosts": list(cfg.allowed_hosts),
            "api_key": cfg.api_key,
            "model": cfg.model,
            "permission_mode": cfg.permission_mode,
            "allow_workspace_scripts": cfg.allow_workspace_scripts,
        }

        if body.api_base is not None:
            new_base = body.api_base.strip()
            if cfg.resolved_profile() == PROFILE_LOCAL and new_base:
                host = model_host_from_api_base(new_base)
                if not is_intranet_model_host(host):
                    office.audit.record_event(
                        "model_host_rejected",
                        outcome="deny",
                        error_code="model_host_rejected",
                        attrs={"host": host, "profile": "local"},
                    )
                    raise HTTPException(
                        status_code=400,
                        detail="本地部署版本仅允许本机或内网模型地址",
                    )
            cfg.api_base = new_base
        if body.allowed_hosts is not None:
            cfg.allowed_hosts = body.allowed_hosts
        if body.api_base is not None:
            # Auto-allow the configured API host so users never manage the allowlist.
            cfg.allowed_hosts = merge_allowed_hosts(
                cfg.api_base,
                cfg.allowed_hosts,
            )
        if body.api_key is not None:
            cfg.api_key = body.api_key
        if body.model is not None:
            cfg.model = body.model
        if body.permission_mode is not None:
            mode = body.permission_mode.strip()
            if mode not in ("cautious", "standard", "trust_workspace"):
                raise HTTPException(
                    status_code=400,
                    detail="permission_mode must be cautious|standard|trust_workspace",
                )
            cfg.permission_mode = mode
        if body.allow_workspace_scripts is not None:
            cfg.allow_workspace_scripts = bool(body.allow_workspace_scripts)

        changes: dict[str, Any] = {}
        keys: list[str] = []

        def _note(key: str, old_v: Any, new_v: Any) -> None:
            if old_v == new_v:
                return
            keys.append(key)
            if key == "api_key":
                # Never persist credential values; keys list still records the change.
                return
            changes[key] = {"old": old_v, "new": new_v}

        _note("api_base", old["api_base"], cfg.api_base)
        _note("allowed_hosts", old["allowed_hosts"], list(cfg.allowed_hosts))
        _note("api_key", old["api_key"], cfg.api_key)
        _note("model", old["model"], cfg.model)
        _note("permission_mode", old["permission_mode"], cfg.permission_mode)
        _note(
            "allow_workspace_scripts",
            old["allow_workspace_scripts"],
            cfg.allow_workspace_scripts,
        )

        if keys:
            office.audit.record_event(
                "config_changed",
                attrs={"keys": keys, **changes},
            )
        save_config(cfg)
        return {"ok": True}

    @app.post("/chat/permissions/{request_id}")
    def resolve_permission(request_id: str, body: PermissionBody) -> dict[str, Any]:
        gate = office.gates.get(request_id)
        if gate is None:
            raise HTTPException(status_code=404, detail="unknown permission request")
        try:
            gate.resolve(request_id, body.allow)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        office.gates.pop(request_id, None)
        return {"ok": True}

    @app.post("/chat/cancel")
    def cancel_chat(body: CancelChatBody) -> dict[str, Any]:
        token = office.active_cancel.get(body.session_id)
        if token is None:
            raise HTTPException(status_code=404, detail="no active chat for session")
        token.cancel()
        # Unblock PermissionGate.wait so cancelled turns do not run the tool.
        gate = office.active_gates.get(body.session_id)
        if gate is not None:
            for request_id in gate.cancel_all():
                office.gates.pop(request_id, None)
        return {"ok": True}

    def _record_gateway_error(e: GatewayError) -> None:
        event_type = (
            "model_host_rejected"
            if e.error_code == "model_host_rejected"
            else "gateway_error"
        )
        attrs: dict[str, Any] | None = None
        if e.host_class:
            attrs = {"host_class": e.host_class}
        office.audit.record_event(
            event_type,
            outcome="error",
            error_code=e.error_code,
            detail=str(e),
            attrs=attrs,
        )
        diag_emit(
            "gateway_error",
            level="error",
            error_code=e.error_code,
            host_class=e.host_class or None,
        )

    def _chat_start_attrs(route: str) -> dict[str, Any]:
        attrs: dict[str, Any] = {"route": route}
        if office.workspace is not None:
            attrs["workspace_hash"] = workspace_hash(office.workspace.root)
        return attrs

    def _prepare_chat(
        body: ChatBody,
        *,
        interactive: bool = False,
        turn_id: str | None = None,
    ) -> tuple[
        str,
        Any,
        ToolExecutor | None,
        list[dict[str, Any]],
        list[str],
        int,
        list[dict[str, Any]],
    ]:
        # Sidecar restarts drop in-memory workspace; recover from session path.
        if office.workspace is None and body.session_id:
            meta = office.sessions.get_session(body.session_id)
            wp = (meta or {}).get("workspace_path") or ""
            if wp:
                try:
                    office.workspace = Workspace(Path(wp))
                    office.workspace.ensure_layout()
                except SandboxError as e:
                    raise HTTPException(status_code=400, detail=str(e)) from e

        onboarding = office.workspace is None
        if onboarding:
            if body.attached_paths:
                raise HTTPException(
                    status_code=400, detail="请先打开文件夹后再附加文件"
                )
            session_id = body.session_id
            if session_id:
                if not office.sessions.session_exists(session_id):
                    raise HTTPException(status_code=404, detail="session not found")
            else:
                session_id = office.sessions.create_session("")
            try:
                gateway = office.gateway_factory(office.config)
            except GatewayError as e:
                _record_gateway_error(e)
                raise HTTPException(status_code=400, detail=str(e)) from e
            history = office.sessions.get_messages(session_id)
            return (
                session_id,
                gateway,
                None,
                [],
                [],
                office.config.max_tool_steps,
                history,
            )

        ws = office.require_workspace()
        session_id = body.session_id
        if session_id:
            if not office.sessions.session_exists(session_id):
                raise HTTPException(status_code=404, detail="session not found")
        else:
            session_id = office.sessions.create_session(str(ws.root))

        try:
            gateway = office.gateway_factory(office.config)
        except GatewayError as e:
            _record_gateway_error(e)
            raise HTTPException(status_code=400, detail=str(e)) from e

        gate = PermissionGate(
            office.config.permission_mode,
            destination_host=model_host_from_api_base(office.config.api_base),
        )
        gate.set_auto(None if interactive else False)
        attached = _validate_attached_paths(ws, body.attached_paths)
        tools = ToolExecutor(
            ws,
            office.registry,
            permission_mode=office.config.permission_mode,
            audit=office.audit,
            gate=gate,
            turn_id=turn_id,
            session_id=session_id,
            attached_paths=attached,
            allow_workspace_scripts=office.config.allow_workspace_scripts,
            require_script_sandbox=office.config.require_script_sandbox
            or office.config.resolved_profile() == PROFILE_LOCAL,
            destination_host=model_host_from_api_base(office.config.api_base),
        )
        catalog = office.registry.enabled_catalog()
        history = office.sessions.get_messages(session_id)
        return (
            session_id,
            gateway,
            tools,
            catalog,
            attached,
            office.config.max_tool_steps,
            history,
        )

    def _sse(event: str, data: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"

    @app.post("/chat")
    async def chat(body: ChatBody) -> dict[str, Any]:
        """Run agent off the event loop so /health stays responsive during long chats."""
        session_id, gateway, tools, catalog, attached, max_steps, history = _prepare_chat(body)
        message = body.message
        started = time.monotonic()
        diag_emit("chat_started", session_id=session_id)
        office.audit.record_event(
            "chat_started",
            session_id=session_id,
            attrs=_chat_start_attrs("/chat"),
        )

        def _run() -> Any:
            return run_agent(
                message,
                attached,
                gateway,
                tools,
                catalog,
                max_steps,
                history=history,
                onboarding=tools is None,
            )

        status = "ok"
        steps = 0
        try:
            try:
                result = await asyncio.to_thread(_run)
            except NeedsInteractivePermission as e:
                status = "error"
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "needs_interactive_permission",
                        "tool": e.tool,
                        "summary": e.summary,
                        "hint": "use POST /chat/stream and confirm via /chat/permissions/{id}",
                    },
                ) from e
            except Exception as e:
                status = "error"
                raise HTTPException(status_code=500, detail=f"agent error: {e}") from e

            steps = len(result.tool_events)
            try:
                office.sessions.append_messages(session_id, result.messages)
            except Exception:
                diag_emit("session_persist_failed", level="error", session_id=session_id)
                logger.warning(
                    "failed to append messages for session %s",
                    session_id,
                    exc_info=True,
                )
            return {
                "reply": result.final_text,
                "tool_events": result.tool_events,
                "session_id": session_id,
            }
        finally:
            diag_emit(
                "chat_finished",
                session_id=session_id,
                duration_ms=int((time.monotonic() - started) * 1000),
                status=status,
                steps=steps,
            )

    @app.post("/chat/stream")
    async def chat_stream(body: ChatBody) -> StreamingResponse:
        """SSE progress for one chat turn: started/status/tool_*/permission_request/final/error."""
        prepared_turn_id = str(uuid4())
        session_id, gateway, tools, catalog, attached, max_steps, history = _prepare_chat(
            body, interactive=True, turn_id=prepared_turn_id
        )
        message = body.message
        turn_id = tools.turn_id if tools is not None else prepared_turn_id
        event_q: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            event_q.put((event, data))

        def on_event(payload: dict[str, Any]) -> None:
            event_type = str(payload.get("type") or "status")
            data = {k: v for k, v in payload.items() if k != "type"}
            emit(event_type, data)

        gate = tools.gate if tools is not None else None

        if gate is not None:

            def on_permission_request(req: PermissionRequest) -> None:
                office.gates[req.id] = gate
                emit(
                    "permission_request",
                    {
                        "id": req.id,
                        "tool": req.tool,
                        "summary": req.summary,
                        "session_id": session_id,
                        "destination": req.destination,
                        "path": req.path,
                    },
                )

            gate.on_request = on_permission_request
            gate.on_timeout = lambda request_id: office.gates.pop(request_id, None)

        cancel_token = CancelToken()
        office.active_cancel[session_id] = cancel_token
        if gate is not None:
            office.active_gates[session_id] = gate

        def worker() -> None:
            started = time.monotonic()
            status = "ok"
            steps = 0
            try:
                diag_emit("chat_started", session_id=session_id, turn_id=turn_id)
                office.audit.record_event(
                    "chat_started",
                    session_id=session_id,
                    turn_id=turn_id,
                    attrs=_chat_start_attrs("/chat/stream"),
                )
                emit("started", {"session_id": session_id, "turn_id": turn_id})
                result = run_agent(
                    message,
                    attached,
                    gateway,
                    tools,
                    catalog,
                    max_steps,
                    history=history,
                    on_event=on_event,
                    cancel=cancel_token,
                    turn_id=turn_id,
                    onboarding=tools is None,
                )
                steps = len(result.tool_events)
                # Best-effort: persist whatever the turn produced (incl. cancel truncation).
                try:
                    office.sessions.append_messages(session_id, result.messages)
                except Exception:
                    diag_emit(
                        "session_persist_failed",
                        level="error",
                        session_id=session_id,
                    )
                    logger.warning(
                        "failed to append messages for session %s",
                        session_id,
                        exc_info=True,
                    )
                emit(
                    "final",
                    {
                        "reply": result.final_text,
                        "tool_events": result.tool_events,
                        "session_id": session_id,
                    },
                )
            except Exception as e:
                status = "error"
                emit("error", {"message": f"agent error: {e}"})
            finally:
                diag_emit(
                    "chat_finished",
                    session_id=session_id,
                    turn_id=turn_id,
                    duration_ms=int((time.monotonic() - started) * 1000),
                    status=status,
                    steps=steps,
                )
                office.active_cancel.pop(session_id, None)
                office.active_gates.pop(session_id, None)
                event_q.put(None)

        threading.Thread(target=worker, daemon=True).start()

        async def event_gen():
            while True:
                item = await asyncio.to_thread(event_q.get)
                if item is None:
                    break
                event, data = item
                yield _sse(event, data)

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


app = create_app()
