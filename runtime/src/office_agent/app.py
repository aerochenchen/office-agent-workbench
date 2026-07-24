from __future__ import annotations

import asyncio
import json
import queue
import threading
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from office_agent.agent_loop import run_agent
from office_agent.bundled_seed import seed_bundled_assets
from office_agent.config import AppConfig
from office_agent.gateway import GatewayError, ModelGateway
from office_agent.paths import app_data_dir
from office_agent.session_store import SessionStore
from office_agent.skills import SkillError, SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import SandboxError, Workspace

DEFAULT_CONFIG = AppConfig(
    api_base="https://api.deepseek.com/v1",
    api_key="",
    model="deepseek-v4-flash",
    allowed_hosts=["api.deepseek.com", "127.0.0.1", "localhost"],
)


def _config_path() -> Path:
    return app_data_dir() / "config.json"


def load_config() -> AppConfig:
    path = _config_path()
    if not path.is_file():
        return DEFAULT_CONFIG
    data = json.loads(path.read_text(encoding="utf-8"))
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


@dataclass
class ProcessState:
    config: AppConfig = field(default_factory=load_config)
    registry: SkillRegistry = field(default_factory=SkillRegistry)
    sessions: SessionStore = field(default_factory=SessionStore)
    workspace: Workspace | None = None
    gateway_factory: Callable[[AppConfig], Any] = ModelGateway

    @classmethod
    def load(cls) -> ProcessState:
        return cls(config=load_config())

    def require_workspace(self) -> Workspace:
        if self.workspace is None:
            raise HTTPException(status_code=400, detail="workspace not open")
        return self.workspace


class OpenWorkspaceBody(BaseModel):
    path: str


class InstallSkillBody(BaseModel):
    path: str


class SetEnabledBody(BaseModel):
    enabled: bool


class ConfigBody(BaseModel):
    api_base: str | None = None
    allowed_hosts: list[str] | None = None
    api_key: str | None = None
    model: str | None = None


class ChatBody(BaseModel):
    message: str
    attached_paths: list[str] = Field(default_factory=list)
    session_id: str | None = None


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

    @app.get("/config")
    def get_config() -> dict[str, Any]:
        cfg = office.config
        key = cfg.api_key or ""
        masked = (key[:6] + "…" + key[-4:]) if len(key) > 12 else ("***" if key else "")
        return {
            "api_base": cfg.api_base,
            "api_key": key,
            "api_key_masked": masked,
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
        except SandboxError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {"ok": True, "path": str(office.workspace.root)}

    @app.get("/workspace/tree")
    def workspace_tree() -> dict[str, Any]:
        ws = office.require_workspace()
        return {"entries": ws.list_dir(".")}

    @app.get("/skills")
    def list_skills() -> dict[str, Any]:
        skills = [
            {
                "id": m.id,
                "name": m.name,
                "description": m.description,
                "version": m.version,
                "tier": m.tier,
                "min_ram_gb": m.min_ram_gb,
                "enabled": m.enabled,
            }
            for m in office.registry.scan()
        ]
        return {"skills": skills}

    @app.post("/skills/install")
    def install_skill(body: InstallSkillBody) -> dict[str, Any]:
        src = Path(body.path).expanduser()
        try:
            meta = office.registry.install_dir(src)
        except SkillError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return {
            "ok": True,
            "skill": {
                "id": meta.id,
                "name": meta.name,
                "tier": meta.tier,
                "min_ram_gb": meta.min_ram_gb,
            },
        }

    @app.post("/skills/{skill_id}/enabled")
    def set_skill_enabled(skill_id: str, body: SetEnabledBody) -> dict[str, Any]:
        known = {m.id for m in office.registry.scan()}
        if skill_id not in known:
            raise HTTPException(status_code=404, detail=f"skill not found: {skill_id}")
        office.registry.set_enabled(skill_id, body.enabled)
        return {"ok": True, "id": skill_id, "enabled": body.enabled}

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
        save_config(office.config)
        return {"ok": True}

    def _prepare_chat(body: ChatBody) -> tuple[str, Any, ToolExecutor, list[dict[str, Any]], list[str], int, list[dict[str, Any]]]:
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

        tools = ToolExecutor(
            ws,
            office.registry,
            permission_mode=office.config.permission_mode,
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
        """SSE progress for one chat turn: started/status/tool_*/final/error."""
        session_id, gateway, tools, catalog, attached, max_steps, history = _prepare_chat(body)
        message = body.message
        event_q: queue.Queue[tuple[str, dict[str, Any]] | None] = queue.Queue()

        def emit(event: str, data: dict[str, Any]) -> None:
            event_q.put((event, data))

        def on_event(payload: dict[str, Any]) -> None:
            event_type = str(payload.get("type") or "status")
            data = {k: v for k, v in payload.items() if k != "type"}
            emit(event_type, data)

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
                )
                office.sessions.append_messages(session_id, result.messages)
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
