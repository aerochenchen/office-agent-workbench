from pathlib import Path

from fastapi.testclient import TestClient

from office_agent.app import create_app


def test_bundled_assets_seeded_on_app_startup(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    repo_bundled = Path(__file__).resolve().parents[2] / "bundled"
    monkeypatch.setenv("OFFICE_AGENT_BUNDLED", str(repo_bundled.resolve()))

    with TestClient(create_app()) as client:
        skills = client.get("/skills").json()["skills"]
    ids = {s["id"] for s in skills}
    assert "government-document-format" in ids
    gongwen = next(s for s in skills if s["id"] == "government-document-format")
    assert gongwen["name"] == "公文格式排版"
    assert gongwen.get("display_name") == "公文格式排版"
    assert (tmp_path / "shared-scripts" / "format_gongwen.py").is_file()
    assert (tmp_path / "skills" / "government-document-format" / "SKILL.md").is_file()
