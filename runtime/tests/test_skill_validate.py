from pathlib import Path

from office_agent.skill_validate import validate_skill_dir, validate_skill_text


def _write_skill(root: Path, body: str = "# Demo\n", **fm: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for key, value in fm.items():
        if key == "permissions":
            lines.append("permissions:")
            for p in value.split(","):
                lines.append(f"  - {p.strip()}")
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    lines.append("")
    lines.append(body)
    (root / "SKILL.md").write_text("\n".join(lines), encoding="utf-8")
    return root


def test_validate_good_package(tmp_path: Path):
    skill = _write_skill(
        tmp_path / "good-skill",
        name="good-skill",
        description="短描述",
        version="1.0.0",
        tier="light",
        display_name="好技能",
        permissions="workspace_read",
        body="# Demo\n\n## 何时\n用。\n\n## 步数预算\n3。\n",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is True
    assert result["errors"] == []


def test_validate_missing_required_fields(tmp_path: Path):
    skill = _write_skill(
        tmp_path / "bad-skill",
        name="bad-skill",
        description="有描述",
        tier="light",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is False
    assert any("version" in e for e in result["errors"])


def test_validate_bad_tier_and_permissions(tmp_path: Path):
    skill = _write_skill(
        tmp_path / "tier-skill",
        name="tier-skill",
        description="d",
        version="0.1.0",
        tier="mega",
        permissions="workspace_list,run_python",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is False
    assert any("tier=" in e for e in result["errors"])
    assert any("workspace_list" in e for e in result["errors"])


def test_validate_unsafe_name(tmp_path: Path):
    skill = tmp_path / "weird"
    skill.mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: ../escape\ndescription: d\nversion: 0.0.1\ntier: light\n---\n\n#\n",
        encoding="utf-8",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is False
    assert any("unsafe" in e for e in result["errors"])


def test_validate_long_description_is_warning(tmp_path: Path):
    long_desc = "x" * 61
    skill = _write_skill(
        tmp_path / "long-desc",
        name="long-desc",
        description=long_desc,
        version="0.0.1",
        tier="light",
        display_name="长描述",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is True
    assert any("description" in w for w in result["warnings"])


def test_validate_missing_display_name_warning(tmp_path: Path):
    skill = _write_skill(
        tmp_path / "no-display",
        name="no-display",
        description="d",
        version="0.0.1",
        tier="light",
    )
    result = validate_skill_dir(skill)
    assert result["ok"] is True
    assert any("display_name" in w for w in result["warnings"])


def test_validate_script_syntax_and_forbidden_import(tmp_path: Path):
    skill = _write_skill(
        tmp_path / "scripted",
        name="scripted",
        description="d",
        version="0.0.1",
        tier="light",
        display_name="脚本",
        permissions="run_python",
    )
    scripts = skill / "scripts"
    scripts.mkdir()
    (scripts / "bad.py").write_text("def (\n", encoding="utf-8")
    (scripts / "net.py").write_text("import requests\nprint(1)\n", encoding="utf-8")
    result = validate_skill_dir(skill)
    assert result["ok"] is False
    assert any("syntax error" in e for e in result["errors"])
    assert any("requests" in e for e in result["errors"])


def test_validate_missing_skill_md(tmp_path: Path):
    d = tmp_path / "empty"
    d.mkdir()
    result = validate_skill_dir(d)
    assert result["ok"] is False
    assert any("SKILL.md" in e for e in result["errors"])


def test_validate_skill_text_ok():
    text = (
        "---\nname: memo\ndescription: d\nversion: 0.1.0\ntier: light\n"
        "display_name: 备忘\n---\n\n#\n"
    )
    result = validate_skill_text(text, "memo")
    assert result["ok"] is True
