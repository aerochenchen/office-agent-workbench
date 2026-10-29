# deck.json

路径相对当前文件夹。**新建只写语义字段**；left/top/pt/裸 hex 仅 `canvas`。

```json
{
  "title": "汇报标题",
  "subtitle": "单位 / 场合 / 日期",
  "palette": "zhengwu-navy",
  "style": ".office-agent/work/ppt-maker/style.json",
  "slides": [
    {"type": "title", "title": "汇报标题", "subtitle": "办公室 2026年10月", "notes": "开场致谢"},
    {"type": "toc", "title": "汇报提纲", "bullets": ["背景", "进展", "问题", "建议"]},
    {"type": "section", "title": "一、主要进展"},
    {"type": "bullets", "title": "工作进展", "bullets": ["完成摸底", "启动试点", "形成口径"]},
    {"type": "kpi", "title": "主要指标", "kpis": [
      {"label": "覆盖率", "value": "92%"},
      {"label": "办结件", "value": "18"}
    ]},
    {"type": "table", "title": "任务一览", "rows": [
      ["事项", "进度"],
      ["摸底", "完成"],
      ["试点", "进行中"]
    ]},
    {"type": "chart", "title": "季度对比", "chart": {
      "kind": "bar",
      "categories": ["一季度", "二季度"],
      "series": {"本部": [10, 12], "分部": [7, 9]}
    }},
    {"type": "closing", "title": "请示事项", "bullets": ["请予明确下一步责任单位"]}
  ]
}
```

`style` 可省略。有参考稿时先跑 `pptx_style.py` 写出该文件，不要手填 left/top。`palette` 与风格包同时出现时以 deck 里的 `palette` 为准。

旧 brief-deck 的 `content` 会当成 `bullets`。不要再写 `layout` 坐标稿去 `pptx_validate.py`。

## 分档

| 档 | 写什么 |
|----|--------|
| 下限 | `type` + 标题/要点/数据 + `palette` |
| 风格参考 | 另加 `style` 指向 `pptx_style.py` 产出；仍禁止坐标 |
| 上限 | `variant`、`emphasis`、`notes`、`type: canvas` |

canvas 颜色只许：`primary` `secondary` `accent` `background` `ink` `muted` `on_primary`，或与当前 palette 相同的 6 位 hex。

## 改图表（pptx_edit --chart-data）

整表替换：

```json
{"slide": 0, "chart": 0, "categories": ["一季度", "二季度"], "series": {"本部": [5, 6]}}
```

局部：`ops` 为 `update_series`、`add_series`、`remove_series`、`rename_category`、`set_title`。页序号与图表序号从 0 开始。
