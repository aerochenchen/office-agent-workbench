from __future__ import annotations

import asyncio
import json
import logging
import os
import queue
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from office_agent.agent_loop import run_agent
from office_agent.audit import AuditLog
from office_agent.bundled_seed import seed_bundled_assets
from office_agent.cancel import CancelToken
from office_agent.config import AppConfig
from office_agent.gateway import GatewayError, ModelGateway
from office_agent.paths import app_data_dir
from office_agent.permissions import PermissionGate, PermissionRequest
from office_agent.session_store import SessionStore, history_to_ui_messages
from office_agent.skill_localize import needs_zh_display, try_localize_installed_skill
from office_agent.skills import SkillError, SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import SandboxError, Workspace

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = AppConfig(
    api_base="https://api.deepseek.com/v1",
    api_key="",
    model="deepseek-v4-flash",
    allowed_hosts=["api.deepseek.com", "127.0.0.1", "localhost"],
)

# When False (tests), /shutdown returns ok but does not terminate the process.
ALLOW_PROCESS_EXIT = True


def _config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> AppConfig:
    path = _config_path()
    if not path.is_file():
        return DEFAULT_CONFIG
    # PowerShell / Notepad may write UTF-8 BOM; utf-8-sig strips it.
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    return AppConfig(
        api_base=str(data.get("api_base", DEFAULT_CONFIG.api_base)),
        api_key=str(data.get("api_key", DEFAULT_CONFIG.api_key)),
        model=str(data.get("model", DEFAULT_CONFIG.model)),
        allowed_hosts=list(data.get("allowed_hosts", DEFAULT_CONFIG.allowed_hosts)),
        permission_mode=str(data.get("permission_mode", DEFAULT_CONFIG.permission_mode)),
        max_tool_steps=int(data.get("max_tool_steps", DEFAULT_CONFIG.max_tool_steps)),
    )


def save_config(cfg: AppConfig) -> None:
    payload = {
        "api_base": cfg.api_base,
        "api_key": cfg.api_key,
        "model": cfg.model,
        "allowed_hosts": cfg.allowed_hosts,
        "permission_mode": cfg.permission_mode,
        "max_tool_steps": cfg.max_tool_steps,
    }
    _config_path().write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


class SetEnabledBody(BaseModel):
    enabled: bool


class ConfigBody(BaseModel):
    api_base: str | None = None
    allowed_hosts: list[str] | None = None
    api_key: str | None = None
    model: str | None = None
    permission_mode: str | None = None


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
    seed_bundled_assets()
    yield


def create_app(state: ProcessState | None = None) -> FastAPI:
    office = state if state is not None else ProcessState.load()
    app = FastAPI(title="Office Agent Runtime", lifespan=_app_lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
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
            skills.append(
                {
                    "id": m.id,
                    "name": m.ui_name,
                    "display_name": m.display_name or m.ui_name,
                    "description": m.description,
                    "version": m.version,
                    "tier": m.tier,
                    "min_ram_gb": m.min_ram_gb,
                    "permissions": m.permissions,
                    "enabled": m.enabled,
                }
            )
        return {"skills": skills}

    @app.post("/skills/inspect")
    def inspect_skill(body: InstallSkillBody) -> dict[str, Any]:
        src = Path(body.path).expanduser()
        try:
            meta = office.registry.inspect_path(src)
        except SkillError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"skill": office.registry.meta_payload(meta)}

    @app.post("/skills/install")
    def install_skill(body: InstallSkillBody) -> dict[str, Any]:
        src = Path(body.path).expanduser()
        try:
            meta = office.registry.install_path(src, enabled=body.enabled)
        except SkillError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        # Allow a fresh localize attempt after (re)install
        office.zh_locale_tried.discard(meta.id)
        meta = office.maybe_localize_skill(meta)
        return {"ok": True, "skill": office.registry.meta_payload(meta)}

    @app.post("/skills/{skill_id}/enabled")
    def set_skill_enabled(skill_id: str, body: SetEnabledBody) -> dict[str, Any]:
        known = {m.id for m in office.registry.scan()}
        if skill_id not in known:
            raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
        office.registry.set_enabled(skill_id, body.enabled)
        return {"ok": True, "id": skill_id, "enabled": body.enabled}

    @app.delete("/skills/{skill_id}")
    def uninstall_skill(skill_id: str) -> dict[str, Any]:
        try:
            office.registry.uninstall(skill_id)
        except SkillError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        office.zh_locale_tried.discard(skill_id)
        return {"ok": True, "id": skill_id}

    @app.post("/config")
    def update_config(body: ConfigBody) -> dict[str, Any]:
        if body.api_base is not None:
            office.config.api_base = body.api_base
        if body.allowed_hosts is not None:
            office.config.allowed_hosts = body.allowed_hosts
        if body.api_key is not None:
            office.config.api_key = body.api_key
        if body.model is not None:
            office.config.model = body.model
        if body.permission_mode is not None:
            mode = body.permission_mode.strip()
            if mode not in ("cautious", "standard", "trust_workspace"):
                raise HTTPException(
                    status_code=400,
                    detail="permission_mode must be cautious|standard|trust_workspace",
                )
            office.config.permission_mode = mode
        save_config(office.config)
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
        return {"ok": True}

    def _prepare_chat(
        body: ChatBody,
        *,
        interactive: bool = False,
    ) -> tuple[str, Any, ToolExecutor, list[dict[str, Any]], list[str], int, list[dict[str, Any]]]:
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
            raise HTTPException(status_code=400, detail=str(e)) from e

        gate = PermissionGate(office.config.permission_mode)
        gate.set_auto(None if interactive else True)
        tools = ToolExecutor(
            ws,
            office.registry,
            permission_mode=office.config.permission_mode,
            audit=office.audit,
            gate=gate,
        )
        catalog = office.registry.enabled_catalog()
        history = office.sessions.get_messages(session_id)
        return (
            session_id,
            gateway,
            tools,
            catalog,
            list(body.attached_paths),
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

        def _run() -> Any:
            return run_agent(
                message,
                attached,
                gateway,
                tools,
                catalog,
                max_steps,
                history=history,
            )

        try:
            result = await asyncio.to_thread(_run)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"agent error: {e}") from e

        office.sessions.append_messages(session_id, result.messages)
        return {
            "reply": result.final_text,
            "tool_events": result.tool_events,
            "session_id": session_id,
        }

    @app.post("/chat/stream")
    async def chat_stream(body: ChatBody) -> StreamingResponse:
        """SSE progress for one chat turn: started/status/tool_*/permission_request/final/error."""
        session_id, gateway, tools, catalog, attached, max_steps, history = _prepare_chat(
            body, interactive=True
        )
        message = body.message
        event_q: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            event_q.put((event, data))

        def on_event(payload: dict[str, Any]) -> None:
            event_type = str(payload.get("type") or "status")
            data = {k: v for k, v in payload.items() if k != "type"}
            emit(event_type, data)

        gate = tools.gate

        def on_permission_request(req: PermissionRequest) -> None:
            office.gates[req.id] = gate
            emit(
                "permission_request",
                {
                    "id": req.id,
                    "tool": req.tool,
                    "summary": req.summary,
                    "session_id": session_id,
                },
            )

        gate.on_request = on_permission_request
        gate.on_timeout = lambda request_id: office.gates.pop(request_id, None)

        cancel_token = CancelToken()
        office.active_cancel[session_id] = cancel_token

        def worker() -> None:
            try:
                emit("started", {"session_id": session_id})
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
                )
                # Best-effort: persist whatever the turn produced (incl. cancel truncation).
                try:
                    office.sessions.append_messages(session_id, result.messages)
                except Exception:
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
                emit("error", {"message": f"agent error: {e}"})
            finally:
                office.active_cancel.pop(session_id, None)
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
