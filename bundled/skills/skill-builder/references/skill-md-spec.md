# SKILL.md 规范

## 目录布局

```
<skill-id>/
  SKILL.md          # 必需，唯一必需项
  scripts/*.py      # 可选：确定性重活，由 run_skill_script 调用
  references/*.md   # 可选：细则手册，由 read_skill 按需读取
  templates/*       # 可选：产出模板
  fixtures/         # 可选：自测样例（会被 --zip 排除）
```

## 极易踩的三件事

1. **技能 id 来自目录名，不是 frontmatter 的 `name`**。`parse_skill_md()` 里 `id=skill_dir.name`。所以目录名必须是纯 ASCII slug，且 `name` 要与目录名写成同一个值，否则 UI、`run_skill_script`、`read_skill` 用的 id 与你以为的不一致。
2. **`description` 每一轮对话都会注入 system prompt**，正文却只在 `read_skill` 时才加载。所以 description 只写"何时启用 + 产出什么"，控制在 60 字内；所有步骤细节放正文。
3. **正文不会自动生效**。Agent 看到目录后必须先 `read_skill` 才拿到正文。所以正文第一段就要说清场景与边界，让 Agent 读完立刻知道该不该继续。

## Frontmatter 字段

Runtime 真正解析这些（见 `runtime/src/office_agent/skills.py`）：

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 与目录名一致的 ASCII slug |
| `display_name` | 是 | 中文名，UI 与技能面板显示 |
| `description` | 是 | ≤60 字，"何时启用 + 产出什么" |
| `version` | 是 | semver，迭代必升 |
| `tier` | 是 | `light` 或 `heavy` |
| `min_ram_gb` | heavy 必填 | 内存建议，UI 会提示 |
| `permissions` | 建议 | 取值 `workspace_read` / `workspace_write` / `run_python` |
| `shared_scripts` | 可选 | 依赖的共享脚本逻辑名，如 `format_gongwen` |

以下字段写了不报错，但**当前 Runtime 不解析**，仅作文档与未来路由用途：`category`、`trigger_phrases`、`target_file_type`、`required_tools`。写 `trigger_phrases` 仍有价值——它是你回头判断"这个技能到底该被什么话触发"的备忘。

## 命名规范

- 目录名 / `name`：`^[a-z0-9][a-z0-9-]{1,39}$`，用连字符，如 `weekly-report-digest`
- `display_name`：中文，4～10 字，让用户在技能面板一眼看懂
- zip 分享包：`<display_name>-<id>.zip`，与 `packaging/skills/` 现有惯例一致

## 正文该写什么

固化的是**判断力和纪律**，不是能被脚本替代的操作。每一步都标注执行者（脚本 / Agent）和预计步数，因为整轮工具步数有上限，超了任务会半途中断。

必备章节：何时用/何时不用、输入与产出（目录约定）、N 步纪律、步数预算、硬规则、变更记录。

正文控制在 8000 字符内。超了就把细则拆到 `references/`，让 Agent 需要时再 `read_skill` 读——这正是渐进式披露的用法。
