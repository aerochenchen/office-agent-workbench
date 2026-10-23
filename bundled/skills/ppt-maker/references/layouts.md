# 页类型（只许从表里抄）

默认 16:9。模型选 `type`，不要写位置或字号。

| type | 何时用 | 必填内容 |
|------|--------|----------|
| `title` | 封面 | `title`，可选 `subtitle` |
| `toc` | 目录/提纲页 | `bullets`（条目名） |
| `section` | 章节隔页 | `title` |
| `bullets` | 一页一意的要点 | `title` + `bullets`（≤6，建议 3～5） |
| `two_column` | 左右对照 | `title` + `left` + `right` |
| `kpi` | 2～4 个关键数字 | `title` + `kpis`：`{"label","value"}` |
| `table` | 对照表 | `title` + `rows`（含表头，≤10 行） |
| `chart` | 数据图 | `title` + `chart.kind/categories/series` |
| `mixed_chart` | 图 + 解读 | `chart` + `bullets` |
| `process` | 流程步骤 | `title` + `steps`（≤6） |
| `closing` | 结束/请示 | `title` + `bullets` |
| `canvas` | 强模型自定义 | 英寸坐标；颜色只用 token 名 |

## 选填（弱模型省略）

- `variant`：`cards`（bullets）、`hero`（kpi）、`chevron`（process）、`split`（chart）
- `emphasis`：要点下标，每页最多 2 个，引擎用强调色
- `notes`：本页口播备注

## 图表 kind

`bar` / `bar_h` / `line` / `pie`

## 配色

`palette` 用 id，或 `{"primary":"003A70"}` 由脚本生成整套 token。
