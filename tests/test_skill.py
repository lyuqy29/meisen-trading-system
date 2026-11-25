#!/usr/bin/env python3
"""离线校验 skill 结构完整性（不联网）。

检查项：
1. SKILL.md frontmatter 完整（name/description/whenToUse），name 与目录名一致
2. references/ 下每个文档有且仅有一个 H1
3. 所有 `xxx.md` 交叉引用都能解析到真实文件
4. 无遗留占位符（TODO/待补充/待定）
5. assets/ 模板齐全
6. scripts/ 可 import（语法正确，不触发网络）

用法：python3 tests/test_skill.py
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
errors: list[str] = []
checks = 0


def check(cond: bool, msg: str) -> None:
    global checks
    checks += 1
    if not cond:
        errors.append(msg)


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    out = {}
    for line in text[3:end].strip().splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            out[k.strip()] = v.strip()
    return out


def main() -> int:
    # 1. frontmatter
    skill = ROOT / "SKILL.md"
    check(skill.exists(), "缺少 SKILL.md")
    text = skill.read_text(encoding="utf-8")
    fm = parse_frontmatter(text)
    for key in ("name", "description", "whenToUse"):
        check(bool(fm.get(key)), f"SKILL.md frontmatter 缺少 {key}")
    check(fm.get("name") == ROOT.name, f"skill name({fm.get('name')}) 与目录名({ROOT.name})不一致")
    check(len(fm.get("description", "")) <= 1024, "description 超过 1024 字符")

    # 2. 每个 reference 一个 H1
    refs = sorted((ROOT / "references").glob("*.md"))
    check(len(refs) >= 15, f"references 数量偏少: {len(refs)}")
    for p in refs:
        h1 = [l for l in p.read_text(encoding="utf-8").splitlines() if l.startswith("# ")]
        check(len(h1) == 1, f"{p.name} 应恰好有一个 H1，实际 {len(h1)}")
        check(p.stat().st_size > 500, f"{p.name} 内容过短")

    # 3. 交叉引用可解析
    files = {p.name for p in refs} | {p.name for p in (ROOT / "assets").glob("*.md")} | {"SKILL.md", "README.md"}
    for p in refs + [skill]:
        body = p.read_text(encoding="utf-8")
        for m in re.findall(r"`([0-9a-zA-Z\-]+\.md)`", body):
            check(m in files, f"{p.name} 引用了不存在的文件: {m}")

    # 4. 占位符
    for p in refs + list((ROOT / "assets").glob("*.md")):
        body = p.read_text(encoding="utf-8")
        for bad in ("TODO", "待补充", "待定", "XXX"):
            check(bad not in body, f"{p.name} 残留占位符: {bad}")

    # 5. assets
    for name in ("cheatsheet.md", "trade-plan.md", "position-sheet.md", "review.md"):
        check((ROOT / "assets" / name).exists(), f"缺少 assets/{name}")

    # 6. scripts 语法/导入（不联网）
    for name in ("ms_data.py", "ms_check.py"):
        path = ROOT / "scripts" / name
        check(path.exists(), f"缺少 scripts/{name}")
        spec = importlib.util.spec_from_file_location(name[:-3], path)
        try:
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)  # type: ignore[union-attr]
            check(True, f"{name} 导入成功")
        except Exception as e:  # noqa: BLE001
            errors.append(f"{name} 导入失败: {type(e).__name__}: {e}")

    # 输出
    print(f"共执行 {checks} 项检查")
    if errors:
        print(f"\n❌ 失败 {len(errors)} 项:")
        for e in errors:
            print("  -", e)
        return 1
    print("✅ 全部通过：SKILL.md、references、assets、scripts 结构完整")
    return 0


if __name__ == "__main__":
    sys.exit(main())
