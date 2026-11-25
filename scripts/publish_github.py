#!/usr/bin/env python3
"""把本仓库发布到 GitHub（无需可用的 git 命令）。

工作方式：
1. 用 GitHub REST API 确认/创建仓库（api.github.com 可达）
2. 用 dulwich 走 HTTPS 推送本地提交历史（保留完整 commit）

凭据（二选一）：
    export GH_TOKEN=ghp_xxx          # classic token，勾选 repo；或 fine-grained 勾选 Contents: RW + Administration: RW
    # 或
    export GIT_USER=lyuqy29 GIT_TOKEN=ghp_xxx

用法：
    python3 scripts/publish_github.py --dry-run
    python3 scripts/publish_github.py
    python3 scripts/publish_github.py --owner lyuqy29 --repo meisen-trading-system --private
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
UA = "meisen-trading-system-publisher"


def _token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GIT_TOKEN")


def api(method: str, path: str, token: str, payload: dict | None = None, allow: tuple[int, ...] = ()) -> tuple[int, dict]:
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", UA)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode() or "{}"
            return r.status, json.loads(body)
    except urllib.error.HTTPError as e:
        body = e.read().decode() or "{}"
        if e.code in allow:
            return e.code, json.loads(body) if body.strip().startswith("{") else {}
        raise SystemExit(f"API {method} {path} 失败: {e.code} {body[:300]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default=os.environ.get("GH_OWNER", "lyuqy29"))
    ap.add_argument("--repo", default=os.environ.get("GH_REPO", "meisen-trading-system"))
    ap.add_argument("--private", action="store_true", help="创建为私有仓库")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = _token()
    if not token:
        print("缺少凭据：请设置 GH_TOKEN（或 GIT_USER + GIT_TOKEN）后重试。")
        print("获取：GitHub → Settings → Developer settings → Personal access tokens（勾选 repo）")
        return 2

    # 1. 校验身份
    code, me = api("GET", "/user", token)
    login = me.get("login", "?")
    print(f"已认证：{login}")
    owner = args.owner or login

    # 2. 仓库是否存在
    code, repo_info = api("GET", f"/repos/{owner}/{args.repo}", token, allow=(404,))
    exists = code == 200
    print(f"仓库 {owner}/{args.repo}: {'已存在' if exists else '不存在'}")
    if exists:
        clone = repo_info.get("clone_url")
        branch = repo_info.get("default_branch", "main")
    else:
        clone = f"https://github.com/{owner}/{args.repo}.git"
        branch = "main"

    if args.dry_run:
        repo = Repo(str(ROOT))
        n = len(porcelain.log(repo, max_entries=100)) if False else 0
        head = repo.head().decode()[:8]
        print(f"[dry-run] 将推送到 {clone}（HEAD={head}），创建动作：{'无' if exists else 'POST /user/repos'}")
        return 0

    # 3. 不存在则创建
    if not exists:
        private = bool(args.private)
        code, info = api("POST", "/user/repos" if owner == login else f"/orgs/{owner}/repos", token, {
            "name": args.repo,
            "description": "梅森交易体系 skill：19 讲课程 → 17 模块方法论 + 数据/校验脚本",
            "private": private,
            "auto_init": False,
        })
        print(f"已创建仓库：{info.get('html_url')}")
        clone = info.get("clone_url", clone)

    # 4. dulwich 推送（保留本地提交历史）
    repo = Repo(str(ROOT))
    cfg = repo.get_config()
    cfg.set(("remote", "origin"), "url", clone.encode())
    cfg.set(("remote", "origin"), "fetch", b"+refs/heads/*:refs/remotes/origin/*")
    cfg.write_to_path()

    refspec = f"refs/heads/{branch}:refs/heads/{branch}".encode()
    print(f"推送 {branch} → {clone} …")
    try:
        porcelain.push(repo, remote_location=clone, refspecs=[refspec],
                       username=os.environ.get("GIT_USER", login), password=token)
    except Exception as e:  # noqa: BLE001
        print(f"推送失败：{type(e).__name__}: {e}")
        print("可改为：先 `git.py remote <url>`，再设置 GIT_USER/GIT_TOKEN 后 `git.py push`")
        return 1
    print(f"✅ 已推送：https://github.com/{owner}/{args.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
