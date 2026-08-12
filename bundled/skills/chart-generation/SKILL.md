---
name: chart-generation
description: 把表格、Excel、CSV、数字等数据自动转成最合适的图表，可按需换图型；用于展示、分析、汇报。
version: 1.0.0
tier: light
display_name: 图表生成
---
# Chart Generation

A general-purpose workflow for turning any kind of source material into the chart that best communicates it — and for re-rendering the same data as a different chart type on request.

## Why a dedicated workflow matters

Picking a chart type is not a styling choice, it's a comprehension choice. The same table rendered as a pie chart vs. a line chart vs. a heatmap can lead a reader to completely different conclusions (or none at all). The goal of this skill is to stop and reason about *what question the data is meant to answer* before touching any charting library, so the chart produced is the one that actually answers it — not just the first one that comes to mind (bar/pie/line are overused defaults that are frequently wrong for the data at hand).

## Workflow

### 1. Understand the material

Before selecting anything, work out:

- **What is being measured, and what type is it?** Categorical labels, timestamps/dates, continuous numbers, counts, percentages, geographic locations, free text, ranked positions, hierarchical groupings (category > subcategory), paired coordinates (x/y), or a matrix of values.
- **How many variables are involved?** One (a single series of values), two (e.g. category + value, or x + y), or three-plus (e.g. category + value + time, or value + size + color).
- **How many data points / categories?** A handful (≤7), a moderate set (8–20), or many (20+). This alone rules out several chart types (e.g. pie charts stop working past ~5-6 slices; dense scatter plots need hundreds of points to look meaningful).
- **What is the reader trying to learn?** Compare magnitudes, see a trend, understand parts of a whole, find a relationship/correlation, see a distribution/spread, see a ranking, trace a flow or hierarchy, locate something geographically, or just check one KPI at a glance. This is the single most important question — the same dataset can support several of these goals, and the goal (not the data shape) usually decides the chart.
- **Any format constraints?** Static report/document vs. interactive dashboard/artifact, black-and-white print vs. color, one chart vs. a small-multiples grid.

If the material is a file (CSV/Excel/JSON/etc.), inspect it directly (columns, dtypes, row count, null rates, date ranges) rather than guessing from a sample or from what the user describes — real data is messier than descriptions of it.

### 2. Select the chart type

Use the decision table below to shortlist, then read `references/chart-catalog.md` for the specific chart family that matches — it lists when each type is the right call, when it silently fails (common misuse), and implementation notes.

| Reader's goal | Data shape | Likely chart family |
|---|---|---|
| Compare magnitudes across categories | Categorical + numeric, few-to-moderate categories | Bar / column, grouped or stacked bar |
| See change over time | Time/ordered axis + numeric | Line, area, candlestick (financial OHLC) |
| Understand parts of a whole | Categories that sum to a total | Donut/pie (≤5-6 slices only), stacked bar, treemap, waterfall (sequential +/- to a total) |
| See distribution / spread | One numeric variable, many observations | Histogram, box plot, violin plot |
| Find a relationship or correlation | Two-plus numeric variables | Scatter, bubble (3rd variable = size), heatmap (correlation matrix) |
| See a ranking | Categorical + numeric, order matters | Sorted bar/lollipop, dumbbell (before/after), bump chart (rank over time) |
| Trace a flow, funnel, or hierarchy | Sequential stages, or nested categories | Sankey, funnel, treemap, sunburst, tree/org chart |
| Locate something geographically | Data tied to regions/coordinates | Choropleth map, bubble map |
| Check one number at a glance | Single value (+ target/threshold) | Gauge, KPI card, bullet chart |
| Compare many attributes at once | Multiple numeric dimensions per entity, few entities | Radar / spider chart |
| Show word/term frequency | Free text with counts | Word cloud (use sparingly — see catalog notes on when it's actually useful) |

When more than one row plausibly applies, prefer the option that lets the reader answer their question in the fewest glances, and default to the simpler, more familiar chart type unless the extra complexity earns its keep (a heatmap is not inherently better than a well-sorted bar chart just because it looks more sophisticated).

If the data supports it and the goal genuinely benefits from more than one angle (e.g. "trend AND composition"), it's fine to produce two small charts rather than forcing one chart to do both jobs.

### 3. Build it

Pick a concrete implementation based on where the output is going — see `references/implementation.md` for library choices, setup, and code patterns for both static/report output and interactive/web output. In short:

- **Static output (reports, documents, presentations, print):** Python with matplotlib/seaborn for simple charts, or plotly for anything that benefits from more polish; export as an image or embed directly into the docx/pptx/pdf skill's workflow if one of those is also in play.
- **Interactive output (dashboards, artifacts, chat-embedded visuals):** Prefer the environment's native visualization tool if one is available (e.g. a visualizer/widget tool). Otherwise build with Chart.js, ECharts, or Recharts in an HTML/React artifact.

Regardless of tool, every chart needs: a clear title, labeled axes (with units), a legend when there's more than one series, readable tick density (don't cram 50 unlabeled x-axis ticks), and a sensible sort order (usually by value, not alphabetical, unless the categories are inherently ordered like time or a scale).

### 4. Sanity-check before presenting

Quickly re-read the chart as if seeing it for the first time:

- Does it actually answer the reader's original question, or just plot the data?
- Is any axis or scale misleading (truncated y-axis exaggerating differences, unequal time intervals treated as equal, a log scale used without saying so)?
- Are there too many categories/series to read (if so, group the smallest into "Other," or switch chart types, or split into small multiples)?
- Would a different chart type make the same data click faster? If so, prefer it — don't stay wedded to the first choice.

## Switching between chart types

When the user asks to see the same data differently ("换个图"、"用柱状图试试"、"有没有更清楚的展示方式"), or when the sanity check above flags a poor fit:

1. Keep the underlying data/query untouched — only the rendering changes.
2. Re-run the selection table with the new constraint in mind (the user may be signaling a goal you didn't originally infer, e.g. asking for a line chart on categorical data usually means they actually care about a trend you missed).
3. If the requested chart type is a poor fit for the data (e.g. they ask for a pie chart with 30 slices, or a line chart with no time/order axis), say so plainly, explain the specific problem it will cause, and offer the closest well-suited alternative — but still produce what they explicitly ask for if they confirm they want it anyway.
4. When producing multiple candidate views is cheap and the best choice is genuinely unclear, offer 2-3 rendered options side by side rather than debating chart theory in prose.

## Reference files

- `references/chart-catalog.md` — full catalog of mainstream chart types grouped by purpose (comparison, trend, composition, distribution, relationship, ranking, flow/hierarchy, geographic, single-value, text), with when-to-use, common misuse, and data-shape requirements for each.
- `references/implementation.md` — library and tool choices for static vs. interactive output, with setup notes and code patterns for matplotlib/seaborn/plotly (Python) and Chart.js/ECharts/Recharts (JS/web).

## 变更记录
- 1.0.0 — 版本升为 1.0.0（正式版），description 保持中文，正文不变。

- 0.1.1 — description 由英文改写为中文（界面展示用），正文内容不变。
