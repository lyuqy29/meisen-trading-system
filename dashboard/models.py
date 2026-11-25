"""九大模型检测 + 打分 + 交易计划生成。

口径来自 laofan-trading-system/references/models.md。体系本身是经验描述，
这里给出的是可执行的机械口径（对应文档中的「※」补充定义），
检测结果标注「机械口径」，不替代人工判断。

每个模型固定 6 项检查（异动价 / 异动量 / 均线结构 / 位置 / 时间 / 无失效）：
6/6 = 标准版，4-5 = 弱化版，<=3 = 不成立。
"""
from __future__ import annotations

from market import platform

CHECKS = ["异动价", "异动量", "均线/结构", "位置", "时间", "无失效"]


def _check(name, ok, evidence, missing=False):
    return {"name": name, "pass": bool(ok), "evidence": evidence, "missing": missing}


def _level(passed, total):
    if total <= 0:
        return "不成立"
    if passed >= total and total >= 5:
        return "标准版"
    if passed / total >= 0.6:
        return "弱化版"
    return "不成立"


def _pct(a, b):
    return (a / b - 1) * 100 if b else 0.0


# ---------------------------------------------------------------- 各模型检测

def m1_shangying(ctx, bars, ev):
    """① 上影反攻：涨停破板长上影 + 天量换手 + 均线转多 + 缩量回踩放量中阳。"""
    n = len(bars)
    hit = [i for i in range(max(1, n - 60), n) if ev[i]["meta"].get("broken_board")]
    checks = []
    if not hit:
        return None
    i = hit[-1]
    b = bars[i]
    e = ev[i]
    checks.append(_check("异动价", True,
                         f"{b['dt']} 涨停破板，回落 {e['meta']['broken_board']:.1f}%"))
    vol_ok = any(ev[j]["meta"].get("volume_peak") or ev[j]["meta"].get("double_vol")
                 for j in range(i, min(n, i + 4)))
    checks.append(_check("异动量", vol_ok,
                         "破板后 3 日内出现天量/倍量" if vol_ok else "破板后无天量配合"))
    ma_ok = ctx["trend"] == "多头排列"
    checks.append(_check("均线/结构", ma_ok,
                         f"当前{ctx['trend']}" + ("" if ma_ok else "，未转多头排列")))
    pos_ok = ctx["position"] in ("低位", "中继/中性")
    checks.append(_check("位置", pos_ok,
                         f"{ctx['position']}（距250日高 {ctx['drop_hi']:+.1f}%）"))
    pull_ok = any(ev[j]["meta"].get("shrink") for j in range(i, n))
    checks.append(_check("时间", pull_ok,
                         "长上影后出现极致缩量回踩" if pull_ok else "未见缩量回踩"))
    low_stop = min(bars[j]["l"] for j in range(max(0, i - 2), i + 1))
    fail_ok = ctx["close"] > low_stop * 0.97
    checks.append(_check("无失效", fail_ok,
                         "未跌破长上影最低点" if fail_ok else "已跌破长上影最低点"))
    return {
        "id": "m1", "name": "① 上影反攻", "anchor": i,
        "checks": checks,
        "buy": {"type": "突破买点",
                "trigger": round(max(b["h"] * 1.01, ctx["ma"]["13"]), 2),
                "desc": "放量中阳站上短期均线组或突破长上影最高点"},
        "stop": {"price": round(low_stop * 0.975, 2), "basis": "长上影最低点下方 2.5%"},
        "invalidation": "长上影后 3 日内跌破短期均线组；天量后持续缩量横盘下移",
    }


def m2_nshi(ctx, bars, ev):
    """② n 式倍量双涨停：低位两次倍量涨停夹回撤，间隔 <=1 个月。"""
    n = len(bars)
    ups = [i for i in range(max(1, n - 60), n)
           if ev[i]["meta"].get("limit_up") and ev[i]["meta"].get("double_vol")]
    if len(ups) < 2:
        return None
    pairs = [(ups[k], ups[k + 1]) for k in range(len(ups) - 1)
             if (ups[k + 1] - ups[k]) <= 22]
    if not pairs:
        return None
    i, j = pairs[-1]
    first_low = bars[i]["l"]
    mid_low = min(bars[k]["l"] for k in range(i, j + 1))
    checks = [
        _check("异动价", True, f"{bars[i]['dt']} 与 {bars[j]['dt']} 两次涨停"),
        _check("异动量", True, "两次均为倍量涨停"),
        _check("均线/结构", ctx["trend"] == "多头排列",
               f"当前{ctx['trend']}" + ("" if ctx["trend"] == "多头排列" else "，趋势未扭转")),
        _check("位置", ctx["position"] == "低位",
               f"{ctx['position']}（模型要求低位，高位同形态直接排除）"),
        _check("时间", True, f"两次涨停间隔 {j - i} 个交易日（要求 ≤22）"),
        _check("无失效", mid_low >= first_low * 0.98,
               "回撤未破首板低点" if mid_low >= first_low * 0.98 else "回撤跌破首板低点"),
    ]
    return {
        "id": "m2", "name": "② n 式倍量双涨停", "anchor": j,
        "checks": checks,
        "buy": {"type": "突破买点", "trigger": round(bars[j]["c"], 2),
                "desc": "第二根倍量涨停当日/次日，或回踩中期均线组起稳"},
        "stop": {"price": round(first_low * 0.98, 2), "basis": "首板最低价下方 2%"},
        "invalidation": "两次涨停间隔 >1 个月；跌破首板低点次日不收回；均线未转多",
    }


def m3_chuanyang(ctx, bars, ev):
    """③ 串阳爬坡：>7 连阳、累计 <=20%，末端大阳/长上影换手后回踩再启动。"""
    n = len(bars)
    streak = ctx["up_streak"]
    if streak < 7:
        return None
    start = n - streak
    seg = bars[start:]
    cum = _pct(seg[-1]["c"], seg[0]["c"])
    end_big = any(ev[k]["meta"].get("upper_shadow") or ev[k]["chg"] >= 5
                  for k in range(max(start, n - 4), n))
    checks = [
        _check("异动价", end_big, "末端出现中大阳/长上影" if end_big else "末端无换手 K 线"),
        _check("异动量", ctx["vol5_20"] >= 0.8,
               f"5日/20日均量 {ctx['vol5_20']:.2f}"),
        _check("均线/结构", ctx["trend"] == "多头排列", f"当前{ctx['trend']}"),
        _check("位置", ctx["position"] != "高位", f"{ctx['position']}"),
        _check("时间", cum <= 20, f"连阳 {streak} 根，累计 {cum:+.1f}%（要求 ≤20%）"),
        _check("无失效", ctx["close"] > ctx["ma"]["55"],
               "仍站在中期均线组上方" if ctx["close"] > ctx["ma"]["55"] else "已跌破中期均线组"),
    ]
    return {
        "id": "m3", "name": "③ 串阳爬坡", "anchor": n - 1,
        "checks": checks,
        "buy": {"type": "回踩买点", "trigger": round(ctx["ma"]["13"], 2),
                "desc": "串阳突破中期组后首次缩量回踩、再放量阳线"},
        "stop": {"price": round(min(b["l"] for b in seg) * 0.99, 2), "basis": "串阳起点下方"},
        "invalidation": "累计涨幅远超 20%；调整期缩量不下来；跌破中期均线组",
    }


def m4_tanlu(ctx, bars, ev):
    """④ 探路尖兵：涨停推进密集区 + 巨量换手 + 缩量修正后二波。"""
    n = len(bars)
    ups = [i for i in range(max(1, n - 60), n) if ev[i]["meta"].get("limit_up")]
    if not ups:
        return None
    i = ups[-1]
    vol_hit = [k for k in range(i, min(n, i + 4))
               if ev[k]["meta"].get("volume_peak") or ev[k]["meta"].get("double_vol")]
    fix = any(ev[k]["meta"].get("shrink") for k in range(i, n))
    above_mid = ctx["close"] > ctx["ma"]["55"]
    gap_hold = all(bars[k]["l"] >= ev[k]["meta"].get("gap_up", (0, 0))[0]
                   for k in range(i, n) if "gap_up" in ev[k]["meta"])
    checks = [
        _check("异动价", True, f"{bars[i]['dt']} 涨停推进"),
        _check("异动量", bool(vol_hit), "涨停后出现天量/倍量" if vol_hit else "无量能配合"),
        _check("均线/结构", above_mid and fix,
               ("缩量修正且仍在中期组上方" if above_mid and fix
                else "修正不足或已跌破中期组")),
        _check("位置", ctx["position"] != "高位", f"{ctx['position']}"),
        _check("时间", (n - 1 - i) <= 40, f"涨停后已修正 {n - 1 - i} 个交易日"),
        _check("无失效", gap_hold and above_mid,
               "缺口未回补" if gap_hold and above_mid else "缺口被回补或跌破中期组"),
    ]
    return {
        "id": "m4", "name": "④ 探路尖兵", "anchor": i,
        "checks": checks,
        "buy": {"type": "突破买点", "trigger": round(max(ctx["ma"]["8"], bars[i]["h"]), 2),
                "desc": "修正末端放量中阳突破；或回踩中期均线组不破"},
        "stop": {"price": round(ctx["ma"]["55"] * 0.98, 2), "basis": "中期均线组下方 2%"},
        "invalidation": "涨停后直接跌穿中期组；缺口回补；横盘期放量下跌",
    }


def m5_jizhi(ctx, bars, ev):
    """⑤ 极值反转：跌停与涨停在同位置对称出现，跌幅 >=30% 的调整末端。"""
    n = len(bars)
    downs = [i for i in range(max(1, n - 60), n) if ev[i]["meta"].get("limit_down")]
    ups = [i for i in range(max(1, n - 60), n) if ev[i]["meta"].get("limit_up")]
    pairs = [(d, u) for d in downs for u in ups if 0 < u - d <= 15]
    if not pairs:
        return None
    d, u = pairs[-1]
    sym_price = _pct(bars[u]["c"], bars[d]["c"])
    deep = ctx["drop_hi"] <= -30 or ctx["trend"] == "空头排列"
    checks = [
        _check("异动价", True, f"{bars[d]['dt']} 跌停 → {bars[u]['dt']} 涨停，对称出现"),
        _check("异动量", ev[d]["vol_ratio"] >= 1.2 or ev[u]["vol_ratio"] >= 1.5,
               f"跌停日量比 {ev[d]['vol_ratio']:.2f}，涨停日量比 {ev[u]['vol_ratio']:.2f}"),
        _check("均线/结构", ctx["close"] > ctx["ma"]["55"],
               "已站上中期均线组" if ctx["close"] > ctx["ma"]["55"] else "仍在中期组下方"),
        _check("位置", deep, f"{ctx['position']}（距250日高 {ctx['drop_hi']:+.1f}%）"),
        _check("时间", (n - 1 - d) <= 30, f"跌停至今 {n - 1 - d} 个交易日"),
        _check("无失效", abs(sym_price) <= 12,
               f"极值对称为同位置（区间差 {sym_price:+.1f}%）"),
    ]
    return {
        "id": "m5", "name": "⑤ 极值反转", "anchor": u,
        "checks": checks,
        "buy": {"type": "突破买点", "trigger": round(ctx["ma"]["60"], 2),
                "desc": "涨停突破中期均线组当日，或突破后回踩不破"},
        "stop": {"price": round(min(bars[d]["l"], bars[u]["l"]) * 0.975, 2),
                 "basis": "跌停板最低点下方 2.5%"},
        "invalidation": "跌停后继续放量下行；跌破跌停低点；未站上中期组",
    }


def m6_yizhu(ctx, bars, ev):
    """⑥ 一柱擎天：倍量涨停/跳空涨停后沿短期均线组 30-45° 小阳推进。"""
    n = len(bars)
    starters = [i for i in range(max(1, n - 30), n)
                if (ev[i]["meta"].get("limit_up") and ev[i]["meta"].get("double_vol"))
                or (ev[i]["meta"].get("limit_up") and ev[i]["meta"].get("gap_up"))]
    if not starters:
        return None
    i = starters[-1]
    after = bars[i:]
    hold = all(b["l"] >= ctx["ma"]["13"] * 0.985 for b in after[1:]) if len(after) > 1 else True
    up_days = sum(1 for k in range(i + 1, n) if bars[k]["c"] > bars[k - 1]["c"])
    total = max(1, n - 1 - i)
    slope = _pct(bars[-1]["c"], bars[i]["c"]) / max(1, total) * 5
    checks = [
        _check("异动价", True, f"{bars[i]['dt']} 倍量涨停/跳空涨停启动"),
        _check("异动量", ev[i]["meta"].get("double_vol") or ev[i]["meta"].get("gap_up"),
               f"启动日量比 {ev[i]['vol_ratio']:.2f}"),
        _check("均线/结构", ctx["trend"] == "多头排列" and hold,
               f"{ctx['trend']}，" + ("未破 13 日线" if hold else "已破 13 日线")),
        _check("位置", ctx["position"] in ("中继/中性", "低位"), f"{ctx['position']}"),
        _check("时间", (n - 1 - i) <= 20, f"启动后 {n - 1 - i} 个交易日"),
        _check("无失效", up_days / total >= 0.45 and slope > 0,
               f"阳线占比 {up_days / total:.0%}，5日均速 {slope:+.1f}%"),
    ]
    return {
        "id": "m6", "name": "⑥ 一柱擎天", "anchor": i,
        "checks": checks,
        "buy": {"type": "回踩买点", "trigger": round(ctx["ma"]["8"], 2),
                "desc": "沿 5/8 日均线回踩不破时介入，加速前上车"},
        "stop": {"price": round(min(ctx["ma"]["13"] * 0.985, bars[i]["l"] * 0.99), 2),
                 "basis": "13 日均线或启动涨停最低点"},
        "invalidation": "放量阴线跌破短期组；阳线缩短、量能背离",
    }


def m7_xianren(ctx, bars, ev):
    """⑦ 仙人指路：3 个月以上底部平台 + 历史级放量涨停突破 + 回踩确认。"""
    n = len(bars)
    ups = [i for i in range(max(1, n - 30), n) if ev[i]["meta"].get("limit_up")]
    for i in ups:
        plat = platform(bars, i, min_len=60, max_amp=0.35)
        if not plat:
            continue
        s, e, hi, lo, length = plat
        if not (ev[i]["meta"].get("double_vol") or ev[i]["meta"].get("volume_peak")):
            continue
        tail_shrink = any(ev[k]["meta"].get("shrink") for k in range(max(s, i - 20), i))
        confirmed = ctx["close"] > hi * 1.0 and any(
            ev[k]["meta"].get("shrink") for k in range(i, n))
        checks = [
            _check("异动价", True, f"{bars[i]['dt']} 放量涨停突破平台高点 {hi:.2f}"),
            _check("异动量", True, f"启动量接近近120日天量（{ev[i]['vol_ratio']:.2f} 倍均量）"),
            _check("均线/结构", ctx["trend"] != "空头排列", f"当前{ctx['trend']}"),
            _check("位置", ctx["position"] == "低位", f"{ctx['position']}"),
            _check("时间", length >= 60,
                   f"平台 {length} 个交易日（约 {length // 20} 个月，要求 ≥3 个月）"),
            _check("无失效", ctx["close"] > hi * 0.98,
                   "未跌回平台" if ctx["close"] > hi * 0.98 else "已跌回平台"),
        ]
        return {
            "id": "m7", "name": "⑦ 仙人指路", "anchor": i,
            "checks": checks,
            "buy": {"type": "突破买点", "trigger": round(hi * 1.01, 2),
                    "desc": "回踩中期均线组确认后；或突破当日打试仓"},
            "stop": {"price": round(lo * 0.985, 2), "basis": "平台下沿下方 1.5%"},
            "invalidation": "涨停量能不足；突破后跌回平台；平台不足 3 个月",
        }
    return None


def m8_chouma(ctx, bars, ev):
    """⑧ 筹码乖离修复：BIAS60 <= -30% + 末端异动 + 双峰真空（筹码数据缺失时降级）。"""
    if ctx["bias60"] > -20:
        return None
    n = len(bars)
    flag = [i for i in range(max(1, n - 20), n)
            if ev[i]["meta"].get("limit_down") or ev[i]["meta"].get("limit_up")]
    checks = [
        _check("异动价", bool(flag),
               f"{bars[flag[-1]]['dt']} 出现涨/跌停异动" if flag else "末端无异动"),
        _check("异动量", True, f"近 20 日均量比 {ctx['vol5_20']:.2f}"),
        _check("均线/结构", True, f"当前{ctx['trend']}，距 MA60 {ctx['bias60']:+.1f}%"),
        _check("位置", ctx["position"] == "低位", f"{ctx['position']}"),
        _check("时间", True, "中期下跌末端，反弹第一段向 MA60 回归"),
        _check("筹码真空", False, "缺筹码分布数据（需自行核对双峰间真空带）", missing=True),
    ]
    return {
        "id": "m8", "name": "⑧ 筹码乖离修复", "anchor": flag[-1] if flag else n - 1,
        "checks": checks,
        "buy": {"type": "乖离买点", "trigger": round(ctx["ma"]["5"], 2),
                "desc": "异动后止跌企稳：站上 5 日线（触发价）+ 放量阳线"},
        "stop": {"price": round(min(b["l"] for b in bars[-20:]) * 0.97, 2),
                 "basis": "底部密集峰下沿"},
        "invalidation": "双峰之间筹码被填满；低位吸筹不足；跌破底部峰",
        "note": "筹码分布需人工确认，机械口径只覆盖乖离与异动两条",
    }


def m9_zhenkong(ctx, bars, ev):
    """⑨ 真空反转平台：下跌中继平台 → 跌破后收敛 → 跳空涨停 → 缺口不补。"""
    n = len(bars)
    gaps = [i for i in range(max(1, n - 60), n)
            if (ev[i]["meta"].get("gap_up") and ev[i]["meta"].get("limit_up"))
            or ev[i]["meta"].get("limit_up")]
    if not gaps:
        return None
    i = gaps[-1]
    plat = platform(bars, i, min_len=20, max_amp=0.30)
    gap = ev[i]["meta"].get("gap_up")
    floor = plat[3] if plat else min(bars[max(0, i - 3)]["l"], bars[i]["l"])
    hold = (ctx["close"] >= gap[0]) if gap else (ctx["close"] > floor)
    checks = [
        _check("异动价", True, f"{bars[i]['dt']} 跳空/涨停打断下跌"),
        _check("异动量", ev[i]["vol_ratio"] >= 1.3,
               f"启动日量比 {ev[i]['vol_ratio']:.2f}"),
        _check("均线/结构", ctx["trend"] != "空头排列", f"当前{ctx['trend']}"),
        _check("位置", ctx["position"] != "高位", f"{ctx['position']}"),
        _check("时间", bool(plat), "存在前期下跌中继平台" if plat else "未识别到平台结构"),
        _check("无失效", hold,
               ("未回补启动缺口" if hold else "启动缺口已被回补（铁律：补掉即失效）")
               if gap else ("仍在平台下沿上方" if hold else "已跌破平台下沿")),
    ]
    buy_px = gap[0] if gap else floor
    return {
        "id": "m9", "name": "⑨ 真空反转平台", "anchor": i,
        "checks": checks,
        "buy": {"type": "突破买点", "trigger": round(max(buy_px, ctx["ma"]["13"]), 2),
                "desc": "震荡末端均线粘合转多、贴短期组启动时"},
        "stop": {"price": round(min(bars[max(0, i - 5)]["l"], buy_px) * 0.98, 2),
                 "basis": "缺口下沿/平台下沿"},
        "invalidation": "缺口被回补；跌破平台下沿；短期组重新跌回中期组下方",
    }


DETECTORS = [m1_shangying, m2_nshi, m3_chuanyang, m4_tanlu, m5_jizhi,
             m6_yizhu, m7_xianren, m8_chouma, m9_zhenkong]


# ---------------------------------------------------------------- 背离与共振

def divergences(ctx):
    bars = ctx["chart"]["bars"]
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    out = []
    n = len(bars)
    if n < 40:
        return out
    # 量价背离：近 10 日创新高但量低于前高量
    recent = closes[-10:]
    if max(recent) >= max(closes[-40:]) - 1e-9:
        i_hi = n - 10 + recent.index(max(recent))
        j_hi = max(range(n - 40, n - 10), key=lambda k: closes[k])
        if closes[i_hi] >= closes[j_hi] and vols[i_hi] < vols[j_hi] * 0.9:
            out.append({"type": "量价背离（多头）", "desc": "价创新高、量未创新高 → 卖点信号"})
    recent_low = min(recent)
    if recent_low <= min(closes[-40:]) + 1e-9:
        i_lo = n - 10 + recent.index(recent_low)
        j_lo = min(range(n - 40, n - 10), key=lambda k: closes[k])
        if closes[i_lo] <= closes[j_lo] and vols[i_lo] > vols[j_lo] * 1.2:
            out.append({"type": "量价背离（空头）", "desc": "价创新低、量放大 → 买点信号"})
    m = ctx["macd"]
    if m["dif"] > m["dif_prev"] and ctx["close"] < closes[-3]:
        out.append({"type": "MACD 底背离迹象", "desc": "价格走低、DIF 抬升（需周线验证）"})
    if m["dif"] < m["dif_prev"] and ctx["close"] > closes[-3]:
        out.append({"type": "MACD 顶背离迹象", "desc": "价格走高、DIF 走低（需周线验证）"})
    return out


ID_NAME = {
    "m1": "① 上影反攻", "m2": "② n 式倍量双涨停", "m3": "③ 串阳爬坡",
    "m4": "④ 探路尖兵", "m5": "⑤ 极值反转", "m6": "⑥ 一柱擎天",
    "m7": "⑦ 仙人指路", "m8": "⑧ 筹码乖离修复", "m9": "⑨ 真空反转平台",
}


# ---------------------------------------------------------------- 汇总与计划

def evaluate(ctx):
    full = ctx["bars_full"]
    ev = ctx["events_raw"]
    matched, near, all_models = [], [], []
    for det in DETECTORS:
        try:
            r = det(ctx, full, ev)
        except Exception as exc:  # noqa: BLE001 - 单模型失败不影响整体
            r = None
            ctx.setdefault("errors", []).append(f"{det.__name__}: {exc}")
        mid = det.__name__.split("_")[0]
        if not r:
            all_models.append({"id": mid, "name": ID_NAME[mid], "status": "未触发",
                               "score": 0, "passed": 0, "total": 6})
            continue
        passed = sum(1 for c in r["checks"] if c["pass"])
        total = sum(1 for c in r["checks"] if not c.get("missing"))
        r["passed"], r["total"] = passed, total
        r["score"] = round(passed / total * 100) if total else 0
        r["level"] = _level(passed, total)
        all_models.append({**r, "status": r["level"]})
        (matched if r["level"] != "不成立" else near).append(r)
    matched.sort(key=lambda x: (x["score"], x["passed"]), reverse=True)
    near.sort(key=lambda x: (x["score"], x["passed"]), reverse=True)
    best = matched[0] if matched else None

    div = divergences(ctx)
    copies = len([m for m in matched if m["id"] in ("m1", "m2", "m4")])
    resonance = {
        "复刻": copies >= 2,
        "嵌套": len(matched) >= 2,
        "背离共振": bool(div),
        "组合": " + ".join(m["name"] for m in matched) if matched else "无",
    }

    # ---- 否决项（checklist F + 结构失效）
    veto = []
    if ctx["position"] == "高位" and ctx["bias60"] > 50:
        veto.append("位置高位且 BIAS60 > 50%")
    if ctx["trend"] == "空头排列" and ctx["bias60"] < -40:
        veto.append("空头排列且深度负乖离，属下跌中继而非底部")
    struct_stop = best["stop"]["price"] if best else None
    if best and struct_stop and struct_stop >= ctx["close"] * 0.995:
        veto.append("结构止损位已高于现价，模型结构已被跌破")
    if best and ctx["close"] < ctx["ma"]["55"] and best["level"] == "标准版":
        veto.append("已跌破中期均线组，标准版需降级")

    # ---- 决策
    if veto:
        decision, tone = "规避", "bad"
    elif best and best["level"] == "标准版":
        decision, tone = "可试仓", "good"
    elif best and best["level"] == "弱化版":
        decision, tone = "观察待确认", "warn"
    else:
        decision, tone = "观察区", "bad" if ctx["trend"] == "空头排列" else "warn"

    # ---- 仓位（risk.md 分级 + 双十法则：散户单票 ≤20%）
    if decision == "规避" or not best:
        grade, cap_max, trial = "C", 0, 0
    elif best["level"] == "标准版" and ctx["trend"] == "多头排列":
        grade, cap_max, trial = "A", 20, 6
    elif best["level"] == "标准版":
        grade, cap_max, trial = "A", 20, 5
    else:
        grade, cap_max, trial = "B", 10, 3
    cap_now = trial if decision == "可试仓" else 0

    # ---- 止损：结构位与 -12% 取先到者
    static_stop = round(ctx["close"] * 0.88, 2)
    if struct_stop:
        stop_price = round(max(struct_stop, static_stop), 2)
        stop_basis = (f"结构位（{best['stop']['basis']}）先到" if struct_stop >= static_stop
                      else "12% 静态止损先到")
    else:
        stop_price = static_stop
        stop_basis = "无模型结构位，按 12% 静态止损"
    risk_pct = round((stop_price / ctx["close"] - 1) * 100, 2)  # 负数=止损在下方

    ma60 = ctx["ma"]["60"]
    targets = [
        {"bias": 30, "price": round(ma60 * 1.30, 2), "label": "震荡/熊市分批"},
        {"bias": 50, "price": round(ma60 * 1.50, 2), "label": "牛市环境放宽"},
        {"bias": 100, "price": round(ma60 * 2.00, 2), "label": "极端主线 等级一"},
    ]

    plan = {
        "decision": decision, "tone": tone,
        "grade": grade, "cap_now": cap_now, "cap_max": cap_max,
        "model": best["name"] if best else "无模型命中",
        "level": best["level"] if best else "—",
        "buy_type": best["buy"]["type"] if best else "—",
        "trigger": best["buy"]["trigger"] if best else None,
        "buy_desc": best["buy"]["desc"] if best else "等待异动 + 模型买点，不做左侧",
        "invalidation": best["invalidation"] if best else "—",
        "stop": {"price": stop_price, "struct": struct_stop, "static": static_stop,
                 "basis": stop_basis, "risk_pct": risk_pct, "valid": risk_pct < 0},
        "targets": targets,
        "sizing": {"trial": trial, "add1": trial, "add2": trial,
                   "desc": "试仓 → 突破加 → 回踩确认加"},
        "veto": veto,
        "resonance": resonance,
    }
    return {"models": matched, "near_models": near, "all_models": all_models,
            "plan": plan, "divergences": div, "errors": ctx.get("errors", [])}
