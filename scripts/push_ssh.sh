#!/usr/bin/env bash
# 用 Deploy Key 推送（本机 git 不可用，走 dulwich）
# 用法: bash scripts/push_ssh.sh
set -euo pipefail
cd "$(dirname "$0")/.."
KEY="$(cd .. && pwd)/.deploy/id_ed25519"
if [ ! -f "$KEY" ]; then
  echo "缺少私钥: $KEY" >&2
  exit 1
fi
PY="${PY:-python3}"
export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
echo "检查 SSH 认证…"
if ! $GIT_SSH_COMMAND -T git@github.com 2>&1 | grep -q "successfully authenticated"; then
  echo "❌ 公钥尚未授权。请把下面这段加到 https://github.com/settings/keys ：" >&2
  cat "$KEY.pub" >&2
  exit 2
fi
echo "✅ SSH 认证通过"
"$PY" scripts/git.py push main
