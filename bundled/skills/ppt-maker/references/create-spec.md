# 新建页纲与改图表参数

路径都相对当前文件夹。颜色用 6 位十六进制，不要带 `#`。位置单位是英寸。

## deck.json

```json
{
  "slide_size": "16:9",
  "slides": [
    {"layout": "title", "title": "标题", "subtitle": "副标题", "notes": "备注"},
    {
      "layout": "title_content",
      "title": "议程",
      "bullets": [
        "一级要点",
        {"text": "二级要点", "level": 1, "bold": true, "size": 18, "color": "1B3A5F"}
      ]
    },
    {
      "layout": "blank",
      "images": [{"path": "logo.png", "left": 0.6, "top": 0.4, "width": 1.6}],
      "tables": [{
        "left": 0.6, "top": 1.6, "width": 8, "height": 2,
        "rows": [["栏目", "数量"], ["甲", "12"]]
      }],
      "shapes": [{
        "type": "rounded_rectangle",
        "left": 9, "top": 1.6, "width": 3, "height": 1,
        "fill": "1B3A5F", "text": "说明", "text_color": "FFFFFF"
      }],
      "charts": [{
        "type": "bar",
        "left": 0.6, "top": 4, "width": 6, "height": 3,
        "title": "对比",
        "categories": ["一季度", "二季度"],
        "series": {"本部": [10, 12], "分部": [7, 9]}
      }]
    }
  ]
}
```

- `slide_size`：`16:9`（默认）或 `4:3`
- `layout`：`title`、`title_content`、`section`、`two_content`、`title_only`、`blank`
- 图表 `type`：`bar`、`bar_h`、`line`、`pie`
- 形状 `type`：`rectangle`、`rounded_rectangle`、`oval`、`diamond`、`right_arrow`、`chevron`
- 要点可以是字符串，或带 `level`（0–4）、`size`、`bold`、`italic`、`font`、`color`、`link` 的对象

## 改图表 chart.json

整表替换：

```json
{"slide": 0, "chart": 0, "categories": ["一季度", "二季度"], "series": {"本部": [5, 6]}}
```

局部修改用 `ops`：`update_series`、`add_series`、`remove_series`、`rename_category`（`from` / `to`）、`set_title`。

页序号、同一页上的图表序号都从 0 开始。
