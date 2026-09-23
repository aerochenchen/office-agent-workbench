# 会话右键重命名 Implementation Plan

> 用户要求「直接执行」：本计划与实现同步落地，未单独阻塞开发。

**Goal:** 左侧会话栏右键「重命名 / 删除」，行内改名经 `PATCH /sessions/{id}` 持久化。

**Architecture:** Runtime `normalize_session_title` + `set_title`；桌面右键菜单与行内 input；删除移入菜单。

## Tasks

- [x] `normalize_session_title` + store/API 测试
- [x] `PATCH /sessions/{id}` + `session_renamed` 审计
- [x] `runtimeClient.renameSession` + `sessionTitle.ts`
- [x] `SessionList` 右键菜单 / 行内编辑；去掉悬停删除
- [x] `App.handleRenameSession` 接线
