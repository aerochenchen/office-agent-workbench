# 文书通 · PDF 文本/表格抽取设计

**日期：** 2026-08-06（2026-09-09 增补：无文本层印刷体 OCR）  
**状态：** 已实施  
**范围：** 标准 Runtime 的 `workspace_extract` / `doc_io`：数字 PDF 抽取（含基础表格）+ 无文本层印刷体扫描/图片版 OCR。不含手写、印章、写回 PDF。

## 1. Objective

用户将 `.pdf` 放入工作区后，Agent 可通过现有 `workspace_extract` 得到与 docx/xlsx 同构的可引用文本单元（含 `unit_id`）。有文本层的页抽正文与基础表格；无文本层的印刷体扫描/图片版页做 OCR（默认最多 30 页），并标明识别来源。OCR 仍为空的页 warning，不假装已读。

## 2. In / Out

**In**

- `normalize_path` / `extract_file` 支持 `.pdf`（无需规范化转换）
- 新增 `extract_pdf`：按页抽正文 + `pdfplumber` 表检测；表 unit 对齐现有 docx 表形态
- `runtime/requirements.txt` 与 `pyproject.toml` 增加 `pdfplumber`
- 更新 `workspace_extract` / `workspace_read` 工具描述与相关系统提示
- pytest：正文、表格、空页 warning、工具层冒烟

**Out**

- 手写、印章、图中表结构还原、视觉多模态读图
- PyMuPDF（AGPL，与 `check_licenses.sh` 冲突）
- PDF 的 `granularity=cells`（单元格级）
- 新工具名；改 workspace 白名单（已含 `.pdf`）
- 写回/编辑 PDF

## 3. 决策摘要

| 项 | 选择 |
|----|------|
| 覆盖面 | 数字 PDF 文本 + 基础表格（方案 B） |
| 表格粒度 | 整表一个 unit，行用 ` \| ` 拼接（对齐 docx） |
| 无文本层 | 按页 warning，整文件不因此失败（方案 C） |
| 库 | `pdfplumber` 接入 `doc_io`（方案 1） |

## 4. 架构与数据流

沿用现有链路，不新增 Agent 工具：

```
.PDF
  → normalize_path：suffix=.pdf → (path, "pdf", [])
  → extract_pdf → units（page/paragraph + table）
  → ExtractResult(format="pdf", …)
```

调用路径：`ToolExecutor._workspace_extract` → `extract_file` → `extract_pdf`。

## 5. Unit 形态与粒度

### 5.1 正文 · `granularity=section`（默认）

- 每页一个 unit：`kind=page`
- `locator`：`第N页`（1-based）
- `text`：该页正文，段间 `\n`。实现时尽量按表 bbox 裁掉表区文字；若裁剪不可靠，允许页 unit 与表 unit 有少量重复（宁可重复，不丢正文）
- `meta`：`{ "page": N, "granularity": "section" }`

### 5.2 正文 · `granularity=paragraph`

- 按页内文本块拆分：`kind=paragraph`
- `locator`：`第N页@块k`
- `meta`：含 `page`、块序号、`granularity`
- 不做不可靠的假章节/标题层级检测

### 5.3 表格（section / paragraph 均抽取）

- 每个检测到的表：`kind=table`
- 行单元格用 ` | ` 拼接（与 `extract_docx` 一致）
- `locator`：`第N页-表M`
- `meta`：`{ "page": N, "table_index": M, "granularity": … }`
- 空表或检测失败：跳过该表，不影响正文

### 5.4 无文本层页

- 先尝试 pypdfium2 渲染 + RapidOCR（印刷体，默认最多 30 页）
- 识别成功：`kind=page`（或 paragraph），`meta.source=ocr`；warning 先说明处理得好的材料（Word/WPS、能选中文字的 PDF），再说明当前扫描件不能保证准确及可能出现的问题
- 超过上限的扫描页：`truncated=true`，warning 说明未识别
- OCR 仍无字：不产生空 unit；`warnings` 追加无文本层（疑似纯图或识别无结果）
- 有字页不跑 OCR；文件可打开则 `ok=true`

### 5.5 截断与 cells

- 沿用全局 `max_chars` / `max_units`；超限 `truncated=true`
- PDF 上 `granularity=cells`：回退为 section，可选 warning；不报错

## 6. 错误处理

| 情况 | 行为 |
|------|------|
| 未安装 pdfplumber | `ok=false`，提示安装 runtime deps |
| 文件损坏/无法打开 | `ok=false`，error 说明原因 |
| 某页无字 | warning，不失败 |
| 表检测失败 | 跳过该表 |
| `cells` 粒度 | 回退 section |

## 7. 依赖与合规

- 声明：`pdfplumber>=0.11.0`（MIT）
- 传递依赖预期含 `pdfminer.six`、`Pillow`、`pypdfium2`（均非 GPL/AGPL）
- 发版门禁：`./scripts/check_licenses.sh` 必须通过
- 标准底座仍禁止 torch；印刷体 OCR 用 RapidOCR + ONNX Runtime（随 sidecar 打包模型）

## 8. Agent 文案

- `workspace_extract`：支持列表含 `.pdf`；无文本层印刷体页会 OCR，并说明好材料与识别不准的风险
- `workspace_read`：Office + PDF 请用 extract
- 系统提示中「读取 Office」类句子同步包含 PDF

## 9. 验收标准

1. 有文本层多页 PDF：`format=pdf`，至少有 `kind=page`（或 paragraph）units，正文含关键句
2. 含简单网格表：至少一个 `kind=table`，行文本含 ` | `
3. 混合页（有字 + 无字）：有字页有 unit；无字页仅 warning；`ok=true`
4. `workspace_extract` 对工作区 `.pdf` 返回 `ok=true` 且带 `unit_id`
5. 既有 docx/xlsx 抽取测试不回归
6. `check_licenses.sh` 在装入 pdfplumber 后仍通过

## 10. 测试约定

- Fixture 优先在测试内用轻量库生成 PDF（避免仓库堆二进制）；若生成成本过高可提交极小样例 PDF
- 覆盖：`extract_file` 直调 + `ToolExecutor` / `workspace_extract` 冒烟

## 11. 实现触点（文件清单）

| 文件 | 变更 |
|------|------|
| `runtime/requirements.txt` | 加 pdfplumber |
| `runtime/pyproject.toml` | dependencies 同步 |
| `runtime/src/office_agent/doc_io.py` | normalize / extract_pdf / extract_file |
| `runtime/src/office_agent/agent_loop.py` | 工具描述与提示 |
| `runtime/tests/test_doc_io.py` | 新用例 |

打包脚本（`build-macos.sh` / `build-windows.ps1`）已按 requirements 安装，预期无需逻辑改动；若 PyInstaller 漏打二进制扩展（如 pypdfium2），在实现阶段验证并按需补 hiddenimports。
