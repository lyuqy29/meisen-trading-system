#!/usr/bin/env bash
# 溜溜交易手册 —— 一键启动
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8777}"

find_python() {
  if [ -n "${DSH_PYTHON:-}" ] && [ -x "$DSH_PYTHON" ]; then echo "$DSH_PYTHON"; return; fi
  local bundled="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/primary-runtime/dependencies/python/bin/python3"
  if [ -x "$bundled" ]; then echo "$bundled"; return; fi
  for c in python3 /usr/local/bin/python3 /opt/homebrew/bin/python3; do
    if command -v "$c" >/dev/null 2>&1; then echo "$c"; return; fi
  done
  echo ""
}

PY="$(find_python)"
if [ -z "$PY" ]; then
  echo "找不到可用的 Python 3，请设置 DSH_PYTHON 指向 python3" >&2
  exit 1
fi

echo "溜溜交易手册"
echo "  Python: $PY"
echo "  地址:   http://127.0.0.1:$PORT"
echo "  (Ctrl+C 停止)"
exec env PORT="$PORT" "$PY" server.py
