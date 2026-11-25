"""交易计划触发器检查：实时行情 → 是否满足买点/否决条件。

用法: python3 tools/ms_check.py
"""
import json, urllib.request

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/131.0 Safari/537.36",
      "Referer": "https://gu.qq.com/"}
Q = "https://qt.gtimg.cn/q="

# 计划参数（与 plans/2026-11-25-交易计划.md 对应）
VETO = {"sh000001": ("上证", 3476.7), "sz399006": ("创业板", 2188.4), "sh000688": ("科创50", 1177.6)}
TRIG = {
    "sh601985": ("中国核电", "防御·当弱不弱", {"min": 9.90, "ma10": 9.83, "buy_above": None, "stop": 9.64}),
    "sh688172": ("燕东微", "进攻·回踩确认", {"buy_above": 36.50, "hold_above": 34.20, "stop": 32.80}),
    "sh688981": ("中芯国际", "条件单·等回踩", {"zone": (116.0, 118.0), "stop": 110.70}),
}


def quote(syms):
    raw = urllib.request.urlopen(urllib.request.Request(Q + ",".join(syms), headers=UA), timeout=15).read().decode("gbk")
    out = {}
    for line in raw.strip().split(";"):
        if "=" not in line:
            continue
        body = line.split("=", 1)[1].strip().strip('"')
        f = body.split("~")
        if len(f) < 40:
            continue
        out[line.split("=")[0].split("_")[-1]] = {
            "name": f[1], "price": float(f[3]), "prev": float(f[4]), "open": float(f[5]),
            "high": float(f[33]) if f[33] else 0, "low": float(f[34]) if f[34] else 0,
            "chg": float(f[32]) if f[32] else 0, "vol": float(f[36]) if f[36] else 0,
            "time": f[30],
        }
    return out


def main():
    syms = list(VETO) + list(TRIG)
    q = quote(syms)
    print("=== 行情 ===")
    for s in syms:
        d = q.get(s)
        if d:
            print(f"{d['name']:10s} {d['price']:>9.2f} {d['chg']:+6.2f}%  开{d['open']:.2f} 高{d['high']:.2f} 低{d['low']:.2f}  {d['time']}")
    print("\n=== 否决线（跌破即全部取消）===")
    veto_hit = False
    for s, (name, line) in VETO.items():
        d = q.get(s)
        if not d:
            continue
        ok = d["price"] > line
        veto_hit |= not ok
        print(f"{'✅' if ok else '🚨'} {name:8s} {d['price']:.2f} vs {line}  距离 {(d['price']/line-1)*100:+.2f}%")
    print("\n=== 个股触发 ===")
    for s, (name, kind, rule) in TRIG.items():
        d = q.get(s)
        if not d:
            continue
        p, msg = d["price"], []
        if "min" in rule:
            msg.append(f"✅ 未过度低开（≥{rule['min']}），可按计划试仓" if p >= rule["min"]
                       else f"🚨 低开超阈值 {rule['min']} → 放弃本笔")
        if "buy_above" in rule and rule["buy_above"]:
            msg.append("✅ 触发买点" if p >= rule["buy_above"] else f"⏳ 未达 {rule['buy_above']}")
        if "hold_above" in rule:
            msg.append(f"{'✅' if p > rule['hold_above'] else '🚨'} 支撑 {rule['hold_above']}")
        if "zone" in rule:
            lo, hi = rule["zone"]
            msg.append("✅ 进入回踩区，可试仓" if lo <= p <= hi else f"⏳ 等回踩 {lo}-{hi}")
        if p < rule["stop"]:
            msg.append("🚨 已破止损")
        print(f"{name:8s} {p:>8.2f} [{kind}] " + " | ".join(msg))
    print("\n结论：" + ("🚨 指数跌破否决线 → 全部计划取消，只看不做" if veto_hit else "否决线未破 → 按计划顺序执行（A→C→B）"))


if __name__ == "__main__":
    main()
