# 实现方式指南

选好图表类型之后，根据输出场景挑选合适的工具。不要为了"炫技"用交互式工具做一张本该是静态图片的图，也不要为了省事用静态图片来做本该可交互探索的仪表盘。

## 判断输出场景

先问：这张图最终会被谁、在哪看到？

- **嵌入报告 / Word / PPT / PDF / 打印材料** → 静态图片，用 Python。
- **在对话中直接展示、或用户要在浏览器里查看、探索、筛选数据** → 交互式，优先用当前环境自带的可视化工具（如果有），否则用网页端图表库。
- **不确定，或用户明确要"可以下载的图片"** → 静态图片更安全，之后需要交互版本再补。

## 静态输出（Python）

### matplotlib + seaborn — 默认选择
适合绝大多数常规图表（柱状图、折线图、散点图、直方图、箱线图等），生态成熟、可控性强、适合批量生成一致风格的图。

```python
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_theme(style="whitegrid")  # 干净的默认风格，避免 matplotlib 原始丑陋样式
fig, ax = plt.subplots(figsize=(10, 6))

# ...绘图逻辑...

ax.set_title("清晰的标题，说明这张图在回答什么问题")
ax.set_xlabel("X 轴（带单位）")
ax.set_ylabel("Y 轴（带单位）")
plt.tight_layout()
plt.savefig("/mnt/user-data/outputs/chart.png", dpi=150, bbox_inches="tight")
```

要点：
- 始终设置 `figsize` 和 `dpi`，避免默认输出模糊或过小。
- 类别较多时用 `plt.xticks(rotation=45, ha="right")` 避免标签重叠，而不是缩小字号到不可读。
- 配色优先用 seaborn/matplotlib 内置的色盲友好调色板（如 `"colorblind"`），除非品牌指南另有要求。

### plotly — 需要更精致视觉效果，或图表本身就要交互（悬停提示、缩放）时
生成的是 HTML，可以直接嵌入网页/artifact，也可以导出静态图片（需要 `kaleido`）。

```python
import plotly.express as px

fig = px.bar(df, x="category", y="value", title="标题")
fig.update_layout(xaxis_title="X 轴", yaxis_title="Y 轴")
fig.write_html("/mnt/user-data/outputs/chart.html")       # 交互版本
fig.write_image("/mnt/user-data/outputs/chart.png")        # 需要 pip install -U kaleido
```

### 何时用哪个
- 常规报告图表、需要严格控制每个像素的样式 → matplotlib/seaborn。
- 地图、桑基图、旭日图、树状图等复杂图表类型 → plotly（内置支持，比手写 matplotlib 省事得多）或 `pyecharts`（对中文场景、地图支持更友好）。
- K线图 → `mplfinance`（matplotlib 生态）或 plotly 的 `Candlestick`。

## 交互式输出（Web / Artifact）

### 优先使用环境自带的可视化工具
如果当前运行环境提供了内建的图表/图形展示能力（例如一个专门的 visualizer 或 widget 工具），优先用它——它通常已经处理好了主题、响应式布局这些细节，产出效果更好也更快。生成前先确认它支持目标图表类型；不支持时再退回到下面的库。

### Chart.js — 常规图表的轻量选择
柱状图、折线图、饼图、雷达图、散点图、气泡图都有原生支持，API 简单，适合大多数交互式仪表盘场景。

```html
<canvas id="chart"></canvas>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<script>
new Chart(document.getElementById('chart'), {
  type: 'bar', // 'line' | 'pie' | 'radar' | 'scatter' | 'bubble' ...
  data: { labels: [...], datasets: [{ label: '...', data: [...] }] },
  options: {
    responsive: true,
    plugins: { title: { display: true, text: '标题' } }
  }
});
</script>
```

### ECharts — 需要覆盖更冷门的图表类型时（桑基图、树图、旭日图、地图、仪表盘等）
比 Chart.js 覆盖的图表类型更全，尤其擅长中文场景和复杂图表（`references/chart-catalog.md` 里"流向/层级类"、"地理类"、"单值类"下的大多数类型都能直接用 ECharts 内置图表拿到）。

```html
<div id="chart" style="width:100%;height:500px;"></div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/echarts/5.5.0/echarts.min.js"></script>
<script>
const chart = echarts.init(document.getElementById('chart'));
chart.setOption({
  title: { text: '标题' },
  tooltip: {},
  series: [{ type: 'sankey', data: [...], links: [...] }] // 或 'bar' | 'line' | 'pie' | 'graph' | 'tree' | 'sunburst' | 'gauge' | 'map' ...
});
</script>
```

### Recharts — 在 React artifact 中构建时
如果输出环境是 React 组件（而不是原生 HTML/JS），用 Recharts 比手动集成 Chart.js/ECharts 更符合 React 的声明式写法，覆盖柱状图、折线图、面积图、饼图、散点图、雷达图等常规类型。

```jsx
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";

<ResponsiveContainer width="100%" height={400}>
  <BarChart data={data}>
    <XAxis dataKey="category" />
    <YAxis />
    <Tooltip />
    <Bar dataKey="value" />
  </BarChart>
</ResponsiveContainer>
```

## 通用注意事项（不分工具）

- **不要生造数据**：如果材料里某些字段缺失或含糊，明确跳过或标注"数据不足"，不要为了把图填满而编造数值。
- **颜色要有意义**：同一份报告/仪表盘里，同一个类别在不同图表中应使用同一种颜色，避免读者混淆。
- **数字格式化**：大数值加千分位分隔符，货币带单位符号，百分比统一保留一致的小数位数。
- **响应式与可读性优先于花哨效果**：3D 饼图、过度的阴影/渐变等"美化"效果通常会让数值更难读，除非用户明确要求这种风格。
