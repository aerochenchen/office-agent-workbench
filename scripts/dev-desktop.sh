#!/usr/bin/env bash
# 兼容旧入口：转发到一键脚本
exec "$(cd "$(dirname "$0")" && pwd)/dev.sh" "$@"
