# 实现方式指南

选好图表类型之后，根据输出场景挑选合适的工具。不要为了"炫技"用交互式工具做一张本该是静态图片的图，也不要为了省事用静态图片来做本该可交互探索的仪表盘。

## 运行时环境（文书通标准底座）

标准 Runtime **已内嵌 matplotlib**（无界面后端，使用 `Agg` 导出 PNG）。**未内嵌** plotly / kaleido / seaborn（体积大或连带过重）。

静态出图时：

1. **优先** `matplotlib` + `Agg`，保存 PNG，再按需嵌入 docx/pptx。
2. **不要**依赖 plotly / kaleido；缺库时不要用 PIL 手绘冒充图表（质量差、难维护）。
3. 桑基、旭日、复杂地图等 matplotlib 吃力的类型：改用更合适的常规图（堆叠柱、树状近似、表格），或说明当前环境仅支持常规统计图并给出最接近的替代图。

## 判断输出场景

先问：这张图最终会被谁、在哪看到？

- **嵌入报告 / Word / PPT / PDF / 打印材料** → 静态 PNG，用 matplotlib。
- **在对话中直接展示** → 同样优先出 PNG（路径交给用户或嵌入文稿）；交互式 HTML 仅在用户明确要求且环境能打开本地 HTML 时使用。
- **不确定，或用户明确要"可以下载的图片"** → 静态 PNG。

## 静态输出（Python · matplotlib）

适合绝大多数常规图表（柱状图、折线图、散点图、直方图、箱线图、热力图等）。

```python
import matplotlib

matplotlib.use("Agg")  # 必须在 import pyplot 之前；sidecar / 无显示器环境必需
import matplotlib.pyplot as plt
from pathlib import Path

# 中文标签：按系统常见字体回退，避免方框
plt.rcParams["font.sans-serif"] = [
    "PingFang SC",
    "Heiti SC",
    "Microsoft YaHei",
    "SimHei",
    "Noto Sans CJK SC",
    "Arial Unicode MS",
    "DejaVu Sans",
]
plt.rcParams["axes.unicode_minus"] = False

out = Path("chart.png")  # 或工作区内的 outputs 路径
fig, ax = plt.subplots(figsize=(10, 6))

# ...绘图逻辑...

ax.set_title("清晰的标题，说明这张图在回答什么问题")
ax.set_xlabel("X 轴（带单位）")
ax.set_ylabel("Y 轴（带单位）")
fig.tight_layout()
fig.savefig(out, dpi=150, bbox_inches="tight")
plt.close(fig)
```

要点：

- 始终设置 `figsize` 和 `dpi`，避免默认输出模糊或过小。
- 类别较多时用 `plt.xticks(rotation=45, ha="right")` 避免标签重叠。
- 配色优先用 matplotlib 色盲友好调色板（如 `plt.get_cmap("tab10")`），除非品牌指南另有要求。
- 画完后 `plt.close(fig)`，避免脚本批处理时泄漏内存。

### 何时不要硬上复杂图

| 目标类型 | 本环境建议 |
|---|---|
| 柱 / 条 / 折线 / 面积 / 饼(少片) / 散点 / 直方 / 箱线 / 热力 | matplotlib 直接做 |
| 桑基、旭日、复杂地图、精致交互悬停 | 换常规图，或说明能力边界；**不要**引入 plotly/kaleido |
| 仅用 Pillow 画柱子/线条 | **禁止**作为默认方案 |

## 交互式输出（Web · 可选）

仅当用户明确要可交互页面，且能接受 HTML 文件时：

- 可写自包含 HTML；**断网环境不要引用 CDN**，优先内联极简 SVG/Canvas，或告知无法拉取在线脚本。
- Chart.js / ECharts 仅在本机已有脚本资源时使用；标准安装包不保证附带这些 JS。

## 通用注意事项（不分工具）

- **不要生造数据**：字段缺失时跳过或标注"数据不足"。
- **颜色要有意义**：同一类别跨图同色。
- **数字格式化**：千分位、单位、百分比小数位一致。
- **可读性优先**：少用 3D 饼图与过度装饰。
