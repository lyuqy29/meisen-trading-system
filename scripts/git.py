#!/usr/bin/env python3
"""极简 git 助手（基于 dulwich）。

背景：这台 macOS 的 /usr/bin/git 依赖缺失的 Xcode Command Line Tools，
`git` 命令不可用；本脚本用纯 Python 的 dulwich 实现常用操作。

用法：
    python3 scripts/git.py status
    python3 scripts/git.py log [条数]
    python3 scripts/git.py commit "提交信息"
    python3 scripts/git.py remote <url>          # 设置 origin
    python3 scripts/git.py push [分支]           # 需要凭据，见下

push 凭据（HTTPS）：
    export GIT_USER=你的用户名
    export GIT_TOKEN=你的 Personal Access Token
    python3 scripts/git.py push
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from dulwich import porcelain
from dulwich.repo import Repo

ROOT = Path(__file__).resolve().parent.parent
NAME = os.environ.get("GIT_AUTHOR_NAME", "quyang")
EMAIL = os.environ.get("GIT_AUTHOR_EMAIL", "quyang@users.noreply.github.com")


def _repo() -> Repo:
    if not (ROOT / ".git").exists():
        raise SystemExit("当前目录不是 git 仓库（缺少 .git）")
    return Repo(str(ROOT))


def _ident() -> bytes:
    return b"%s <%s>" % (NAME.encode(), EMAIL.encode())


def cmd_status(_args: list[str]) -> int:
    repo = _repo()
    st = porcelain.status(repo)
    staged = [f for f in st.staged["add"] + st.staged["modify"] + st.staged["delete"]]
    print(f"分支: {_branch(repo)}")
    if staged:
        print(f"已暂存 ({len(staged)}):")
        for f in staged[:50]:
            print("  +", f.decode() if isinstance(f, bytes) else f)
    if st.unstaged:
        print(f"未暂存 ({len(st.unstaged)}):")
        for f in st.unstaged[:50]:
            print("  M", f.decode() if isinstance(f, bytes) else f)
    if st.untracked:
        print(f"未跟踪 ({len(st.untracked)}):")
        for f in st.untracked[:50]:
            print("  ?", f.decode() if isinstance(f, bytes) else f)
    if not (staged or st.unstaged or st.untracked):
        print("工作区干净 ✅")
    return 0


def cmd_log(args: list[str]) -> int:
    repo = _repo()
    n = int(args[0]) if args and args[0].isdigit() else 10
    sha = repo.head()
    for _ in range(n):
        c = repo[sha]
        first = c.message.decode(errors="replace").strip().splitlines()[0]
        print(f"{sha.decode()[:8]}  {c.author.decode(errors='replace')}")
        print(f"          {first}")
        if not c.parents:
            break
        sha = c.parents[0]
    return 0


def cmd_commit(args: list[str]) -> int:
    if not args:
        raise SystemExit('用法: python3 scripts/git.py commit "提交信息"')
    msg = args[0]
    repo = _repo()
    porcelain.add(repo, paths=["."])
    sha = porcelain.commit(repo, message=msg.encode(), author=_ident(), committer=_ident())
    print(f"✅ 已提交 {sha.decode()[:8]}  {msg}")
    return 0


def cmd_remote(args: list[str]) -> int:
    if not args:
        repo = _repo()
        cfg = repo.get_config()
        try:
            url = cfg.get(("remote", "origin"), "url").decode()
            print("origin:", url)
        except KeyError:
            print("未设置 origin")
        return 0
    repo = _repo()
    cfg = repo.get_config()
    cfg.set(("remote", "origin"), "url", args[0].encode())
    cfg.set(("remote", "origin"), "fetch", b"+refs/heads/*:refs/remotes/origin/*")
    cfg.write_to_path()
    print("origin →", args[0])
    return 0


def cmd_push(args: list[str]) -> int:
    repo = _repo()
    branch = args[0] if args else _branch(repo)
    user, token = os.environ.get("GIT_USER"), os.environ.get("GIT_TOKEN")
    refspec = f"refs/heads/{branch}:refs/heads/{branch}".encode()
    try:
        porcelain.push(repo, refspecs=[refspec], username=user, password=token)
    except NotImplementedError:
        print("❌ 该远端协议（如 SSH）需要 paramiko：pip install 'dulwich[ssh]'")
        return 2
    except Exception as e:  # noqa: BLE001
        print(f"❌ push 失败: {type(e).__name__}: {e}")
        print("提示：HTTPS 需要 GIT_USER / GIT_TOKEN；SSH 需要 paramiko 与可用私钥。")
        return 1
    print(f"✅ 已推送 {branch}")
    return 0


def _branch(repo: Repo) -> str:
    head = repo.refs.read_ref(b"HEAD")
    if head.startswith(b"ref: refs/heads/"):
        return head[len(b"ref: refs/heads/"):].decode()
    return "main"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmds = {"status": cmd_status, "log": cmd_log, "commit": cmd_commit,
            "remote": cmd_remote, "push": cmd_push}
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return 0
    fn = cmds.get(argv[0])
    if not fn:
        print(f"未知命令: {argv[0]}（可选: {', '.join(cmds)}）")
        return 2
    return fn(argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
