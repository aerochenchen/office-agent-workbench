"""Per-user office memory: habits, recent notes, one-shot undo, flow traces."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from office_agent.paths import app_data_dir, chmod_private_dir, write_private_text

MAX_HABITS = 12
MAX_RECENT = 8
PROMPT_DIGEST_CHARS = 1000
TOPIC_MAX = 40
TEXT_MAX = 200
RECENT_MAX = 120

_SAFE_TOPIC_RE = re.compile(r"\s+")


def _now() -> float:
    return time.time()


def _clean_topic(raw: str) -> str:
    text = _SAFE_TOPIC_RE.sub(" ", (raw or "").strip())
    if len(text) > TOPIC_MAX:
        text = text[:TOPIC_MAX]
    return text


def _clean_text(raw: str, *, limit: int) -> str:
    text = _SAFE_TOPIC_RE.sub(" ", (raw or "").strip())
    if len(text) > limit:
        text = text[:limit]
    return text


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


class MemoryStore:
    def __init__(self, root: Path | None = None) -> None:
        base = root if root is not None else app_data_dir()
        self.root = (base / "memory").resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        chmod_private_dir(self.root)
        self.habits_path = self.root / "habits.json"
        self.recent_path = self.root / "recent.json"
        self.undo_path = self.root / "undo.json"
        self.traces_path = self.root / "traces.json"
        self.skills_path = self.root / "skills.json"
        self.backup_root = self.root / "skill-backup"

    def snapshot(self) -> dict[str, Any]:
        return {
            "habits": self.list_habits(),
            "recent": self.list_recent(),
            "can_undo": self.can_undo(),
            "crystallized": self.list_crystallized(),
        }

    def list_habits(self) -> list[dict[str, Any]]:
        raw = _read_json(self.habits_path, [])
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            topic = _clean_topic(str(item.get("topic") or ""))
            text = _clean_text(str(item.get("text") or ""), limit=TEXT_MAX)
            if not topic or not text:
                continue
            out.append(
                {
                    "topic": topic,
                    "text": text,
                    "updated_at": float(item.get("updated_at") or 0),
                }
            )
        return out[:MAX_HABITS]

    def list_recent(self) -> list[dict[str, Any]]:
        raw = _read_json(self.recent_path, [])
        if not isinstance(raw, list):
            return []
        out: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            text = _clean_text(str(item.get("text") or ""), limit=RECENT_MAX)
            if not text:
                continue
            out.append({"text": text, "updated_at": float(item.get("updated_at") or 0)})
        return out[:MAX_RECENT]

    def list_crystallized(self) -> list[dict[str, Any]]:
        raw = _read_json(self.skills_path, {})
        if not isinstance(raw, dict):
            return []
        out: list[dict[str, Any]] = []
        for sig, info in raw.items():
            if not isinstance(info, dict):
                continue
            skill_id = str(info.get("skill_id") or "").strip()
            display_name = str(info.get("display_name") or skill_id).strip()
            if not skill_id:
                continue
            out.append(
                {
                    "signature": str(sig),
                    "skill_id": skill_id,
                    "display_name": display_name,
                    "version": str(info.get("version") or "1.0.0"),
                    "updated_at": float(info.get("updated_at") or 0),
                }
            )
        out.sort(key=lambda x: x["updated_at"], reverse=True)
        return out

    def can_undo(self) -> bool:
        data = _read_json(self.undo_path, None)
        return isinstance(data, dict) and "habits" in data and "recent" in data

    def prompt_digest(self) -> str:
        habits = self.list_habits()
        if not habits:
            return ""
        lines: list[str] = ["记忆："]
        for item in habits:
            lines.append(f"- {item['text']}")
        text = "\n".join(lines)
        if len(text) > PROMPT_DIGEST_CHARS:
            text = text[: PROMPT_DIGEST_CHARS - 1] + "…"
        return text

    def _write_lists(self, habits: list[dict[str, Any]], recent: list[dict[str, Any]]) -> None:
        write_private_text(
            self.habits_path,
            json.dumps(habits[:MAX_HABITS], ensure_ascii=False, indent=2) + "\n",
        )
        write_private_text(
            self.recent_path,
            json.dumps(recent[:MAX_RECENT], ensure_ascii=False, indent=2) + "\n",
        )

    def _save_undo(self) -> None:
        payload = {
            "habits": self.list_habits(),
            "recent": self.list_recent(),
            "saved_at": _now(),
        }
        write_private_text(
            self.undo_path,
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        )

    def replace_all(
        self,
        habits: list[dict[str, Any]],
        recent: list[dict[str, Any]],
        *,
        save_undo: bool = True,
    ) -> dict[str, Any]:
        cleaned_habits: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in habits:
            if not isinstance(item, dict):
                continue
            topic = _clean_topic(str(item.get("topic") or ""))
            text = _clean_text(str(item.get("text") or ""), limit=TEXT_MAX)
            if not topic or not text or topic in seen:
                continue
            seen.add(topic)
            cleaned_habits.append(
                {
                    "topic": topic,
                    "text": text,
                    "updated_at": float(item.get("updated_at") or _now()),
                }
            )
            if len(cleaned_habits) >= MAX_HABITS:
                break

        cleaned_recent: list[dict[str, Any]] = []
        for item in recent:
            if not isinstance(item, dict):
                continue
            text = _clean_text(str(item.get("text") or ""), limit=RECENT_MAX)
            if not text:
                continue
            cleaned_recent.append(
                {"text": text, "updated_at": float(item.get("updated_at") or _now())}
            )
            if len(cleaned_recent) >= MAX_RECENT:
                break

        if save_undo:
            self._save_undo()
        self._write_lists(cleaned_habits, cleaned_recent)
        return self.snapshot()

    def apply_reflection(
        self,
        habits: list[dict[str, str]],
        recent_texts: list[str],
    ) -> dict[str, Any]:
        """Merge reflection output: same topic replaces; recent prepends."""
        current = {h["topic"]: h for h in self.list_habits()}
        changed_topics: list[str] = []
        now = _now()
        for item in habits:
            topic = _clean_topic(str(item.get("topic") or ""))
            text = _clean_text(str(item.get("text") or ""), limit=TEXT_MAX)
            if not topic or not text:
                continue
            prev = current.get(topic)
            if prev and prev.get("text") == text:
                continue
            current[topic] = {"topic": topic, "text": text, "updated_at": now}
            changed_topics.append(topic)

        recent = self.list_recent()
        new_recent: list[dict[str, Any]] = []
        for raw in recent_texts:
            text = _clean_text(raw, limit=RECENT_MAX)
            if not text:
                continue
            if recent and recent[0].get("text") == text:
                continue
            new_recent.append({"text": text, "updated_at": now})
        merged_recent = (new_recent + recent)[:MAX_RECENT]

        # Keep most recently updated habits first; drop overflow.
        ordered = sorted(current.values(), key=lambda h: h.get("updated_at") or 0, reverse=True)
        ordered = ordered[:MAX_HABITS]

        if not changed_topics and not new_recent:
            return {
                "changed": False,
                "topics": [],
                "recent_line": "",
                "snapshot": self.snapshot(),
            }

        self._save_undo()
        self._write_lists(ordered, merged_recent)
        recent_line = new_recent[0]["text"] if new_recent else ""
        return {
            "changed": True,
            "topics": changed_topics,
            "recent_line": recent_line,
            "snapshot": self.snapshot(),
        }

    def undo(self) -> dict[str, Any]:
        data = _read_json(self.undo_path, None)
        if not isinstance(data, dict) or "habits" not in data or "recent" not in data:
            raise ValueError("没有可撤销的备忘")
        habits = data.get("habits") if isinstance(data.get("habits"), list) else []
        recent = data.get("recent") if isinstance(data.get("recent"), list) else []
        # Snapshot current before undo so one more undo returns to post-edit state.
        current = {"habits": self.list_habits(), "recent": self.list_recent(), "saved_at": _now()}
        self._write_lists(
            [h for h in habits if isinstance(h, dict)],
            [r for r in recent if isinstance(r, dict)],
        )
        write_private_text(
            self.undo_path,
            json.dumps(current, ensure_ascii=False, indent=2) + "\n",
        )
        return self.snapshot()

    def record_trace(self, signature: str) -> int:
        """Increment count for a flow signature; return new count."""
        sig = (signature or "").strip()
        if not sig:
            return 0
        raw = _read_json(self.traces_path, {})
        if not isinstance(raw, dict):
            raw = {}
        entry = raw.get(sig) if isinstance(raw.get(sig), dict) else {}
        count = int(entry.get("count") or 0) + 1
        raw[sig] = {"count": count, "updated_at": _now()}
        write_private_text(
            self.traces_path,
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        )
        return count

    def get_trace_count(self, signature: str) -> int:
        raw = _read_json(self.traces_path, {})
        if not isinstance(raw, dict):
            return 0
        entry = raw.get(signature)
        if not isinstance(entry, dict):
            return 0
        return int(entry.get("count") or 0)

    def get_crystallized(self, signature: str) -> dict[str, Any] | None:
        raw = _read_json(self.skills_path, {})
        if not isinstance(raw, dict):
            return None
        entry = raw.get(signature)
        return entry if isinstance(entry, dict) else None

    def set_crystallized(
        self,
        signature: str,
        *,
        skill_id: str,
        display_name: str,
        version: str,
    ) -> None:
        raw = _read_json(self.skills_path, {})
        if not isinstance(raw, dict):
            raw = {}
        raw[signature] = {
            "skill_id": skill_id,
            "display_name": display_name,
            "version": version,
            "updated_at": _now(),
        }
        write_private_text(
            self.skills_path,
            json.dumps(raw, ensure_ascii=False, indent=2) + "\n",
        )
