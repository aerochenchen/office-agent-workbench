"""End-to-end: seed the bundled skill-builder, then author a skill through the tools.

Covers the whole loop the Agent actually walks: read_skill loads the workflow,
the draft is written into the workspace, skill scripts validate and install it,
and the registry picks the new skill up without a restart.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from office_agent.bundled_seed import seed_bundled_assets
from office_agent.skills import SkillRegistry
from office_agent.tools import ToolExecutor
from office_agent.workspace import Workspace

REPO_BUNDLED = Path(__file__).resolve().parents[2] / "bundled"
DRAFT_DIR = ".office-agent/work/skill-draft/e2e-demo"

DRAFT_SKILL_MD = """---
name: e2e-demo
display_name: 端到端示例
description: 端到端测试用的示例技能。
version: 1.0.0
tier: light
permissions:
  - workspace_read
trigger_phrases:
  - 端到端示例
---

# 端到端示例

验证 skill-builder 流水线可用。

## 何时用 / 何时不用

- 用：自动化测试
- 不用：真实任务

## 步数预算

| 阶段 | 约计步数 |
|------|----------|
| 全部 | 1 |

## 交付物

无。

## 变更记录

- 1.0.0 — 首版
"""


@pytest.fixture
def seeded(tmp_path: Path, monkeypatch) -> tuple[ToolExecutor, SkillRegistry]:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path / "app-data"))
    seed_bundled_assets(REPO_BUNDLED)
    ws = tmp_path / "ws"
    ws.mkdir()
    registry = SkillRegistry()
    return ToolExecutor(Workspace(ws), registry, permission_mode="trust"), registry


def test_skill_builder_is_bundled_and_enabled(seeded):
    _, registry = seeded
    catalog = {s["id"]: s for s in registry.enabled_catalog()}
    assert "skill-builder" in catalog
    assert catalog["skill-builder"]["name"] == "创建技能"


def test_read_skill_loads_workflow_and_templates(seeded):
    tools, _ = seeded
    body = tools.execute("read_skill", {"skill_id": "skill-builder"})
    assert body["ok"] is True
    assert "七步纪律" in body["content"]
    assert "references/skill-md-spec.md" in body["files"]
    assert "templates/SKILL.md.tmpl" in body["files"]

    template = tools.execute(
        "read_skill", {"skill_id": "skill-builder", "file": "templates/SKILL.md.tmpl"}
    )
    assert template["ok"] is True
    assert "display_name" in template["content"]


def test_author_validate_install_and_load_new_skill(seeded):
    tools, registry = seeded

    written = tools.execute(
        "workspace_write", {"path": f"{DRAFT_DIR}/SKILL.md", "content": DRAFT_SKILL_MD}
    )
    assert written["ok"] is True
    assert written["path"] == f"{DRAFT_DIR}/SKILL.md"

    checked = tools.execute(
        "run_skill_script",
        {"skill_id": "skill-builder", "script": "validate.py", "args": [DRAFT_DIR]},
    )
    assert checked["ok"] is True, checked["stderr"]
    report = json.loads(checked["stdout"])
    assert report["ok"] is True
    assert report["errors"] == []

    installed = tools.execute(
        "run_skill_script",
        {"skill_id": "skill-builder", "script": "install.py", "args": [DRAFT_DIR]},
    )
    assert installed["ok"] is True, installed["stderr"]
    outcome = json.loads(installed["stdout"])
    assert outcome["skill_id"] == "e2e-demo"
    assert outcome["enabled"] is True

    # Visible to the running Runtime with no restart.
    catalog = {s["id"]: s for s in SkillRegistry().enabled_catalog()}
    assert catalog["e2e-demo"]["name"] == "端到端示例"

    loaded = tools.execute("read_skill", {"skill_id": "e2e-demo"})
    assert loaded["ok"] is True
    assert "端到端示例" in loaded["content"]


def test_validate_rejects_broken_draft(seeded):
    tools, _ = seeded
    tools.execute(
        "workspace_write",
        {
            "path": ".office-agent/work/skill-draft/Bad_Draft/SKILL.md",
            "content": "---\nname: other\ndescription: x\nversion: 9\ntier: light\n---\n\n# x\n",
        },
    )
    checked = tools.execute(
        "run_skill_script",
        {
            "skill_id": "skill-builder",
            "script": "validate.py",
            "args": [".office-agent/work/skill-draft/Bad_Draft"],
        },
    )
    assert checked["ok"] is False
    report = json.loads(checked["stdout"])
    assert report["ok"] is False
    joined = " ".join(report["errors"])
    assert "目录名" in joined
    assert "不一致" in joined
    assert "display_name" in joined


def test_export_zip_lands_in_output(seeded):
    tools, _ = seeded
    tools.execute("workspace_write", {"path": f"{DRAFT_DIR}/SKILL.md", "content": DRAFT_SKILL_MD})
    tools.execute(
        "run_skill_script",
        {"skill_id": "skill-builder", "script": "install.py", "args": [DRAFT_DIR]},
    )
    exported = tools.execute(
        "run_skill_script",
        {"skill_id": "skill-builder", "script": "export.py", "args": ["e2e-demo", "--zip"]},
    )
    assert exported["ok"] is True, exported["stderr"]
    payload = json.loads(exported["stdout"])
    assert payload["zip"] == "output/端到端示例-e2e-demo.zip"
    assert (tools.workspace.root / payload["zip"]).is_file()
