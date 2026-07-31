from pathlib import Path

from fastapi.testclient import TestClient

from office_agent.app import create_app
from office_agent.bundled_seed import seed_bundled_assets


def test_bundled_assets_seeded_on_app_startup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    with TestClient(create_app()) as client:
        skills = client.get("/skills").json()["skills"]
    ids = {s["id"] for s in skills}
    assert "government-document-format" in ids
    assert "multidoc-digest" in ids
    assert "office-visual-design" in ids
    gongwen = next(s for s in skills if s["id"] == "government-document-format")
    assert gongwen["name"] == "公文格式排版"
    assert gongwen.get("display_name") == "公文格式排版"
    digest = next(s for s in skills if s["id"] == "multidoc-digest")
    assert digest.get("display_name") == "批量文档整理"
    visual = next(s for s in skills if s["id"] == "office-visual-design")
    assert visual.get("display_name") == "办公视觉设计"
    assert (tmp_path / "shared-scripts" / "format_gongwen.py").is_file()
    assert (tmp_path / "skills" / "government-document-format" / "SKILL.md").is_file()
    assert (tmp_path / "skills" / "multidoc-digest" / "scripts" / "ingest.py").is_file()
    assert (tmp_path / "skills" / "office-visual-design" / "palettes" / "zhengwu-navy.md").is_file()


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
