"""行情与指标层：拉取 A 股前复权日 K，计算移动平均带、乖离、异动事件。

数据源：腾讯 web.ifzq.gtimg.cn（实测最稳定）。仅用标准库。
所有口径对应 laofan-trading-system/references/ma-band.md 与 models.md 的 ※ 量化定义。
"""
from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36")
API = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
       "?param={sym},day,,,{n},qfq")


class DataSourceError(RuntimeError):
    """行情数据源错误。

    message 直接面向用户展示：中文、可操作，不含异常类型、堆栈等技术细节。
    其他异常一律由 server 层换成通用文案，只写日志。
    """


def symbol_of(code: str) -> str:
    """代码 → 腾讯符号（sh600519）。非法代码抛 DataSourceError 而不是 ValueError。"""
    raw = str(code or "").strip().lower().replace(".", "").replace(" ", "")
    if raw[:2] in ("sh", "sz", "bj"):
        prefix, base = raw[:2], raw[2:]
    elif raw[:2] in ("60", "68", "90", "51", "58", "11"):
        prefix, base = "sh", raw
    elif raw[:2] in ("00", "30", "20", "15", "12", "16", "39"):
        prefix, base = "sz", raw
    elif raw[:2] in ("43", "83", "87", "92"):
        prefix, base = "bj", raw
    else:
        raise DataSourceError("请输入 6 位 A 股代码（一次一个），例如 600519")
    if len(base) != 6 or not base.isdigit():
        raise DataSourceError("请输入 6 位 A 股代码（一次一个），例如 600519")
    return prefix + base


def limit_pct(sym: str, name: str = "") -> float:
    if "ST" in name.upper():
        return 5.0
    base = sym[2:]
    if sym.startswith("bj") or base.startswith(("43", "83", "87", "92")):
        return 30.0
    if base.startswith(("30", "68")):
        return 20.0
    return 10.0


def fetch(code: str, bars: int = 320) -> dict:
    sym = symbol_of(code)
    req = urllib.request.Request(
        API.format(sym=sym, n=bars),
        headers={"User-Agent": UA, "Referer": "https://gu.qq.com/"})
    try:
        payload = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "replace")
    except (urllib.error.URLError, http.client.HTTPException, OSError, TimeoutError):
        raise DataSourceError("行情接口暂时连不上，请检查网络后重试") from None
    try:
        raw = json.loads(payload)
    except ValueError:
        raise DataSourceError("行情接口返回内容异常，请稍后重试") from None
    if not isinstance(raw, dict):
        raise DataSourceError("行情接口返回内容异常，请稍后重试")
    if raw.get("code") != 0:
        raise DataSourceError("数据源查不到这个代码，请确认代码是否正确")

    data = raw.get("data")
    node = data.get(sym) if isinstance(data, dict) else None
    if not isinstance(node, dict):
        raise DataSourceError("数据源查不到这个代码，请确认代码是否正确，或该标的暂不支持")

    qt = node.get("qt")
    if isinstance(qt, dict):
        qt = qt.get(sym)
    qt = qt if isinstance(qt, (list, tuple)) else []
    name = qt[1] if len(qt) > 1 and isinstance(qt[1], str) and qt[1].strip() else sym.upper()

    rows = node.get("qfqday") or node.get("day") or []
    if not isinstance(rows, list):
        raise DataSourceError("数据源返回结构异常，请稍后重试")
    bars_out = []
    for r in rows:
        if not isinstance(r, (list, tuple)) or len(r) < 6:
            continue
        try:
            bars_out.append({"dt": str(r[0]), "o": float(r[1]), "c": float(r[2]),
                             "h": float(r[3]), "l": float(r[4]), "v": float(r[5])})
        except (TypeError, ValueError):
            continue
    if len(bars_out) < 70:
        raise DataSourceError(
            f"{name} 只有 {len(bars_out)} 根日 K，不足以做中期均线分析"
            "（新股、长期停牌或数据源暂不支持该代码）")
    return {"symbol": sym, "name": name, "bars": bars_out}


def sma(vals, n):
    if len(vals) < n:
        return None
    return sum(vals[-n:]) / n


def sma_series(closes, n):
    out, run = [], 0.0
    for i, c in enumerate(closes):
        run += c
        if i >= n:
            run -= closes[i - n]
        out.append(run / n if i >= n - 1 else None)
    return out


def ema_series(vals, n):
    k = 2 / (n + 1)
    out, prev = [], None
    for v in vals:
        prev = v if prev is None else v * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(closes):
    e12, e26 = ema_series(closes, 12), ema_series(closes, 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = ema_series(dif, 9)
    hist = [2 * (a - b) for a, b in zip(dif, dea)]
    return dif, dea, hist


def events(bars, limit):
    """标注每根 K 线的异动标签。"""
    out = []
    vols = [b["v"] for b in bars]
    for i, b in enumerate(bars):
        if i == 0:
            out.append([])
            continue
        p = bars[i - 1]
        chg = (b["c"] / p["c"] - 1) * 100
        tags = []
        tag = {}
        if chg >= limit - 0.3:
            tags.append(f"涨停{chg:+.2f}%")
            tag["limit_up"] = True
        if chg <= -(limit - 0.3):
            tags.append(f"跌停{chg:+.2f}%")
            tag["limit_down"] = True
        if p["v"] and b["v"] >= p["v"] * 2:
            tags.append(f"倍量{b['v'] / p['v']:.1f}x")
            tag["double_vol"] = True
        win = bars[max(0, i - 119): i + 1]
        vmax = max(x["v"] for x in win)
        v20 = sum(vols[max(0, i - 19): i + 1]) / len(vols[max(0, i - 19): i + 1])
        if b["v"] >= vmax * 0.995 and b["v"] >= v20 * 1.5 and len(win) >= 60:
            tags.append("近120日天量")
            tag["volume_peak"] = True
        if b["l"] > p["h"]:
            tags.append(f"向上跳空{(b['l'] / p['h'] - 1) * 100:.1f}%")
            tag["gap_up"] = (p["h"], b["l"])
        if b["h"] < p["l"]:
            tags.append(f"向下跳空{(1 - b['h'] / p['l']) * 100:.1f}%")
            tag["gap_down"] = (b["h"], p["l"])
        body = abs(b["c"] - b["o"])
        upper = b["h"] - max(b["c"], b["o"])
        lower = min(b["c"], b["o"]) - b["l"]
        if body > 0 and upper >= body * 2 and upper / b["c"] * 100 >= 3:
            tags.append(f"长上影{upper / b['c'] * 100:.1f}%")
            tag["upper_shadow"] = upper / b["c"] * 100
        if body > 0 and lower >= body * 2 and lower / b["c"] * 100 >= 3:
            tags.append(f"长下影{lower / b['c'] * 100:.1f}%")
            tag["lower_shadow"] = lower / b["c"] * 100
        # 涨停破板：盘中最少摸到涨停价，收盘未涨停且回落 >=5%
        limit_price = p["c"] * (1 + limit / 100)
        if b["h"] >= limit_price * 0.998 and b["c"] < limit_price * 0.995 \
                and (b["h"] - b["c"]) / b["c"] * 100 >= 5:
            tags.append("涨停破板")
            tag["broken_board"] = (b["h"] - b["c"]) / b["c"] * 100
        if b["v"] <= min(vols[max(0, i - 19): i + 1]) * 1.2 and b["v"] <= v20 * 0.65:
            tags.append("极致缩量")
            tag["shrink"] = True
        out.append({"tags": tags, "chg": chg, "meta": tag,
                    "vol_ratio": b["v"] / v20 if v20 else 0})
    return out


def platform(bars, end_idx, min_len=60, max_amp=0.35):
    """在 end_idx 之前寻找最长横盘平台，返回 (start, end, high, low) 或 None。"""
    best = None
    for length in range(min_len, min(260, end_idx) + 1):
        s = end_idx - length
        if s < 0:
            break
        seg = bars[s:end_idx]
        hi = max(x["h"] for x in seg)
        lo = min(x["l"] for x in seg)
        if lo <= 0:
            continue
        if (hi - lo) / lo <= max_amp:
            best = (s, end_idx - 1, hi, lo, length)
    return best


def consecutive_up(bars):
    """从最新一根往前数连续收阳（收盘高于前收）的根数，返回 (count, start_idx)。"""
    n = 1
    i = len(bars) - 1
    while i > 0 and bars[i]["c"] > bars[i - 1]["c"]:
        n += 1
        i -= 1
    return n, i


def build_context(code: str, bars_n: int = 320) -> dict:
    data = fetch(code, bars_n)
    bars = data["bars"]
    sym, name = data["symbol"], data["name"]
    closes = [b["c"] for b in bars]
    vols = [b["v"] for b in bars]
    limit = limit_pct(sym, name)

    ma = {n: sma(closes, n) for n in (5, 8, 13, 55, 60, 65)}
    short = (ma[5], ma[8], ma[13])
    mid = (ma[55], ma[60], ma[65])
    if min(short) > max(mid):
        trend = "多头排列"
    elif max(short) < min(mid):
        trend = "空头排列"
    else:
        trend = "缠绕/粘合"

    slope5 = (ma[5] / (sum(closes[-10:-5]) / 5) - 1) * 100
    close = closes[-1]
    bias60 = (close - ma[60]) / ma[60] * 100

    hi250 = max(b["h"] for b in bars[-250:])
    lo250 = min(b["l"] for b in bars[-250:])
    drop_hi = (close / hi250 - 1) * 100
    rise_lo = (close / lo250 - 1) * 100

    if drop_hi <= -40:
        position = "低位"
    elif rise_lo >= 100 and bias60 > 30:
        position = "高位"
    else:
        position = "中继/中性"

    ev = events(bars, limit)
    dif, dea, hist = macd(closes)
    up_n, up_start = consecutive_up(bars)

    v5 = sum(vols[-5:]) / 5
    v20 = sum(vols[-20:]) / 20
    chart_n = 120
    base = len(bars) - chart_n
    chart = {
        "bars": [{"dt": b["dt"], "o": b["o"], "c": b["c"], "h": b["h"],
                  "l": b["l"], "v": b["v"]} for b in bars[-chart_n:]],
        "ma5": sma_series(closes, 5)[-chart_n:],
        "ma8": sma_series(closes, 8)[-chart_n:],
        "ma13": sma_series(closes, 13)[-chart_n:],
        "ma55": sma_series(closes, 55)[-chart_n:],
        "ma60": sma_series(closes, 60)[-chart_n:],
        "ma65": sma_series(closes, 65)[-chart_n:],
    }

    recent_events = []
    for i in range(max(1, len(bars) - 60), len(bars)):
        if ev[i]["tags"]:
            recent_events.append({
                "idx": i - base if i >= base else None,
                "dt": bars[i]["dt"], "close": bars[i]["c"],
                "chg": round(ev[i]["chg"], 2),
                "vol_ratio": round(ev[i]["vol_ratio"], 2),
                "tags": ev[i]["tags"],
            })

    return {
        "symbol": sym, "code": sym[2:], "name": name,
        "last_date": bars[-1]["dt"], "close": close,
        "prev_close": closes[-2], "chg": (close / closes[-2] - 1) * 100,
        "limit_pct": limit,
        "ma": {str(k): v for k, v in ma.items()},
        "trend": trend, "slope5": slope5, "bias60": bias60,
        "hi250": hi250, "lo250": lo250, "drop_hi": drop_hi,
        "rise_lo": rise_lo, "position": position,
        "vol5_20": v5 / v20 if v20 else 1,
        "v20min": min(vols[-20:]), "v120max": max(vols[-120:]),
        "macd": {"dif": dif[-1], "dea": dea[-1], "hist": hist[-1],
                 "hist_prev": hist[-2], "dif_prev": dif[-2]},
        "up_streak": up_n, "up_streak_start": bars[up_start]["dt"] if up_n > 1 else None,
        "events_raw": ev, "recent_events": recent_events,
        "bars_full": bars,
        "chart": chart,
        "bars_meta": {"count": len(bars), "start": bars[0]["dt"]},
    }
