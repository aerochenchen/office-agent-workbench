# PDF 文本/表格抽取 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 `workspace_extract` 能从数字 PDF 抽出与 docx/xlsx 同构的文本与整表 units，扫描页按页 warning、不做 OCR。

**Architecture:** 在 `doc_io` 放行 `.pdf` 并新增 `extract_pdf`（pdfplumber）；`extract_file` 增加 `pdf` 分支；更新 Agent 工具文案与 PyInstaller collect。不新增工具。

**Tech Stack:** Python 3.11+ · pdfplumber · pytest · 现有 ExtractUnit / ExtractResult

**Spec:** `docs/superpowers/specs/2026-08-06-pdf-extract-design.md`

## Global Constraints

- 标准底座依赖保持 light：可加 `pdfplumber`，禁止 `torch` / OCR 引擎 / PyMuPDF（AGPL）。
- `./scripts/check_licenses.sh` 必须通过（无 GPL/AGPL）。
- PDF `granularity=cells` 回退为 section，不报错。
- 无文本层页：warning，整文件 `ok=true`（文件可打开时）。
- 表 unit 对齐 docx：`kind=table`，行用 ` | ` 拼接。
- 用户可见文案不引入无关营销；工具描述需写明扫描页无 OCR。

## File map

| 文件 | 职责 |
|------|------|
| `runtime/requirements.txt` | 运行时依赖声明 |
| `runtime/pyproject.toml` | 包装依赖 + 可选 test 生成库 |
| `runtime/src/office_agent/doc_io.py` | normalize / extract_pdf / extract_file |
| `runtime/src/office_agent/agent_loop.py` | 工具 schema 与系统提示 |
| `runtime/tests/test_doc_io.py` | PDF 抽取与工具冒烟 |
| `packaging/runtime.spec` | PyInstaller 打入 pdfplumber 及其二进制依赖 |

---

### Task 1: 依赖 + 失败测试（正文 / 空页 / 工具）

**Files:**
- Modify: `runtime/requirements.txt`
- Modify: `runtime/pyproject.toml`
- Modify: `runtime/tests/test_doc_io.py`
- Test: `runtime/tests/test_doc_io.py`

**Interfaces:**
- Consumes: 现有 `extract_file(path, workspace_root, …) -> ExtractResult`
- Produces: 失败测试定义期望的 `format="pdf"`、`kind=page`、空页 warning、工具路径

- [ ] **Step 1: 声明依赖**

在 `runtime/requirements.txt` 末尾（`xlrd` 之后、`pytest` 之前）加入：

```
pdfplumber>=0.11.0
```

在 `runtime/pyproject.toml` 的 `dependencies` 列表加入 `"pdfplumber>=0.11.0",`。

在 `[project.optional-dependencies]` 的 `dev` 改为：

```toml
dev = ["pytest>=8.2.0", "reportlab>=4.0.0"]
```

（`reportlab` 仅用于测试生成带表 PDF，不进标准运行时必需路径。）

- [ ] **Step 2: 安装依赖**

Run:

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pip install -e ".[dev]"
```

Expected: 成功安装 `pdfplumber` 与 `reportlab`。

- [ ] **Step 3: 在测试文件中加入 PDF fixture 辅助函数**

在 `runtime/tests/test_doc_io.py` 的 `_write_xls` 之后追加：

```python
def _write_pdf_pages(path: Path, page_texts: list[str | None]) -> None:
    """Write a minimal multi-page PDF. None = empty content (no text layer)."""
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    path.parent.mkdir(parents=True, exist_ok=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    for text in page_texts:
        if text:
            c.setFont("Helvetica", 12)
            y = 800
            for line in text.split("\n"):
                c.drawString(72, y, line)
                y -= 18
        c.showPage()
    c.save()


def _write_pdf_with_table(path: Path) -> None:
    reportlab = pytest.importorskip("reportlab")
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
    from reportlab.lib.styles import getSampleStyleSheet

    path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    data = [
        ["Dept", "Rate", "Note"],
        ["Office", "95%", "pilot"],
        ["Biz", "88%", ""],
    ]
    table = Table(data, colWidths=[120, 80, 120])
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
            ]
        )
    )
    doc.build(
        [
            Paragraph("Progress report", styles["Heading1"]),
            Spacer(1, 12),
            table,
        ]
    )
```

- [ ] **Step 4: 写失败测试**

在同一测试文件末尾追加：

```python
def test_extract_pdf_pages_and_empty_warning(tmp_path: Path):
    src = tmp_path / "mixed.pdf"
    _write_pdf_pages(src, ["Alpha progress 128 sites", None])
    result = extract_file(src, tmp_path)
    assert result.ok is True
    assert result.format == "pdf"
    assert result.doc_key
    page_units = [u for u in result.units if u.kind == "page"]
    assert len(page_units) >= 1
    blob = "\n".join(u.text for u in page_units)
    assert "128" in blob
    assert any("无文本层" in w for w in result.warnings)


def test_extract_pdf_table_unit(tmp_path: Path):
    src = tmp_path / "table.pdf"
    _write_pdf_with_table(src)
    result = extract_file(src, tmp_path)
    assert result.ok is True
    tables = [u for u in result.units if u.kind == "table"]
    assert tables, "expected at least one table unit"
    assert any("|" in u.text for u in tables)
    assert any("Office" in u.text or "95%" in u.text for u in tables)


def test_extract_pdf_paragraph_granularity(tmp_path: Path):
    src = tmp_path / "para.pdf"
    _write_pdf_pages(src, ["Line one\nLine two"])
    section = extract_file(src, tmp_path, granularity="section")
    paragraph = extract_file(src, tmp_path, granularity="paragraph")
    assert paragraph.ok is True
    para_units = [u for u in paragraph.units if u.kind == "paragraph"]
    assert len(para_units) >= 1
    assert all(u.meta.get("granularity") == "paragraph" for u in para_units)
    assert section.units[0].kind == "page"


def test_extract_pdf_cells_falls_back(tmp_path: Path):
    src = tmp_path / "cells.pdf"
    _write_pdf_pages(src, ["fallback body"])
    result = extract_file(src, tmp_path, granularity="cells")
    assert result.ok is True
    assert result.format == "pdf"
    assert any(u.kind == "page" for u in result.units)


def test_workspace_extract_pdf_tool(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OFFICE_AGENT_DATA", str(tmp_path / "data"))
    (tmp_path / "data" / "skills").mkdir(parents=True)
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_pdf_pages(ws / "材料.pdf", ["Workspace PDF body 42"])
    ex = ToolExecutor(
        Workspace(ws),
        SkillRegistry(),
        permission_mode="trust",
        audit=AuditLog(tmp_path / "data" / "a.sqlite"),
    )
    r = ex.execute("workspace_extract", {"path": "材料.pdf"})
    assert r["ok"] is True
    assert r["format"] == "pdf"
    assert r["units"]
    assert r["units"][0]["unit_id"].startswith(r["doc_key"] + "#u")
    assert any("42" in u["text"] for u in r["units"])
```

- [ ] **Step 5: 跑测试确认失败（尚未实现 extract）**

Run:

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pytest tests/test_doc_io.py::test_extract_pdf_pages_and_empty_warning tests/test_doc_io.py::test_extract_pdf_table_unit -v
```

Expected: FAIL（`unsupported format` / `unsupported format for normalize: .pdf`）。

- [ ] **Step 6: Commit**

```bash
git add runtime/requirements.txt runtime/pyproject.toml runtime/tests/test_doc_io.py
git commit -m "$(cat <<'EOF'
test: add failing PDF extract coverage before implementation

EOF
)"
```

---

### Task 2: 实现 `extract_pdf` 并接入 `extract_file`

**Files:**
- Modify: `runtime/src/office_agent/doc_io.py`
- Test: `runtime/tests/test_doc_io.py`

**Interfaces:**
- Consumes: `ExtractUnit`, `ExtractResult`, `short_doc_key`, `_tags_for`, `max_chars` / `max_units`
- Produces:
  - `normalize_path` 对 `.pdf` 返回 `(src, "pdf", warnings)`
  - `extract_pdf(path, doc_key, *, max_chars, max_units, granularity="section") -> tuple[list[ExtractUnit], bool, list[str]]`
  - `extract_file` 在 `fmt == "pdf"` 时调用 `extract_pdf`

- [ ] **Step 1: 更新模块 docstring**

将 `doc_io.py` 顶部 docstring 改为包含 PDF：

```python
"""Document I/O: normalize legacy Office formats and extract text units.

- .doc  → .docx (soffice / textutil / optional Word COM later)
- .xls  → .xlsx (xlrd → openpyxl)
- extract: .docx / .xlsx / .pdf → list of units with stable unit_id anchors
"""
```

- [ ] **Step 2: `normalize_path` 放行 pdf**

在 `normalize_path` 中，于 `.xlsx` 分支之后、`.doc` 之前插入：

```python
    if suffix == ".pdf":
        return src, "pdf", warnings
```

并将错误信息改为：

```python
    raise DocIOError(
        f"unsupported format for normalize: {suffix} "
        "(supported: .doc .docx .xls .xlsx .pdf)"
    )
```

- [ ] **Step 3: 实现 `extract_pdf`**

在 `extract_xlsx` 之后、`extract_file` 之前插入完整函数：

```python
def extract_pdf(
    path: Path,
    doc_key: str,
    *,
    max_chars: int,
    max_units: int,
    granularity: str = "section",
) -> tuple[list[ExtractUnit], bool, list[str]]:
    try:
        import pdfplumber
    except ImportError as e:
        raise DocIOError(
            "reading .pdf requires pdfplumber; install runtime deps"
        ) from e

    gran = (granularity or "section").strip().lower()
    if gran == "cells":
        gran = "section"
        cells_fallback = True
    else:
        cells_fallback = False
    if gran not in {"section", "paragraph"}:
        gran = "section"

    warnings: list[str] = []
    if cells_fallback:
        warnings.append("pdf 不支持 granularity=cells，已回退为 section")

    units: list[ExtractUnit] = []
    total_chars = 0
    truncated = False
    unit_i = 0

    def _append(kind: str, locator: str, text: str, meta: dict[str, Any]) -> bool:
        nonlocal unit_i, total_chars, truncated
        text = text.strip()
        if not text:
            return False
        if len(units) >= max_units:
            truncated = True
            return True
        if total_chars + len(text) > max_chars:
            remain = max_chars - total_chars
            if remain <= 0:
                truncated = True
                return True
            text = text[:remain] + "…"
            truncated = True
        unit_i += 1
        units.append(
            ExtractUnit(
                unit_id=f"{doc_key}#u{unit_i:02d}",
                kind=kind,
                locator=locator,
                text=text,
                tags=_tags_for(text),
                meta=meta,
            )
        )
        total_chars += len(text)
        return truncated

    with pdfplumber.open(str(path)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            table_objs = []
            try:
                table_objs = page.find_tables() or []
            except Exception as exc:  # noqa: BLE001
                warnings.append(f"第{page_no}页: 表检测失败（{exc}）")
                table_objs = []

            # Body text: prefer filtering out table bboxes; fall back to full page.
            try:
                if table_objs:
                    bboxes = [t.bbox for t in table_objs if getattr(t, "bbox", None)]

                    def _not_in_tables(obj: dict[str, Any]) -> bool:
                        x0 = float(obj.get("x0", 0))
                        x1 = float(obj.get("x1", 0))
                        top = float(obj.get("top", 0))
                        bottom = float(obj.get("bottom", 0))
                        cx = (x0 + x1) / 2
                        cy = (top + bottom) / 2
                        for bx0, btop, bx1, bbottom in bboxes:
                            if bx0 <= cx <= bx1 and btop <= cy <= bbottom:
                                return False
                        return True

                    filtered = page.filter(_not_in_tables)
                    body = filtered.extract_text() or ""
                else:
                    body = page.extract_text() or ""
            except Exception:  # noqa: BLE001
                body = page.extract_text() or ""

            body = (body or "").strip()
            if not body and not table_objs:
                warnings.append(
                    f"第{page_no}页: 无文本层（疑似扫描或纯图，暂不支持 OCR）"
                )
            elif gran == "paragraph":
                blocks = [b.strip() for b in body.split("\n") if b.strip()]
                for bi, block in enumerate(blocks, start=1):
                    if _append(
                        "paragraph",
                        f"第{page_no}页@块{bi}",
                        block,
                        {
                            "page": page_no,
                            "block": bi,
                            "granularity": "paragraph",
                        },
                    ):
                        break
            elif body:
                if _append(
                    "page",
                    f"第{page_no}页",
                    body,
                    {"page": page_no, "granularity": "section"},
                ):
                    pass

            for ti, tobj in enumerate(table_objs, start=1):
                try:
                    grid = tobj.extract()
                except Exception as exc:  # noqa: BLE001
                    warnings.append(f"第{page_no}页-表{ti}: 抽取失败（{exc}）")
                    continue
                if not grid:
                    continue
                rows: list[str] = []
                for row in grid:
                    cells = [
                        " ".join(str(c).split()) if c is not None else ""
                        for c in row
                    ]
                    line = " | ".join(cells).strip()
                    if line:
                        rows.append(line)
                if not rows:
                    continue
                if _append(
                    "table",
                    f"第{page_no}页-表{ti}",
                    "\n".join(rows),
                    {
                        "page": page_no,
                        "table_index": ti,
                        "granularity": gran,
                    },
                ):
                    break
            if truncated or len(units) >= max_units:
                break

    if not units and not any("无文本层" in w for w in warnings):
        warnings.append("pdf 未解析到文本或表格")
    return units, truncated, warnings
```

- [ ] **Step 4: `extract_file` 接入 pdf 分支**

将 `extract_file` 中 `if fmt == "docx": ... elif fmt == "xlsx": ... else:` 改为包含 pdf：

```python
        if fmt == "docx":
            units, truncated, w2 = extract_docx(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
            )
        elif fmt == "xlsx":
            units, truncated, w2 = extract_xlsx(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
            )
        elif fmt == "pdf":
            units, truncated, w2 = extract_pdf(
                modern,
                doc_key,
                max_chars=max_chars,
                max_units=max_units,
                granularity=granularity,
            )
        else:
            raise DocIOError(f"unsupported extract format: {fmt}")
```

同时把 `extract_file` docstring 改为提到 pdf。

无 workspace 时的 early path：在 `suffix in {".doc", ".xls"}` 旁逻辑保持不变；`.pdf` 走 `suffix.lstrip(".")` → `fmt="pdf"`，无需 normalize。

- [ ] **Step 5: 跑 PDF 相关测试**

Run:

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pytest tests/test_doc_io.py -k pdf -v
```

Expected: 全部 PASS。若 `test_extract_pdf_table_unit` 因 reportlab 表线检测失败，可在该测试中改用 `page.extract_tables()` 验证前先本地调试；必要时在 `_write_pdf_with_table` 加强 `GRID` 线宽至 `1`，或断言放宽为「正文含 Progress / Office」且表 unit 可选——但规格要求至少一表，应优先修 fixture 使 pdfplumber 能检出。

- [ ] **Step 6: 回归既有抽取测试**

Run:

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pytest tests/test_doc_io.py -v
```

Expected: 全部 PASS（`xlwt` 缺失时旧 xls 用例 skip 可接受）。

- [ ] **Step 7: Commit**

```bash
git add runtime/src/office_agent/doc_io.py runtime/tests/test_doc_io.py
git commit -m "$(cat <<'EOF'
feat: extract text and tables from PDF via pdfplumber

EOF
)"
```

---

### Task 3: Agent 工具文案与系统提示

**Files:**
- Modify: `runtime/src/office_agent/agent_loop.py`（约 L58、L70–L76、L439）
- Test: 若已有 `tests/test_agent_loop.py` 断言工具描述，同步更新；否则以手工核对 + 既有测试不破为准

**Interfaces:**
- Consumes: 无新 API
- Produces: 模型可见描述包含 `.pdf` 与「扫描页无 OCR」

- [ ] **Step 1: 更新 `workspace_read` 描述**

将 L58 附近改为：

```python
                "读取工作区内【纯文本】文件内容。"
                "Office/PDF 文件（.docx/.doc/.xlsx/.xls/.pdf）请改用 workspace_extract。"
```

- [ ] **Step 2: 更新 `workspace_extract` 描述**

将 L71–L76 附近改为：

```python
            "description": (
                "从工作区 Office/PDF 文件抽取可引用文本单元（含 unit_id）。"
                "支持 .docx/.xlsx/.pdf；.doc/.xls 会先规范化为 docx/xlsx 再抽取。"
                "PDF 仅支持有文本层的数字稿；扫描/纯图页会 warning，不做 OCR。"
                "不要用 workspace_read 读这些二进制格式。"
                "docx 可用 granularity=paragraph 按段抽取（校对/定位）；默认 section 按章节。"
                "xlsx 可用 granularity=cells 按单元格抽取（表格成文）；默认按行块。"
                "pdf 默认按页；granularity=paragraph 按页内文本行块；不支持 cells。"
            ),
```

`granularity` 参数说明可改为：

```python
                        "description": (
                            "抽取粒度：docx 用 section|paragraph；"
                            "xlsx 用 section|cells；"
                            "pdf 用 section|paragraph（cells 会回退为 section）"
                        ),
```

- [ ] **Step 3: 更新系统提示中的读取约定**

将约 L439 的句子改为：

```python
        "- 读取 .docx/.doc/.xlsx/.xls/.pdf 请用 workspace_extract"
        "（.doc/.xls 会先转为 docx/xlsx；PDF 扫描页无 OCR）；\n"
```

（保持与周围字符串拼接风格一致；若原为单行 f-string/普通字符串，按文件现有写法改一处即可。）

- [ ] **Step 4: 跑 agent_loop / doc_io 测试**

Run:

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pytest tests/test_agent_loop.py tests/test_doc_io.py -v
```

Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add runtime/src/office_agent/agent_loop.py
git commit -m "$(cat <<'EOF'
docs: mention PDF support in workspace_extract tool prompts

EOF
)"
```

---

### Task 4: 打包 hiddenimports + 许可证门禁

**Files:**
- Modify: `packaging/runtime.spec`
- Verify: `scripts/check_licenses.sh`

**Interfaces:**
- Consumes: Task 1 已安装的 pdfplumber 树
- Produces: PyInstaller 能收集 `pdfplumber` / `pdfminer` / `pypdfium2`；许可证扫描通过

- [ ] **Step 1: 更新 `runtime.spec` hiddenimports 与 collect_all**

在 `hiddenimports` 列表（含 `"xlrd"` 处）追加：

```python
        "pdfplumber",
        "pdfminer",
        "pypdfium2",
```

在 `for pkg in (...)` 元组中追加：

```python
    "pdfplumber",
    "pdfminer",
    "pypdfium2",
    "PIL",
```

- [ ] **Step 2: 许可证扫描**

确保当前用于扫描的 venv 已装 runtime 依赖后执行：

```bash
cd /Users/chenzai/内部办公智能体 && bash scripts/check_licenses.sh
```

Expected: 退出码 0（无 GPL/AGPL）。若失败，记录违规包并改用兼容版本或换实现——不得引入 AGPL。

- [ ] **Step 3: Commit**

```bash
git add packaging/runtime.spec
git commit -m "$(cat <<'EOF'
build: bundle pdfplumber stack in runtime sidecar

EOF
)"
```

---

### Task 5: 收口验证

**Files:** 无新文件

- [ ] **Step 1: 全量 runtime 测试**

```bash
cd /Users/chenzai/内部办公智能体/runtime && python3 -m pytest -v
```

Expected: 全绿（或缺可选依赖时 skip 与既有基线一致）。

- [ ] **Step 2: 对照 spec 验收清单**

逐项确认 `docs/superpowers/specs/2026-08-06-pdf-extract-design.md` §9：

1. 多页文本 PDF → `format=pdf` + page units  
2. 简单表 → `kind=table` + `|`  
3. 混合空页 → warning + `ok=true`  
4. 工具层 `workspace_extract`  
5. docx/xlsx 不回归  
6. `check_licenses.sh` 通过  

- [ ] **Step 3: 将 spec 状态改为「已实施」**（可选，与用户确认后）

把 design 文档头 `**状态：** 待实施` 改为 `**状态：** 已实施`。

- [ ] **Step 4: Commit（若有状态更新）**

```bash
git add docs/superpowers/specs/2026-08-06-pdf-extract-design.md
git commit -m "$(cat <<'EOF'
docs: mark PDF extract design as implemented

EOF
)"
```

---

## Spec coverage self-check

| Spec 要求 | 任务 |
|-----------|------|
| normalize/extract 支持 pdf | Task 2 |
| extract_pdf + 表对齐 docx | Task 2 |
| pdfplumber 依赖 | Task 1 |
| 工具描述 / 系统提示 | Task 3 |
| 空页按页 warning | Task 1 测试 + Task 2 |
| cells 回退 | Task 1 测试 + Task 2 |
| 许可证门禁 | Task 4 |
| PyInstaller 二进制 | Task 4 |
| 验收 / 不回归 | Task 5 |

无 OCR、无新工具、不改白名单：刻意 Out，无任务。
