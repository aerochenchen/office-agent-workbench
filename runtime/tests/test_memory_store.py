from __future__ import annotations

from pathlib import Path

import pytest

from office_agent.memory_store import MAX_HABITS, MAX_RECENT, MemoryStore


@pytest.fixture
def store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> MemoryStore:
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    return MemoryStore(tmp_path)


def test_apply_reflection_replaces_same_topic(store: MemoryStore):
    store.apply_reflection(
        [{"topic": "标题", "text": "用短标题"}],
        ["刚做完校对"],
    )
    store.apply_reflection(
        [{"topic": "标题", "text": "标题固定八字"}],
        [],
    )
    habits = store.list_habits()
    assert len(habits) == 1
    assert habits[0]["text"] == "标题固定八字"
    assert store.list_recent()[0]["text"] == "刚做完校对"


def test_recent_capped(store: MemoryStore):
    for i in range(MAX_RECENT + 3):
        store.apply_reflection([], [f"近况{i}"])
    recent = store.list_recent()
    assert len(recent) == MAX_RECENT
    assert recent[0]["text"] == f"近况{MAX_RECENT + 2}"


def test_habits_capped(store: MemoryStore):
    store.apply_reflection(
        [{"topic": f"主题{i}", "text": f"内容{i}"} for i in range(MAX_HABITS + 4)],
        [],
    )
    assert len(store.list_habits()) == MAX_HABITS


def test_undo_restores_previous(store: MemoryStore):
    store.apply_reflection([{"topic": "a", "text": "1"}], ["r1"])
    store.apply_reflection([{"topic": "a", "text": "2"}], ["r2"])
    snap = store.undo()
    assert snap["habits"][0]["text"] == "1"
    assert snap["recent"][0]["text"] == "r1"
    assert snap["can_undo"] is True


def test_prompt_digest_includes_habits(store: MemoryStore):
    assert store.prompt_digest() == ""
    store.apply_reflection([{"topic": "语气", "text": "少确认"}], ["做完排版"])
    digest = store.prompt_digest()
    assert "记忆：" in digest
    assert "- 少确认" in digest
    assert "语气：" not in digest
    assert "做完排版" not in digest
    assert "近况" not in digest
    assert "习惯" not in digest


def test_replace_all_and_trace(store: MemoryStore):
    store.replace_all(
        [{"topic": "交付", "text": "都放工作成果"}],
        [{"text": "上周做过对照"}],
    )
    assert store.list_habits()[0]["topic"] == "交付"
    assert store.record_trace("sig-a") == 1
    assert store.record_trace("sig-a") == 2
    assert store.get_trace_count("sig-a") == 2
    store.set_crystallized(
        "sig-a", skill_id="learned-flow-x", display_name="习惯流程", version="1.0.0"
    )
    info = store.get_crystallized("sig-a")
    assert info is not None
    assert info["skill_id"] == "learned-flow-x"
