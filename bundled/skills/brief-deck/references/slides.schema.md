# slides.json 示例（brief-deck）

Agent 将汇报提纲落成此结构后，再调用 `build_pptx.py`。

```json
{
  "title": "XX专项工作进展汇报",
  "subtitle": "XX处 · 专题会 · 2026-08",
  "slides": [
    {
      "type": "title",
      "title": "XX专项工作进展汇报",
      "subtitle": "XX处 · 专题会 · 2026-08"
    },
    {
      "type": "section",
      "title": "一、总体进展"
    },
    {
      "type": "content",
      "title": "阶段目标完成情况",
      "bullets": [
        "已完成事项 A（见材料 path）",
        "推进中事项 B，节点待核实",
        "下步重点 C"
      ]
    },
    {
      "type": "closing",
      "title": "请示事项",
      "bullets": [
        "请审议下一步安排",
        "请明确责任处室与时限"
      ]
    }
  ]
}
```

约束：

- `type` 仅用 `title` | `section` | `content` | `closing`
- 单页 `bullets` 建议 ≤6 条；禁止把整段报告粘进一条
- 定量条必须能回溯材料或写明待核实
