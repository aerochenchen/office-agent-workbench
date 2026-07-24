#!/usr/bin/env bash
# 停止 scripts/dev.sh 拉起的 Runtime / Vite（以及占用 8765/1420 的残留进程）
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${ROOT}/.dev"

log() { printf '[dev-stop] %s\n' "$*"; }

kill_pidfile() {
  local name="$1" file="$2"
  if [[ -f "$file" ]]; then
    local pid
    pid="$(cat "$file" 2>/dev/null || true)"
    if [[ -n "${pid}" ]] && kill -0 "$pid" 2>/dev/null; then
      log "结束 ${name} (pid=${pid})"
      kill "$pid" 2>/dev/null || true
      sleep 0.3
      kill -9 "$pid" 2>/dev/null || true
    fi
    rm -f "$file"
  fi
}

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    log "释放端口 ${port}: ${pids}"
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.3
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

kill_pidfile "runtime" "${STATE_DIR}/runtime.pid"
kill_pidfile "vite" "${STATE_DIR}/vite.pid"
kill_port 8765
kill_port 1420

log "完成。Tauri 窗口请手动关闭（若仍开着）。"
