#!/usr/bin/env bash
# Probe whether this Linux host can isolate script processes (unprivileged net ns).
set -euo pipefail
if ! command -v unshare >/dev/null 2>&1; then
  echo "unshare not found; install util-linux" >&2
  exit 1
fi
if unshare --net -- true; then
  echo "ok: unshare --net works; local deployment script isolation is available"
else
  echo "unshare --net failed; enable user namespaces or run scripts will be denied" >&2
  exit 1
fi
