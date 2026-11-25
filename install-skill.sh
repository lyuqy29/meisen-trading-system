#!/usr/bin/env bash
# 梅森交易体系 · skill 安装器（macOS / Linux）
#
# 用法：
#   bash install-skill.sh                # 装到用户级 ${DSH_HOME:-~/.dsh}/skills
#   bash install-skill.sh --project      # 装到当前项目 ./.dsh/skills
#   bash install-skill.sh --force        # 覆盖已安装版本
#   bash install-skill.sh --uninstall    # 卸载
set -euo pipefail

NAME="meisen-trading-system"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

usage() {
  cat <<EOF
梅森交易体系 · skill 安装器

用法: bash install-skill.sh [选项]

选项:
  --project      安装到当前项目的 .dsh/skills/（仅该项目生效）
  --force, -f    覆盖已存在的安装
  --uninstall    卸载
  -h, --help     显示帮助

默认安装到: \${DSH_HOME:-~/.dsh}/skills/$NAME
EOF
}

MODE="user"
FORCE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --project) MODE="project" ;;
    --force|-f) FORCE=1 ;;
    --uninstall) MODE="uninstall" ;;
    -h|--help) usage; exit 0 ;;
    *) echo "未知参数: $1"; usage; exit 1 ;;
  esac
  shift
done

if [ "$MODE" = "project" ]; then
  DEST="$(pwd)/.dsh/skills/$NAME"
else
  DEST="${DSH_HOME:-$HOME/.dsh}/skills/$NAME"
fi

if [ "$MODE" = "uninstall" ]; then
  rm -rf "$DEST"
  echo "已卸载: $DEST"
  exit 0
fi

if [ -e "$DEST" ] && [ "$FORCE" -ne 1 ]; then
  echo "目标已存在: $DEST"
  echo "使用 --force 覆盖，或先 --uninstall 卸载。"
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
rm -rf "$DEST"
cp -R "$SRC" "$DEST"
rm -f "$DEST/install-skill.sh" "$DEST/install-skill.ps1"
echo "已安装到: $DEST"
echo "在 DSH 中运行 /skills 或重启会话即可看到 $NAME。"
