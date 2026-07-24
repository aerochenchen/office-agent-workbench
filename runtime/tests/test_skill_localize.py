from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from office_agent.app import ProcessState, create_app
from office_agent.config import AppConfig
from office_agent.session_store import SessionStore
from office_agent.skill_localize import (
    apply_zh_frontmatter,
    has_cjk,
    needs_zh_display,
    try_localize_installed_skill,
)
from office_agent.skills import SkillMeta, SkillRegistry, parse_skill_md
from fastapi.testclient import TestClient


def _completion(*, content: str | None = None):
    message = SimpleNamespace(content=content, tool_calls=None)
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class RecordingGateway:
    def __init__(self, content: str | None = None, *, error: Exception | None = None):
        self.content = content
        self.error = error
        self.calls = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None):
        self.calls += 1
        if self.error:
            raise self.error
        return _completion(content=self.content)


def test_needs_zh_display_false_when_chinese_name():
    meta = SkillMeta(
        id="government-document-format",
        name="government-document-format",
        description="公文排版",
        display_name="公文格式排版",
    )
    assert needs_zh_display(meta) is False


def test_needs_zh_display_true_when_english_only():
    meta = SkillMeta(
        id="demo-skill",
        name="demo-skill",
        description="formats documents",
        display_name="",
    )
    assert needs_zh_display(meta) is True
    assert has_cjk(meta.description) is False


def test_apply_zh_frontmatter_preserves_body(tmp_path: Path):
    md = tmp_path / "SKILL.md"
    md.write_text(
        "---\nname: demo-skill\ndescription: formats docs\ntier: light\n---\n\n# Keep Body\n",
        encoding="utf-8",
    )
    apply_zh_frontmatter(md, display_name="演示技能", description="格式化文档")
    text = md.read_text(encoding="utf-8")
    assert "display_name: 演示技能" in text
    assert "description: 格式化文档" in text
    assert "# Keep Body" in text
    meta = parse_skill_md(text, tmp_path)
    assert meta.display_name == "演示技能"
    assert meta.description == "格式化文档"
    assert "Keep Body" in meta.body


def test_try_localize_writes_display_name(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: formats documents\ntier: light\n---\n\n# Body\n",
        encoding="utf-8",
    )
    meta = parse_skill_md((skill / "SKILL.md").read_text(encoding="utf-8"), skill)
    gw = RecordingGateway(
        content='{"display_name":"演示技能","description":"格式化文档"}'
    )
    updated = try_localize_installed_skill(meta, lambda _cfg: gw, AppConfig(
        api_base="http://127.0.0.1:8000/v1",
        api_key="k",
        model="m",
        allowed_hosts=["127.0.0.1"],
    ))
    assert gw.calls == 1
    assert updated.display_name == "演示技能"
    assert updated.description == "格式化文档"
    disk = (skill / "SKILL.md").read_text(encoding="utf-8")
    assert "display_name: 演示技能" in disk
    assert "# Body" in disk


def test_try_localize_soft_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "demo-skill"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: formats documents\ntier: light\n---\n\n# Body\n",
        encoding="utf-8",
    )
    meta = parse_skill_md((skill / "SKILL.md").read_text(encoding="utf-8"), skill)
    gw = RecordingGateway(error=RuntimeError("network down"))
    updated = try_localize_installed_skill(meta, lambda _cfg: gw, AppConfig(
        api_base="http://127.0.0.1:8000/v1",
        api_key="k",
        model="m",
        allowed_hosts=["127.0.0.1"],
    ))
    assert updated.display_name == ""
    assert updated.description == "formats documents"


def test_install_localizes_via_api(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    gw = RecordingGateway(
        content='{"display_name":"我的技能","description":"安装测试说明"}'
    )
    state = ProcessState(
        config=AppConfig(
            api_base="http://127.0.0.1:8000/v1",
            api_key="test-key",
            model="deepseek-v4-flash",
            allowed_hosts=["127.0.0.1", "localhost"],
        ),
        registry=SkillRegistry(),
        sessions=SessionStore(),
        gateway_factory=lambda _cfg: gw,
    )
    client = TestClient(create_app(state))

    src = tmp_path / "pkg" / "my-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: install test\ntier: light\n---\n\n# y\n",
        encoding="utf-8",
    )
    r = client.post("/skills/install", json={"path": str(src), "enabled": True})
    assert r.status_code == 200
    skill = r.json()["skill"]
    assert skill["display_name"] == "我的技能"
    assert skill["description"] == "安装测试说明"
    assert gw.calls == 1
    installed = tmp_path / "skills" / "my-skill" / "SKILL.md"
    assert "display_name: 我的技能" in installed.read_text(encoding="utf-8")


def test_install_succeeds_when_localize_fails(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    gw = RecordingGateway(error=RuntimeError("boom"))
    state = ProcessState(
        config=AppConfig(
            api_base="http://127.0.0.1:8000/v1",
            api_key="test-key",
            model="deepseek-v4-flash",
            allowed_hosts=["127.0.0.1", "localhost"],
        ),
        registry=SkillRegistry(),
        sessions=SessionStore(),
        gateway_factory=lambda _cfg: gw,
    )
    client = TestClient(create_app(state))

    src = tmp_path / "pkg" / "my-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: my-skill\ndescription: install test\ntier: light\n---\n\n# y\n",
        encoding="utf-8",
    )
    r = client.post("/skills/install", json={"path": str(src), "enabled": True})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert r.json()["skill"]["id"] == "my-skill"
    # Falls back to English name for display
    assert r.json()["skill"]["display_name"] == "my-skill"
