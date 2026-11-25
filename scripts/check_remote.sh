#!/usr/bin/env bash
# 检查 GitHub 远端凭据：是账号级 key 还是仓库 Deploy key，以及是否有写权限
# 用法: bash scripts/check_remote.sh [owner/repo]
set -uo pipefail
cd "$(dirname "$0")/.."
REPO="${1:-lyuqy29/meisen-trading-system}"
KEY="$(cd .. && pwd)/.deploy/id_ed25519"
SSH_CMD="ssh -i $KEY -o IdentitiesOnly=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10"

if [ ! -f "$KEY" ]; then echo "❌ 缺少私钥 $KEY" >&2; exit 1; fi

echo "私钥指纹: $(/usr/bin/ssh-keygen -lf "$KEY.pub" | awk '{print $2}')"
echo

echo "① 认证身份"
msg=$($SSH_CMD -T git@github.com 2>&1 | grep -v "Warning: Permanently" || true)
ident=$(printf '%s' "$msg" | sed -n 's/.*Hi \([^!]*\)!.*/\1/p' | head -1)
if [ -z "$ident" ]; then
  echo "   ❌ 认证失败：$(printf '%s' "$msg" | tail -2 | tr '\n' ' ')"
  exit 2
elif [[ "$ident" == */* ]]; then
  echo "   ✅ 仓库级 Deploy Key（$ident）—— 仅对该仓库有效"
else
  echo "   ⚠️  账号级 SSH Key（$ident）—— 对该账号下所有仓库有效"
fi

echo
echo "② 写权限（git-receive-pack on $REPO）"
out=$($SSH_CMD git@github.com "git-receive-pack '$REPO.git'" 2>&1 || true)
if printf '%s' "$out" | grep -q "refs/heads/"; then
  echo "   ✅ 有写权限，可直接 push"
elif printf '%s' "$out" | grep -qi "write access\|denied\|not authorized"; then
  echo "   ❌ 只读或无权限：$(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
  echo "      去 https://github.com/$REPO/settings/keys 勾选 Allow write access"
  exit 3
else
  echo "   ❔ 无法判断：$(printf '%s' "$out" | tail -2 | tr '\n' ' ')"
  exit 4
fi
