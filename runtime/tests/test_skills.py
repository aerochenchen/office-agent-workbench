from pathlib import Path
import zipfile
import pytest
from office_agent.skills import SkillRegistry, SkillError


def test_scan_parses_frontmatter(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "demo-light"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: demo-light\ndescription: 测试轻量技能\nversion: 0.0.1\ntier: light\n"
        "permissions:\n  - workspace_read\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    metas = SkillRegistry().scan()
    assert len(metas) == 1
    assert metas[0].name == "demo-light"
    assert metas[0].tier == "light"
    assert metas[0].permissions == ["workspace_read"]
    assert metas[0].ui_name == "demo-light"


def test_scan_prefers_display_name(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "government-document-format"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: government-document-format\ndisplay_name: 公文格式排版\n"
        "description: 公文排版\ntier: light\n---\n\n# Demo\n",
        encoding="utf-8",
    )
    meta = SkillRegistry().scan()[0]
    assert meta.name == "government-document-format"
    assert meta.display_name == "公文格式排版"
    assert meta.ui_name == "公文格式排版"
    payload = SkillRegistry().meta_payload(meta)
    assert payload["name"] == "公文格式排版"
    assert payload["display_name"] == "公文格式排版"


def test_install_zip_heavy_tier(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "heavy-demo"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: heavy-demo\ndescription: 重量\nversion: 0.1.0\ntier: heavy\nmin_ram_gb: 8\n"
        "permissions:\n  - run_python\n---\n\n# H\n",
        encoding="utf-8",
    )
    z = tmp_path / "heavy.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src / "SKILL.md", arcname="heavy-demo/SKILL.md")
    meta = SkillRegistry().install_zip(z)
    assert meta.tier == "heavy"
    assert meta.min_ram_gb == 8
    assert (tmp_path / "skills" / "heavy-demo" / "SKILL.md").is_file()


def test_install_path_zip_and_disable(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "z-demo"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: z-demo\ndescription: d\nversion: 0.1.0\ntier: light\n"
        "permissions:\n  - workspace_write\n---\n\n#\n",
        encoding="utf-8",
    )
    z = tmp_path / "z.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.write(src / "SKILL.md", arcname="z-demo/SKILL.md")
    meta = SkillRegistry().install_path(z, enabled=False)
    assert meta.enabled is False
    scanned = SkillRegistry().scan()
    assert scanned[0].enabled is False


def test_install_md_lightweight(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    md = tmp_path / "公文助手.md"
    md.write_text(
        "---\nname: memo-helper\ndescription: 仅说明\nversion: 0.1.0\ntier: light\n---\n\n# 用法\n",
        encoding="utf-8",
    )
    meta = SkillRegistry().install_path(md)
    assert meta.id == "memo-helper"
    assert (tmp_path / "skills" / "memo-helper" / "SKILL.md").is_file()


def test_inspect_path_dir(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "peek"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: peek\ndescription: 预览\ntier: light\npermissions:\n  - workspace_list\n---\n\n#\n",
        encoding="utf-8",
    )
    meta = SkillRegistry().inspect_path(src)
    assert meta.name == "peek"
    assert meta.permissions == ["workspace_list"]
    assert not (tmp_path / "skills").exists() or not any((tmp_path / "skills").iterdir())


def test_reject_without_skill_md(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "readme.txt").write_text("x", encoding="utf-8")
    with pytest.raises(SkillError):
        SkillRegistry().install_dir(bad)


def test_install_zip_rejects_path_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    z = tmp_path / "evil.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("../escape/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
        zf.writestr("evil/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
    with pytest.raises(SkillError, match="unsafe zip"):
        SkillRegistry().install_zip(z)
    assert not (tmp_path / "escape").exists()


def test_inspect_zip_rejects_path_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    z = tmp_path / "evil2.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("/tmp/evil-skill/SKILL.md", "---\nname: evil\ndescription: x\ntier: light\n---\n\n#\n")
    with pytest.raises(SkillError, match="unsafe zip"):
        SkillRegistry().inspect_path(z)


def test_uninstall_removes_skill(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    skill = tmp_path / "skills" / "to-remove"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text(
        "---\nname: to-remove\ndescription: d\ntier: light\n---\n\n#\n",
        encoding="utf-8",
    )
    reg = SkillRegistry()
    reg.set_enabled("to-remove", False)
    assert len(reg.scan()) == 1
    reg.uninstall("to-remove")
    assert len(reg.scan()) == 0
    assert not skill.exists()
    assert "to-remove" not in reg._state.get("enabled", {})


def test_uninstall_unknown_raises(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    with pytest.raises(SkillError, match="not found"):
        SkillRegistry().uninstall("missing-skill")


def test_uninstall_rejects_path_escape(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    outside = tmp_path / "outside-skill"
    outside.mkdir()
    (outside / "SKILL.md").write_text(
        "---\nname: outside\ndescription: d\ntier: light\n---\n\n#\n",
        encoding="utf-8",
    )
    reg = SkillRegistry()
    for bad_id in ("../outside-skill", "..\\outside-skill", "a/b", "a\\b", ".."):
        with pytest.raises(SkillError, match="invalid skill_id"):
            reg.uninstall(bad_id)
    assert outside.is_dir()
    assert (outside / "SKILL.md").is_file()


def test_install_rejects_invalid_package(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "bad-pkg"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: bad-pkg\ndescription: d\ntier: light\n---\n\n# missing version\n",
        encoding="utf-8",
    )
    with pytest.raises(SkillError) as ei:
        SkillRegistry().install_dir(src)
    assert ei.value.validation is not None
    assert ei.value.validation["ok"] is False
    assert any("version" in e for e in ei.value.validation["errors"])
    assert not (tmp_path / "skills" / "bad-pkg").exists()


def test_install_rejects_forbidden_script_import(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "net-skill"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: net-skill\ndescription: d\nversion: 0.1.0\ntier: light\n"
        "permissions:\n  - run_python\n---\n\n#\n",
        encoding="utf-8",
    )
    scripts = src / "scripts"
    scripts.mkdir()
    (scripts / "fetch.py").write_text("import httpx\n", encoding="utf-8")
    with pytest.raises(SkillError) as ei:
        SkillRegistry().install_dir(src)
    assert any("httpx" in e for e in ei.value.validation["errors"])
    assert not (tmp_path / "skills" / "net-skill").exists()


def test_inspect_returns_validation(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path))
    src = tmp_path / "pkg" / "peek-ok"
    src.mkdir(parents=True)
    (src / "SKILL.md").write_text(
        "---\nname: peek-ok\ndescription: 预览\nversion: 0.1.0\ntier: light\n"
        "display_name: 预览技能\npermissions:\n  - workspace_read\n---\n\n#\n",
        encoding="utf-8",
    )
    meta, validation = SkillRegistry().inspect_with_validation(src)
    assert meta.name == "peek-ok"
    assert validation["ok"] is True
    assert validation["errors"] == []
