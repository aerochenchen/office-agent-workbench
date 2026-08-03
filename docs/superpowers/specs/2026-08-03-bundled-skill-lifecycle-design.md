# 预置技能管理策略

**日期：** 2026-08-03  
**状态：** 已落地

## 规则

| 能力 | 预置（`source=bundled`） | 已导入（`source=user`） |
|------|--------------------------|-------------------------|
| 开启/关闭 | 允许 | 允许 |
| 卸载 | 禁止（UI 隐藏 + Runtime 拒绝） | 允许 |
| 导出 | 禁止（`can_export=false`；管理页无导出入口） | 允许（由 skill-builder 等能力承担） |
| 用新包覆盖安装 | 允许；版本低于已装须 `force_overwrite` | 允许直接覆盖 |
| 恢复出厂 | `POST /skills/{id}/restore-bundled` | 不适用 |

预置判定：安装目录名出现在当前产品 `bundled/skills/` 目录中。覆盖安装后 `overridden=true`，可「恢复预置」清回出厂包。

## API 增量

- `GET /skills` → `source` / `overridden` / `can_uninstall` / `can_export`
- `POST /skills/inspect` → `replace` 冲突信息
- `POST /skills/install` → `force_overwrite`
- `POST /skills/{id}/restore-bundled`
- `DELETE /skills/{id}` 对预置返回 400
