# sample-30 试跑夹具

- 30 份合成 `.docx` + `gold_facts.json`（10 条必须出现的金标事实）
- `_workspace/` 由 `scripts/smoke_pipeline.py` 生成（已 gitignore）

重跑冒烟：

```bash
runtime/.venv/bin/python bundled/skills/multidoc-digest/scripts/smoke_pipeline.py
```
