# 技能脚本约定

## 执行环境

`run_skill_script` 用 `subprocess` 起一个独立 Python 进程跑 `scripts/*.py`：

- **cwd 是工作区根目录**，不是技能目录。所有路径参数按相对工作区解析
- 超时 **600 秒**，每次调用计 **1 步**工具
- 返回 `{ok, exit_code, stdout, stderr}` 给 Agent
- 打包后（PyInstaller sidecar）经 `--run-script` 重入执行，行为与开发环境一致

要读技能自己目录下的文件（模板、词表），用 `Path(__file__).resolve().parent.parent`，不要用相对路径。

## CLI 形态

```python
#!/usr/bin/env python3
"""一句话说明 + Usage 示例"""
import argparse, json, sys

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(...)
    args = parser.parse_args(argv)
    ...
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
```

- **stdout 只打 JSON 摘要**。Agent 靠它判断结果，掺杂进度日志会干扰解析；要打日志就走 stderr
- 失败时 stderr 打 `ERROR: 原因`，返回非 0
- 批处理时单个文件失败不要整体中断，记进 `failed` 列表继续，最后在摘要里报告成功/失败份数

两类文件不受上述 CLI 约定约束，`validate.py` 也会跳过对它们的检查：

- **辅助模块**——没有 `if __name__ == "__main__"` 入口的，比如被其他脚本 import 的公共函数
- **`smoke_pipeline.py`**——本仓库约定的开发期自测脚本名，零参数运行，不由 Agent 调用

## 硬禁

- **不要执行 shell**：`os.system`、`subprocess(..., shell=True)` 一律禁止
- **不要联网**：`requests`、`urllib.request` 一律禁止。这是内网离线环境
- 不要 `import office_agent`。脚本是独立进程，Runtime 内部模块不保证可导入

需要应用数据目录（`~/.office-agent`）时自己复刻一遍逻辑，环境变量会被继承：

```python
import os
from pathlib import Path

def app_data_dir() -> Path:
    override = os.environ.get("OFFICE_AGENT_DATA")
    return Path(override) if override else Path.home() / ".office-agent"
```

## 可用依赖

标准库 + `python-docx`（Word）+ `openpyxl`（Excel）+ `pyyaml`。不要引入新的第三方包——离线环境装不上。

## 什么该写成脚本

写成脚本：遍历目录、抽取文本、统计汇总、格式检查、批量改名、模板填充——**输入相同则输出必定相同**的活。

留在正文当 SOP：需要理解语义、权衡取舍、判断口径的活。

判断标准很简单：如果这一步能用 if/else 描述清楚，就该是脚本；如果需要"看情况"，就该是正文。
