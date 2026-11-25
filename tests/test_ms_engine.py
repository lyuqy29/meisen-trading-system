#!/usr/bin/env python3
"""ms_engine 离线单测（不联网）：用合成 K 线验证判定口径与计划生成。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "dashboard"))

import ms_engine as ms  # noqa: E402

fails = []


def check(cond: bool, msg: str) -> None:
    if not cond:
        fails.append(msg)


def synth(n: int, start: float, step: float, vol: float = 1e6) -> list[dict]:
    rows, px = [], start
    for i in range(n):
        px += step
        rows.append({"date": f"2026-01-{i + 1:02d}", "open": px, "close": px,
                     "high": px * 1.01, "low": px * 0.99, "vol": vol})
    return rows


# 1) 均线三态
check(ms.ma_state([r["close"] for r in synth(30, 10, 0.2)]) == "多头排列", "上涨序列应为多头排列")
check(ms.ma_state([r["close"] for r in synth(30, 20, -0.2)]) == "空头排列", "下跌序列应为空头排列")

# 2) 三天不新低
rows = synth(20, 10, -0.1)
rows[-3:] = [dict(r, low=r["low"] + 2) for r in rows[-3:]]
s = ms.summarize(rows)
check(s["no_new_low"] >= 3, f"应识别三天不新低，实际 {s['no_new_low']}")

# 3) 计划生成（脱网）
ms.stock = lambda code: {  # type: ignore[assignment]
    "code": code, "name": "测试股", "state": "多头排列", "dist_ma20": 1.5,
    "zone": "回踩区 · 可试仓", "signals": ["回踩买点"], "close": 10.0,
    "high20": 10.5, "low20": 9.2, "stop": 9.4, "stop_struct": 9.4, "stop_line": 8.5,
    "cap": "1/5", "cap_note": "可试仓",
}
ms.plans_dir = lambda: str(ROOT / "plans")  # type: ignore[assignment]
r = ms.make_plan("600000", 1_000_000, 20, 10.0, 9.4, "回踩")
check(r["row"]["shares"] == 20000, f"股数应 20000，实际 {r['row']['shares']}")
check(abs(r["row"]["loss"] - 12000) < 1, f"最大亏损应 12000，实际 {r['row']['loss']}")
check("| 测试股 600000 | 回踩 | 10.00 | 20% |" in r["markdown"], "表格行格式不对")
check(Path(r["path"]).exists(), "计划文件未写入")
Path(r["path"]).unlink(missing_ok=True)

# 4) 复盘统计（脱网）
ms.REVIEWS = "/tmp/_ms_reviews_test.json"
Path(ms.REVIEWS).write_text("[]", encoding="utf-8")
ms.add_review({"code": "600000", "name": "A", "date": "2026-11-01", "pl_pct": 5,
               "layers": {"时机": "对", "方向": "对", "位置": "对", "执行": "对"}, "tags": []})
ms.add_review({"code": "600001", "name": "B", "date": "2026-11-02", "pl_pct": -3,
               "layers": {"时机": "错", "方向": "对", "位置": "错", "执行": "错"},
               "tags": ["时机-追高"]})
st = ms.reviews()["stats"]
check(st["total"] == 2, "复盘应有 2 条")
check(st["win_rate"] == 50.0, f"胜率应 50%，实际 {st['win_rate']}")
check(st["by_tag"][0]["tag"] == "时机-追高", "标签统计不对")
check(st["by_layer"]["时机"]["错"] == 1, "四层归因统计不对")
Path(ms.REVIEWS).unlink(missing_ok=True)

if fails:
    print("❌ 失败:")
    for f in fails:
        print("  -", f)
    sys.exit(1)
print("✅ ms_engine 离线单测通过（均线/三天不新低/计划生成/复盘统计）")
