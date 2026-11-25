#!/usr/bin/env python3
"""把「账号级 SSH Key」切换成「仓库级 Deploy Key」（write access）。

安全顺序：先加 Deploy Key → 删账号级 Key（避免中途失去推送权限）。

凭据：export GH_TOKEN=ghp_xxx
  - classic token 需要 `repo` + `admin:public_key` 范围
  - fine-grained token 需要该仓库 Administration: Read and write，
    以及账号级 SSH keys 的读写（用于删除账号 key）

用法：
    python3 scripts/switch_to_deploy_key.py --dry-run
    python3 scripts/switch_to_deploy_key.py
    python3 scripts/switch_to_deploy_key.py --keep-account-key   # 只加 deploy key，不删账号 key
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PUB = Path(os.environ.get("DEPLOY_PUBKEY", str(ROOT.parent / ".deploy" / "id_ed25519.pub")))
API = "https://api.github.com"


def token() -> str | None:
    return os.environ.get("GH_TOKEN") or os.environ.get("GIT_TOKEN")


def api(method: str, path: str, tok: str, payload: dict | None = None, allow: tuple[int, ...] = ()) -> tuple[int, dict | list]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method)
    req.add_header("Authorization", f"Bearer {tok}")
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "meisen-deploy-key-switch")
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read().decode()
            return r.status, json.loads(body) if body.strip() else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        if e.code in allow:
            return e.code, {}
        raise SystemExit(f"API {method} {path} 失败: {e.code} {body[:300]}")


def fingerprint(pub: Path) -> str:
    out = subprocess.run(["/usr/bin/ssh-keygen", "-lf", str(pub)], capture_output=True, text=True).stdout
    # "256 SHA256:xxxx comment (ED25519)"
    return out.split()[1] if out else ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default=os.environ.get("GH_OWNER", "lyuqy29"))
    ap.add_argument("--repo", default=os.environ.get("GH_REPO", "meisen-trading-system"))
    ap.add_argument("--title", default="meisen-skill-deploy")
    ap.add_argument("--keep-account-key", action="store_true", help="只加 deploy key，不删除账号级 key")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not PUB.exists():
        raise SystemExit(f"找不到公钥: {PUB}")
    pub = PUB.read_text().strip()
    fp = fingerprint(PUB)
    print(f"公钥指纹: {fp}")

    tok = token()
    if not tok:
        print("缺少凭据：export GH_TOKEN=...（需 repo / admin:public_key 范围）")
        print("或者手动两步：")
        print(f"  1) 加 Deploy Key（勾 Allow write access）: https://github.com/{args.owner}/{args.repo}/settings/keys")
        print(f"  2) 删除账号级 Key: https://github.com/settings/keys  ← 找到指纹 {fp} 那条")
        return 2

    code, me = api("GET", "/user", tok)
    print(f"已认证：{me.get('login')}")

    # 现有 deploy keys
    code, keys = api("GET", f"/repos/{args.owner}/{args.repo}/keys", tok)
    existing = [k for k in keys if fp and fp in (k.get("key", "") or "")] if isinstance(keys, list) else []
    keys_list = keys if isinstance(keys, list) else []
    same = [k for k in keys_list if k.get("key", "").split()[:2] == pub.split()[:2]]
    print(f"仓库已有 deploy keys: {len(keys_list)}，其中匹配本公钥: {len(same)}")

    if same:
        k = same[0]
        print(f"已存在 Deploy Key id={k['id']} read_only={k.get('read_only')}")
        if k.get("read_only"):
            print("⚠️  该 key 是只读，需要删除后重新添加（API 不支持原地改权限）")
    else:
        print(f"[plan] POST /repos/{args.owner}/{args.repo}/keys  read_only=False")
        if not args.dry_run:
            code, k = api("POST", f"/repos/{args.owner}/{args.repo}/keys", tok, {
                "title": args.title, "key": pub, "read_only": False})
            print(f"✅ 已添加 Deploy Key id={k.get('id')} read_only={k.get('read_only')}")

    # 账号级 key
    code, ukeys = api("GET", "/user/keys", tok, allow=(403, 404))
    ulist = ukeys if isinstance(ukeys, list) else []
    umatch = [k for k in ulist if k.get("key", "").split()[:2] == pub.split()[:2]]
    print(f"账号级 keys: {len(ulist)}，其中匹配本公钥: {len(umatch)}")
    for k in umatch:
        print(f"   - id={k['id']} title={k.get('title')} 指纹={k.get('fingerprint')}")
        if not args.dry_run and not args.keep_account_key:
            api("DELETE", f"/user/keys/{k['id']}", tok)
            print(f"   ✅ 已删除账号级 key id={k['id']}")

    if args.dry_run:
        print("\n[dry-run] 未做任何修改")
        return 0

    print("\n验证：bash scripts/check_remote.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
