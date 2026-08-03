import threading
import time
from pathlib import Path

from fastapi.testclient import TestClient

from office_agent.app import create_app
from office_agent.bundled_seed import seed_bundled_assets


def test_health_available_before_slow_seed_finishes(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    release = threading.Event()
    real_seed = seed_bundled_assets

    def slow_seed(*args, **kwargs):
        release.wait(timeout=5)
        return real_seed(*args, **kwargs)

    monkeypatch.setattr("office_agent.app.seed_bundled_assets", slow_seed)

    with TestClient(create_app()) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        release.set()
        deadline = time.time() + 5
        while time.time() < deadline:
            skills = client.get("/skills").json()["skills"]
            if any(s["id"] == "government-document-format" for s in skills):
                break
            time.sleep(0.05)
        else:
            raise AssertionError("seed did not finish")


def test_bundled_assets_seeded_on_app_startup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    expected = {
        "government-document-format",
        "multidoc-digest",
        "office-visual-design",
        "doc-proofread",
        "doc-diff-review",
        "meeting-followup",
        "material-gap",
        "sheet-to-brief",
        "skill-builder",
    }
    skills: list = []
    with TestClient(create_app()) as client:
        deadline = time.time() + 5
        while time.time() < deadline:
            skills = client.get("/skills").json()["skills"]
            ids = {s["id"] for s in skills}
            if expected.issubset(ids):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(
                f"seed did not finish before deadline; got {sorted(ids)}"
            )
    ids = {s["id"] for s in skills}
    assert expected.issubset(ids)
    gongwen = next(s for s in skills if s["id"] == "government-document-format")
    assert gongwen["name"] == "公文格式排版"
    assert gongwen.get("display_name") == "公文格式排版"
    digest = next(s for s in skills if s["id"] == "multidoc-digest")
    assert digest.get("display_name") == "批量文档整理"
    visual = next(s for s in skills if s["id"] == "office-visual-design")
    assert visual.get("display_name") == "办公视觉设计"
    proof = next(s for s in skills if s["id"] == "doc-proofread")
    assert proof.get("display_name") == "通篇校对"
    diff_review = next(s for s in skills if s["id"] == "doc-diff-review")
    assert diff_review.get("display_name") == "文稿对照"
    meeting = next(s for s in skills if s["id"] == "meeting-followup")
    assert meeting.get("display_name") == "会议督办"
    gap = next(s for s in skills if s["id"] == "material-gap")
    assert gap.get("display_name") == "材料摸底"
    sheet = next(s for s in skills if s["id"] == "sheet-to-brief")
    assert sheet.get("display_name") == "表格成文"
    assert (tmp_path / "shared-scripts" / "format_gongwen.py").is_file()
    assert (tmp_path / "shared-scripts" / "docx_diff.py").is_file()
    assert (tmp_path / "skills" / "government-document-format" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "multidoc-digest" / "scripts" / "ingest.py").is_file()
    assert (tmp_path / "skills" / "office-visual-design" / "palettes" / "zhengwu-navy.md").is_file()
    assert (tmp_path / "skills" / "doc-proofread" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "doc-diff-review" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "meeting-followup" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "material-gap" / "scripts" / "inventory.py").is_file()
    assert (tmp_path / "skills" / "sheet-to-brief" / "SKILL.md").is_file()


def test_seed_does_not_clobber_user_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    skill_dir = tmp_path / "skills" / "government-document-format"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: government-document-format\ndescription: 用户自定义副本\ntier: light\n---\n\n# User\n",
        encoding="utf-8",
    )
    (skill_dir / "USER_MARKER.txt").write_text("keep me", encoding="utf-8")

    seed_bundled_assets(repo_bundled)

    assert (skill_dir / "USER_MARKER.txt").read_text(encoding="utf-8") == "keep me"
    assert "用户自定义副本" in (skill_dir / "SKILL.md").read_text(encoding="utf-8")
