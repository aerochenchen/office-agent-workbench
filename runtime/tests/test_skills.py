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
        "---\nname: z-demo\ndescription: d\ntier: light\npermissions:\n  - workspace_write\n---\n\n#\n",
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
        "---\nname: memo-helper\ndescription: 仅说明\ntier: light\n---\n\n# 用法\n",
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
