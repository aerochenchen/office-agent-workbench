#!/usr/bin/env python3
"""End-to-end self test for skill-builder (development / CI, not part of the Agent flow).

Usage:
    python smoke_pipeline.py

在临时的 OFFICE_AGENT_DATA 下走一遍：造草稿 → validate 拒收坏包 → validate 通过好包
→ install → 读回 → export --to-draft → export --zip。全绿退出码 0。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent

GOOD_SKILL_MD = """---
name: smoke-demo
display_name: 冒烟示例
description: 冒烟自测用的示例技能。
version: 1.0.0
tier: light
permissions:
  - workspace_read
  - run_python
trigger_phrases:
  - 冒烟示例
---

# 冒烟示例

用于验证 skill-builder 流水线本身。

## 何时用 / 何时不用

- 用：开发期自测
- 不用：真实办公任务

## 步数预算

| 阶段 | 约计步数 |
|------|----------|
| 全部 | 1 |

## 交付物

无，仅自测。

## 变更记录

- 1.0.0 — 首版
"""

BAD_SKILL_MD = """---
name: wrong-name
display_name: 坏示例
description: 目录名与 name 不一致，且引用了不存在的脚本 scripts/missing.py。
version: bad-version
tier: unknown
---

# 坏示例

正文还留着 {{占位符}}，见 scripts/missing.py。
"""


def _run(script: str, args: list[str], cwd: Path, env: dict[str, str]) -> tuple[int, dict]:
    proc = subprocess.run(
        [sys.executable, str(SCRIPTS / script), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
        timeout=120,
    )
    payload: dict = {}
    if proc.stdout.strip():
        try:
            payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            payload = {"_stdout": proc.stdout, "_stderr": proc.stderr}
    return proc.returncode, payload


def main() -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory(prefix="skill-builder-smoke-") as tmp:
        root = Path(tmp)
        data = root / "app-data"
        (data / "skills").mkdir(parents=True)
        ws = root / "ws"
        draft_root = ws / ".office-agent" / "work" / "skill-draft"

        good = draft_root / "smoke-demo"
        good.mkdir(parents=True)
        (good / "SKILL.md").write_text(GOOD_SKILL_MD, encoding="utf-8")

        bad = draft_root / "bad-demo"
        bad.mkdir(parents=True)
        (bad / "SKILL.md").write_text(BAD_SKILL_MD, encoding="utf-8")

        env = {**os.environ, "OFFICE_AGENT_DATA": str(data)}

        code, report = _run("validate.py", [str(bad)], ws, env)
        if code == 0:
            failures.append("validate 应当拒收坏包，却返回 0")
        joined = " ".join(report.get("errors", []))
        for expect in ("不一致", "semver", "tier", "占位符", "不存在的文件"):
            if expect not in joined:
                failures.append(f"validate 漏报坏包问题：{expect}（实际：{joined}）")

        code, report = _run("validate.py", [str(good)], ws, env)
        if code != 0 or not report.get("ok"):
            failures.append(f"validate 误报好包：{report.get('errors')}")

        code, report = _run("install.py", [str(good)], ws, env)
        if code != 0 or not report.get("ok"):
            failures.append(f"install 失败：{report}")
        installed = data / "skills" / "smoke-demo" / "SKILL.md"
        if not installed.is_file():
            failures.append(f"安装后 {installed} 不存在")
        elif "冒烟示例" not in installed.read_text(encoding="utf-8"):
            failures.append("安装后的 SKILL.md 内容不对")
        state = data / "skills_state.json"
        if not state.is_file() or json.loads(state.read_text(encoding="utf-8"))["enabled"].get(
            "smoke-demo"
        ) is not True:
            failures.append("skills_state.json 未把新技能标记为启用")

        # Reinstall must back up the previous copy outside skills/.
        code, report = _run("install.py", [str(good)], ws, env)
        backup = (report.get("replaced") or {}).get("backup")
        if code != 0 or not backup or not Path(backup).is_dir():
            failures.append(f"重复安装未产生备份：{report.get('replaced')}")
        elif Path(backup).is_relative_to(data / "skills"):
            failures.append("备份落在 skills/ 内，会被 SkillRegistry 误当技能扫到")

        code, report = _run("install.py", [str(bad)], ws, env)
        if code == 0 or report.get("ok"):
            failures.append("install 应当拒装校验失败的包")
        if (data / "skills" / "bad-demo").exists():
            failures.append("拒装后仍写入了技能目录")

        code, report = _run("export.py", ["smoke-demo", "--to-draft"], ws, env)
        if code != 0 or not (ws / report.get("draft_dir", "nope") / "SKILL.md").is_file():
            failures.append(f"export --to-draft 失败：{report}")

        code, report = _run("export.py", ["smoke-demo", "--zip"], ws, env)
        zip_rel = report.get("zip", "")
        zip_path = ws / zip_rel
        if code != 0 or not zip_path.is_file():
            failures.append(f"export --zip 失败：{report}")
        else:
            if "冒烟示例-smoke-demo" not in zip_path.name:
                failures.append(f"zip 命名不符约定：{zip_path.name}")
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
            if "smoke-demo/SKILL.md" not in names:
                failures.append(f"zip 内未按 <id>/SKILL.md 组织：{names}")

    summary = {"ok": not failures, "failures": failures}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if failures:
        print(f"ERROR: {len(failures)} 项冒烟检查失败", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
