#!/usr/bin/env bash
# 一键启动办公智能体联调环境：Runtime (:8765) + Vite (:1420) + Tauri 桌面壳
#
# 用法：
#   ./scripts/dev.sh           # 完整桌面（默认）
#   ./scripts/dev.sh --web     # 仅 Runtime + 浏览器前端（不开 Tauri）
#   ./scripts/dev.sh --runtime # 仅启动 / 重启 Runtime
#   ./scripts/dev-stop.sh      # 停止本脚本拉起的进程
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATE_DIR="${ROOT}/.dev"
mkdir -p "$STATE_DIR"

MODE="desktop"
for arg in "$@"; do
  case "$arg" in
    --web) MODE="web" ;;
    --runtime) MODE="runtime" ;;
    -h|--help)
      sed -n '2,10p' "$0"
      exit 0
      ;;
    *)
      echo "未知参数: $arg（支持 --web / --runtime）" >&2
      exit 1
      ;;
  esac
done

log() { printf '[dev] %s\n' "$*"; }

wait_http() {
  local url="$1" name="$2" n="${3:-40}"
  local i=0
  while (( i < n )); do
    if curl -sf "$url" >/dev/null 2>&1; then
      log "${name} 就绪 → ${url}"
      return 0
    fi
    sleep 0.25
    i=$((i + 1))
  done
  log "等待 ${name} 超时：${url}"
  return 1
}

pid_alive() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

# Desktop mode: Tauri injects OFFICE_AGENT_API_TOKEN and will not attach to a
# runtime that holds a different token. /shutdown also requires that token, so
# a pre-started or leftover listener makes the shell exit. Free the port and
# let the shell spawn the runtime.
prepare_desktop_runtime_port() {
  if ! curl -sf "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
    return 0
  fi
  log "释放 8765 上的旧运行时（令牌与本次桌面壳不一致，壳无法回收）"
  local pids
  pids="$(lsof -tiTCP:8765 -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -n "$pids" ]]; then
    # shellcheck disable=SC2086
    kill $pids 2>/dev/null || true
    sleep 0.3
    # shellcheck disable=SC2086
    kill -9 $pids 2>/dev/null || true
  fi
}

ensure_runtime() {
  if curl -sf "http://127.0.0.1:8765/health" >/dev/null 2>&1; then
    log "Runtime 已在 8765 运行，跳过启动"
    return 0
  fi

  local venv_py="${ROOT}/runtime/.venv/bin/python"
  local venv_uv="${ROOT}/runtime/.venv/bin/uvicorn"
  if [[ ! -x "$venv_uv" ]]; then
    echo "未找到 ${venv_uv}，请先：cd runtime && python3 -m venv .venv && .venv/bin/pip install -e '.[dev]'" >&2
    exit 1
  fi

  log "启动 Runtime → http://127.0.0.1:8765"
  (
    cd "${ROOT}/runtime"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    exec uvicorn office_agent.app:app --app-dir src --host 127.0.0.1 --port 8765 \
      --reload --reload-dir src
  ) >"${STATE_DIR}/runtime.log" 2>&1 &
  echo $! >"${STATE_DIR}/runtime.pid"
  wait_http "http://127.0.0.1:8765/health" "Runtime" 60
}

ensure_vite() {
  if curl -sf "http://127.0.0.1:1420/" >/dev/null 2>&1; then
    log "Vite 已在 1420 运行，跳过启动"
    return 0
  fi

  if [[ ! -d "${ROOT}/apps/desktop/node_modules" ]]; then
    log "安装前端依赖…"
    (cd "${ROOT}/apps/desktop" && npm install)
  fi

  log "启动 Vite → http://127.0.0.1:1420"
  (
    cd "${ROOT}/apps/desktop"
    exec npx vite --host 127.0.0.1 --port 1420
  ) >"${STATE_DIR}/vite.log" 2>&1 &
  echo $! >"${STATE_DIR}/vite.pid"
  wait_http "http://127.0.0.1:1420/" "Vite" 60
}

start_tauri() {
  if [[ -f "${HOME}/.cargo/env" ]]; then
    # shellcheck disable=SC1091
    source "${HOME}/.cargo/env"
  fi
  if ! command -v cargo >/dev/null 2>&1; then
    echo "未找到 cargo。可改用：./scripts/dev.sh --web" >&2
    exit 1
  fi
  # tauri.conf.json bundles resources/NOTICE; stage from repo root before cargo.
  bash "${ROOT}/scripts/stage_notice.sh"
  log "启动 Tauri 桌面壳（首次编译较慢）…"
  log "日志：Runtime → ${STATE_DIR}/runtime.log | Vite → ${STATE_DIR}/vite.log"
  log "停止：./scripts/dev-stop.sh"
  cd "${ROOT}/apps/desktop"
  exec npm run tauri -- dev
}

if [[ "$MODE" == "desktop" ]]; then
  prepare_desktop_runtime_port
else
  ensure_runtime
fi

if [[ "$MODE" == "runtime" ]]; then
  log "仅 Runtime 模式，完成。日志：${STATE_DIR}/runtime.log"
  exit 0
fi

ensure_vite

if [[ "$MODE" == "web" ]]; then
  log "浏览器模式就绪：打开 http://127.0.0.1:1420/"
  log "工作区可粘贴绝对路径；停止：./scripts/dev-stop.sh"
  if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:1420/" || true
  fi
  # 前台挂住，Ctrl+C 时尽量清理本脚本拉起的子进程
  trap 'log "收到中断…"; "'"${ROOT}/scripts/dev-stop.sh"'" || true; exit 0' INT TERM
  log "前台等待中（Ctrl+C 停止）…"
  while true; do sleep 3600; done
fi

start_tauri
