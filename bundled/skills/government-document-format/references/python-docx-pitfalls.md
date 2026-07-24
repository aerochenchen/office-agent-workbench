# python-docx 陷阱：多段落插入与段落操作

## 陷阱一：`addprevious` + `reversed()` 不可靠

### 问题

在目标段落前插入多个段落时，常见的 `reversed(insert_list) + addprevious` 模式可能产生不可预测的结果：

```python
# ❌ 不可靠
for text, font, bold in reversed(insert_list):
    p = doc.add_paragraph()
    ref._element.addprevious(p._element)
    set_para_text(p, text, cn=font, bold=bold)
```

`addprevious` 每次调用都在同一个 `ref._element` 前插入，但当 `ref` 是 `doc.paragraphs[idx]` 时，段落索引可能因前面的文本修改而漂移，导致插入位置错误或顺序反转。

### 正确做法

使用 `parent.insert()` 直接操作 XML 树：

```python
# ✅ 可靠
body = doc.element.body
parent = body
children = list(parent)
ref_pos = children.index(ref._element)

# 1. 创建所有新段落元素
new_elements = []
for text, font, bold in insert_list:
    p = doc.add_paragraph()
    body.remove(p._element)  # 从文档尾部移除
    if text:
        set_para_text(p, text, cn=font, bold=bold)
    new_elements.append(p._element)

# 2. 批量插入（正序，无需 reversed）
for i, el in enumerate(new_elements):
    parent.insert(ref_pos + i, el)
```

### 关键点

- `doc.add_paragraph()` 会将段落添加到文档末尾 → 立即用 `body.remove()` 取下
- `parent.insert(pos, el)` 在 XML 树级别精确控制位置
- 正序循环，每插入一个元素后续位置自动 +1
- 不依赖段落索引（索引在操作期间可能失效）

## 陷阱二：修改段落后索引漂移

当用 `set_para_text()` 修改段落文本后，依赖原段落索引查找后续段落时，索引可能已变化（尤其是当修改操作改变了段落数量时）。

### 正确做法

- 插入/删除操作前，用文本内容匹配（而非硬编码索引）找到目标段落
- 每次结构性修改后，重新 `find()` 目标段落
- 批量修改前一次性收集所有目标索引

## 陷阱三：清除段落内容时不要删除段落元素

用 `set_para_text(para, '')` 清空内容比 `body.remove(para._element)` 更安全，因为删除元素会导致后续所有段落的索引变化。只在确认不需要保留段落占位时才删除元素。
