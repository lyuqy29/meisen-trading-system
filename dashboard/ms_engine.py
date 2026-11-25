#!/usr/bin/env python3
"""梅森交易体系 · 看板引擎（只依赖标准库）。

把 meisen-trading-system 的判断口径做成看板接口：
  overview()      三大指数均线三态 + 三天不新低 + 时机结论
  sectors(top)     板块持续性（今日/5日/20日/均线/涨跌家数）
  stock(code)      个股位置判断（均线三态、距 MA20、买点候选、止损建议）
  intraday(code)   日内做T：分时价格/均价、大盘同步、急跌急涨信号、当日最强 T 机会
  plan()           交易计划解析（plans/*.md）+ 实时触发状态

口径来源：meisen-trading-system/references/03-timing.md、07-buy-points.md、
10-ma-trend.md、12-bottom.md、15-checklist.md。
"""
from __future__ import annotations

import json
import os
import re
import statistics as st
import time
import urllib.error
import urllib.request

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0 Safari/537.36")
TX = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq"
EM_LIST = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz={pz}&po=1&np=1&fltt=2&invt=2"
           "&fid=f3&fs={fs}&fields=f12,f14,f3,f104,f105,f109,f24,f62,f128")
EM_K = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&klt=101&fqt=1"
        "&beg=0&end=20500101&lmt={n}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57")

INDEX = {"上证": "sh000001", "深成": "sz399001", "创业板": "sz399006",
         "科创50": "sh000688", "沪深300": "sh000300"}

_TTL = 300
_cache: dict[str, tuple[float, dict]] = {}
_NAMES: dict[str, str] = {}
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
SECTORS_CACHE = os.path.join(DATA, "ms_sectors.json")


class DataError(RuntimeError):
    pass


def _get(url: str, ref: str = "https://gu.qq.com/", tries: int = 3) -> dict:
    last: Exception | None = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": ref})
            return json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(0.8 * (i + 1))
    raise DataError(f"行情获取失败（{type(last).__name__}），请稍后重试")


def _cached(key: str, fn, ttl: int = _TTL):
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < ttl:
        return hit[1]
    val = fn()
    _cache[key] = (now, val)
    return val


def symbol_of(code: str) -> str:
    code = str(code).strip().lower()
    if code[:2] in ("sh", "sz", "bj"):
        return code
    if code.startswith(("60", "68", "90", "51", "58")):
        return "sh" + code
    if code.startswith(("00", "30", "20", "15", "16", "39")):
        return "sz" + code
    if code.startswith(("43", "83", "87", "92")):
        return "bj" + code
    raise DataError("代码格式不对，试试 6 位代码，例如 600519")


def kline(sym: str, n: int = 130) -> list[dict]:
    d = _get(TX.format(sym=sym, n=n))
    node = (d.get("data") or {}).get(sym) or {}
    rows = node.get("qfqday") or node.get("day") or []
    if not rows:
        raise DataError("没有拿到 K 线数据")
    qt = (node.get("qt") or {}).get(sym) or []
    if len(qt) > 1 and qt[1]:
        _NAMES[sym] = str(qt[1])
    return [{"date": r[0], "open": float(r[1]), "close": float(r[2]),
             "high": float(r[3]), "low": float(r[4]), "vol": float(r[5])} for r in rows]


def _ma(vals: list[float], n: int) -> float | None:
    return sum(vals[-n:]) / n if len(vals) >= n else None


def ma_state(closes: list[float]) -> str:
    m5, m10, m20 = _ma(closes, 5), _ma(closes, 10), _ma(closes, 20)
    if None in (m5, m10, m20):
        return "数据不足"
    if m5 > m10 > m20 and closes[-1] > m5:
        return "多头排列"
    if m5 < m10 < m20 and closes[-1] < m5:
        return "空头排列"
    if (max(m5, m10, m20) - min(m5, m10, m20)) / m20 < 0.015:
        return "均线粘合"
    return "缠绕"


def summarize(rows: list[dict]) -> dict:
    c = [r["close"] for r in rows]
    v = [r["vol"] for r in rows]
    lows = [r["low"] for r in rows]
    m5, m10, m20 = _ma(c, 5), _ma(c, 10), _ma(c, 20)
    ret = lambda k: round((c[-1] / c[-1 - k] - 1) * 100, 2) if len(c) > k else None  # noqa: E731
    vol5 = st.mean(v[-6:-1]) if len(v) > 6 else None
    swing = min(lows[-10:])
    no_new_low = 0
    for lw in reversed(lows):
        if lw > swing:
            no_new_low += 1
        else:
            break
    return {
        "date": rows[-1]["date"], "close": round(c[-1], 2),
        "ret1": ret(1), "ret5": ret(5), "ret20": ret(20), "ret60": ret(60),
        "ma5": round(m5, 2) if m5 else None,
        "ma10": round(m10, 2) if m10 else None,
        "ma20": round(m20, 2) if m20 else None,
        "state": ma_state(c),
        "dist_ma20": round((c[-1] / m20 - 1) * 100, 2) if m20 else None,
        "dist_ma5": round((c[-1] / m5 - 1) * 100, 2) if m5 else None,
        "vol_ratio": round(v[-1] / vol5, 2) if vol5 else None,
        "high20": round(max(c[-20:]), 2), "low20": round(min(c[-20:]), 2),
        "swing_low": round(swing, 2), "no_new_low": no_new_low,
        "bars": len(c),
    }


# ---------------------------------------------------------------- 时机
def _timing_verdict(rows: dict[str, dict]) -> dict:
    down = sum(1 for s in rows.values() if s["state"] == "空头排列")
    up = sum(1 for s in rows.values() if s["state"] == "多头排列")
    confirm = sum(1 for s in rows.values() if s["no_new_low"] >= 3)
    if down >= 3:
        level, text = "defense", "防守：三大指数同时朝下，只允许试仓或空仓"
    elif up >= 3:
        level, text = "attack", "进攻：多指数共振向上，可提高仓位"
    elif confirm >= 2:
        level, text = "probe", "试探：已出现三天不新低，可小仓试错（1/6~1/5）"
    else:
        level, text = "wait", "观望：方向未明，等三天不新低或均线联合朝上"
    return {"level": level, "text": text, "down": down, "up": up, "confirm": confirm}


def overview() -> dict:
    def build():
        rows = {}
        for name, sym in INDEX.items():
            try:
                rows[name] = summarize(kline(sym, 90))
            except DataError:
                rows[name] = {"state": "数据缺失", "close": None, "ret1": None,
                              "ret5": None, "ret20": None, "dist_ma20": None,
                              "no_new_low": 0, "swing_low": None, "ma20": None, "date": "—"}
        return {"indices": rows, "verdict": _timing_verdict(rows),
                "asof": next((r["date"] for r in rows.values() if r.get("date") != "—"), "—")}
    return _cached("overview", build)


# ---------------------------------------------------------------- 板块
def _sectors() -> dict:
    """板块持续性（列表口径）：今日 / 5日 / 60日 / 涨跌家数 / 领涨 / 主力净额。

    说明：东财板块 K 线接口在当前网络下常被重置（RemoteDisconnected），
    因此 20 日与均线状态暂不提供，界面标注为「—」，避免伪造数据。
    成功结果落盘 data/ms_sectors.json，接口异常时回退到上次快照（stale=True）。
    """
    d = _get(EM_LIST.format(pz=500, fs="m:90+t:2"), "https://quote.eastmoney.com/", tries=2)
    items = (d.get("data") or {}).get("diff") or []
    if not items:
        raise DataError("板块列表为空")
    rows = []
    for it in items:
        up, dn = it.get("f104") or 0, it.get("f105") or 0
        rows.append({
            "name": it.get("f14") or "—", "code": it.get("f12") or "",
            "today": it.get("f3"), "ret5": it.get("f109"), "ret20": None,
            "ret60": it.get("f24"), "dist_ma20": None, "state": "—",
            "up": up, "dn": dn,
            "ratio": round(up / (up + dn) * 100, 0) if (up + dn) else None,
            "lead": it.get("f128"), "flow": it.get("f62"),
        })
    rows.sort(key=lambda r: r["ret5"] if r["ret5"] is not None else -99, reverse=True)
    data = {"rows": rows[:24], "asof": time.strftime("%Y-%m-%d %H:%M"), "stale": False,
            "note": "20日/均线状态因板块K线接口受限暂缺"}
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(SECTORS_CACHE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except OSError:
        pass
    return data


def _sectors_cached_file() -> dict:
    try:
        with open(SECTORS_CACHE, encoding="utf-8") as f:
            d = json.load(f)
            d["stale"] = True
            return d
    except Exception:  # noqa: BLE001
        return {"rows": [], "asof": "—", "stale": True, "note": "板块数据暂时取不到，稍后重试"}


def sectors() -> dict:
    try:
        return _cached("sectors", _sectors, ttl=600)
    except Exception:  # noqa: BLE001
        return _sectors_cached_file()


# ---------------------------------------------------------------- 个股
def stock(code: str) -> dict:
    sym = symbol_of(code)
    key = f"stock:{sym}"
    return _cached(key, lambda: _stock(sym), ttl=120)


def _stock(sym: str) -> dict:
    rows = kline(sym, 130)
    s = summarize(rows)
    closes = [r["close"] for r in rows]
    # 名称：从腾讯实时行情取
    name = _NAMES.get(sym, sym)

    idx = overview()
    sh = idx["indices"].get("上证") or {}
    idx_ret20 = sh.get("ret20")
    idx_ret1 = sh.get("ret1")

    # 位置判断（07-buy-points / 10-ma-trend）
    d20 = s["dist_ma20"]
    if s["state"] == "空头排列":
        zone, tone = "趋势朝下 · 不做", "bad"
    elif d20 is None:
        zone, tone = "数据不足", "dim"
    elif d20 > 10:
        zone, tone = "双涨追高区 · 等回踩", "warn"
    elif d20 > 4:
        zone, tone = "趋势中段 · 只做回踩", "warn"
    elif d20 >= -2:
        zone, tone = "回踩区 · 可试仓", "good"
    elif d20 >= -6:
        zone, tone = "破位观察 · 不接刀", "warn"
    else:
        zone, tone = "深跌区 · 等企稳", "bad"

    # 买点候选（三大买点）
    signals = []
    if idx_ret1 is not None and s["ret1"] is not None and idx_ret1 < 0 and s["ret1"] < -0.5 \
            and s["state"] in ("多头排列", "均线粘合", "缠绕"):
        signals.append("双杀买点（大盘+个股同步杀跌）")
    if idx_ret20 is not None and s["ret20"] is not None and idx_ret20 < 0 < s["ret20"]:
        signals.append("当弱不弱（大盘 20 日下跌，个股逆势走强）")
    if s["state"] == "多头排列" and d20 is not None and -2 <= d20 <= 4:
        signals.append("回踩买点（多头排列回踩 MA20 附近）")
    if s["no_new_low"] >= 3 and s["state"] != "空头排列":
        signals.append("三天不新低（抄底结构，确定性偏低）")
    if s["state"] == "均线粘合" and s["ret5"] and s["ret5"] > 0:
        signals.append("均线粘合后向上（变盘向上）")

    # 止损（04-stop-loss：定线 -15% 与结构位取先到者）
    stop_struct = s["ma20"]
    stop_line = round(s["close"] * 0.85, 2)
    stop = max(v for v in (stop_struct, stop_line) if v) if stop_struct else stop_line

    # 仓位建议（05-position + 06-pickup-law）
    if tone == "good" and signals:
        cap, cap_note = "1/5", "可试仓，盈利后再加"
    elif tone == "good":
        cap, cap_note = "1/6", "只能小仓试错"
    elif tone == "warn" and s["state"] == "多头排列":
        cap, cap_note = "0", "等回踩到 MA20 附近再看"
    else:
        cap, cap_note = "0", "当前不满足体系买点"

    return {
        "code": sym[2:], "name": name, "date": s["date"], "close": s["close"],
        "state": s["state"], "zone": zone, "tone": tone,
        "ret1": s["ret1"], "ret5": s["ret5"], "ret20": s["ret20"],
        "dist_ma20": d20, "dist_ma5": s["dist_ma5"], "vol_ratio": s["vol_ratio"],
        "ma5": s["ma5"], "ma10": s["ma10"], "ma20": s["ma20"],
        "high20": s["high20"], "low20": s["low20"], "no_new_low": s["no_new_low"],
        "signals": signals, "stop": stop, "stop_line": stop_line, "stop_struct": stop_struct,
        "stop_pct": round((stop / s["close"] - 1) * 100, 2),
        "cap": cap, "cap_note": cap_note,
        "index_ret20": idx_ret20, "index_state": sh.get("state"),
        "closes": [round(x, 2) for x in closes[-60:]],
        "dates": [r["date"] for r in rows[-60:]],
    }


# ---------------------------------------------------------------- 交易计划
PLAN_ROW = re.compile(r"^\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|")


def plans_dir() -> str:
    env = os.environ.get("MS_PLANS_DIR")
    cands = [env] if env else []
    here = os.path.dirname(os.path.abspath(__file__))
    cands += [os.path.join(here, "plans"), os.path.join(os.path.dirname(here), "plans"),
              os.path.join(os.path.dirname(os.path.dirname(here)), "plans")]
    for c in cands:
        if c and os.path.isdir(c):
            return c
    return ""


def _num(cell: str) -> float | None:
    m = re.search(r"(\d+(?:\.\d+)?)", cell.replace(",", ""))
    return float(m.group(1)) if m else None


def _trigger(cell: str) -> tuple[float, float] | None:
    m = re.search(r"(\d+(?:\.\d+)?)\s*[-–~到]\s*(\d+(?:\.\d+)?)", cell)
    if m:
        return float(m.group(1)), float(m.group(2))
    v = _num(cell)
    return (v, v) if v else None


def _parse_plan_file(path: str) -> list[dict]:
    """按表头解析计划表（列名含「标的/触发/仓位/止损」），找不到表头则退回启发式。"""
    lines = open(path, encoding="utf-8").read().splitlines()
    rows: list[dict] = []
    header: list[str] | None = None
    for line in lines:
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        if any("标的" in c for c in cells) and any("止损" in c for c in cells):
            header = cells
            continue
        if set(s) <= set("|-: "):
            continue
        m = re.search(r"(\d{6})", s)
        if not m:
            continue
        code = m.group(1)
        rec = {"code": code, "file": os.path.basename(path)}
        if header and len(header) >= 3:
            def col(keyword: str) -> str | None:
                for i, h in enumerate(header):
                    if keyword in h and i < len(cells):
                        return cells[i]
                return None
            name_cell = cells[0]
            rec["name"] = re.sub(r"\d{6}", "", name_cell).strip()
            rec["kind"] = col("性质") or (cells[1] if len(cells) > 1 else "")
            rec["trigger_text"] = col("触发") or ""
            rec["trigger"] = _trigger(rec["trigger_text"])
            rec["weight"] = col("仓位") or ""
            rec["stop"] = _num(col("止损") or "")
        else:
            # 兜底：只接受「像计划行」的记录（有仓位百分比或 ≤/≥/区间 触发价）
            weight = next((c for c in cells if re.fullmatch(r"\d{1,3}%", c)), "")
            trig_cell = next((c for c in cells if re.search(r"[≤≥]|\d\s*[-–~到]\s*\d", c)), "")
            if not weight and not trig_cell:
                continue
            rec.update({"name": re.sub(r"\d{6}", "", cells[0]).strip(),
                        "kind": cells[1] if len(cells) > 1 else "",
                        "trigger_text": trig_cell,
                        "trigger": _trigger(trig_cell) if trig_cell else None,
                        "weight": weight,
                        "stop": _num(cells[-3]) if len(cells) >= 3 else None})
        rows.append(rec)
    return rows


def plan() -> dict:
    d = plans_dir()
    if not d:
        return {"ok": True, "file": None, "rows": [], "note": "未找到 plans/ 目录"}
    files = sorted((f for f in os.listdir(d) if f.endswith(".md")), reverse=True)
    if not files:
        return {"ok": True, "file": None, "rows": [], "note": "plans/ 里还没有计划"}
    path = os.path.join(d, files[0])
    base = _parse_plan_file(path)
    out = []
    for r in base:
        item = dict(r)
        try:
            s = stock(r["code"])
            item.update({"name": s["name"] or r["name"], "close": s["close"],
                         "state": s["state"], "dist_ma20": s["dist_ma20"]})
            trig = r["trigger"]
            if trig:
                lo, hi = trig
                if s["close"] < (r["stop"] or 0):
                    item["status"], item["tone"] = "已破止损 · 取消", "bad"
                elif lo == hi and s["close"] >= lo:
                    item["status"], item["tone"] = "触发", "good"
                elif lo != hi and lo <= s["close"] <= hi:
                    item["status"], item["tone"] = "进入区间 · 可试仓", "good"
                elif s["close"] > hi:
                    item["status"], item["tone"] = "高于触发价 · 等回踩", "warn"
                else:
                    item["status"], item["tone"] = f"等待（差 {(lo / s['close'] - 1) * 100:+.1f}%）", "dim"
            else:
                item["status"], item["tone"] = "条件单", "dim"
        except Exception as exc:  # noqa: BLE001
            item.update({"error": f"{type(exc).__name__}", "status": "取数失败", "tone": "dim"})
        out.append(item)
    return {"ok": True, "file": files[0], "rows": out, "note": ""}


# ---------------------------------------------------------------- 日内做T
MIN = "https://web.ifzq.gtimg.cn/appstock/app/minute/query?code={sym}"


def _minute(sym: str) -> dict:
    d = _get(MIN.format(sym=sym), "https://gu.qq.com/")
    node = (d.get("data") or {}).get(sym) or {}
    inner = node.get("data") or {}
    rows = inner.get("data") or []
    q = (node.get("qt") or {}).get(sym) or []
    out = {"date": inner.get("date") or "", "name": q[1] if len(q) > 1 else sym,
           "prev_close": float(q[4]) if len(q) > 4 else None,
           "last": float(q[3]) if len(q) > 3 else None,
           "points": [], "unit": 100.0}
    # 腾讯分时：主板 cum_vol 单位是「手」，科创板/创业板是「股」——用首行反推
    if rows:
        f0 = rows[0].split()
        if len(f0) >= 4:
            p0, cv0, ca0 = float(f0[1]), float(f0[2]), float(f0[3])
            if cv0 > 0 and p0 > 0 and (ca0 / cv0) / p0 < 10:
                out["unit"] = 1.0
    pv = pa = 0.0
    for r in rows:
        f = r.split()
        if len(f) < 4:
            continue
        t, price, cv, ca = f[0], float(f[1]), float(f[2]), float(f[3])
        vol, amt = max(cv - pv, 0.0), max(ca - pa, 0.0)
        pv, pa = cv, ca
        shares = cv * out["unit"]
        out["points"].append({"t": t, "price": price, "vol": vol,
                              "avg": round(ca / shares, 3) if shares else price})
    return out


def intraday(code: str) -> dict:
    sym = symbol_of(code)
    key = f"min:{sym}"

    def build():
        m = _minute(sym)
        idx = _minute("sh000001")
        pts = m["points"]
        if not pts:
            raise DataError("没有分时数据（可能未开盘）")
        prev = m["prev_close"] or pts[0]["price"]
        prices = [p["price"] for p in pts]
        high, low = max(prices), min(prices)
        amt = sum(p["vol"] * m.get("unit", 100.0) * p["price"] for p in pts)
        amp = (high - low) / prev * 100 if prev else 0

        # 大盘分时（按分钟对齐，换算成涨跌幅）
        idx_map = {}
        ip = idx["points"]
        iprev = idx["prev_close"] or (ip[0]["price"] if ip else None)
        for p in ip:
            if iprev:
                idx_map[p["t"]] = round((p["price"] / iprev - 1) * 100, 2)

        # 信号：急跌/急涨/均线穿越/偏离均价/大盘同步
        sigs = []
        vols = [p["vol"] for p in pts]
        for i, p in enumerate(pts):
            if i < 5:
                continue   # 09:30 集合竞价 + 开盘前几分钟量比失真
            base = pts[i - 1]["price"]
            chg = (p["price"] / base - 1) * 100 if base else 0
            win = vols[max(1, i - 20):i] or [1]
            vmul = p["vol"] / (sum(win) / len(win)) if sum(win) else 0
            it = idx_map.get(p["t"])
            if chg <= -0.6 and vmul >= 1.8:
                if it is not None and it <= -0.3:
                    sigs.append({"t": p["t"], "kind": "急跌正T", "tone": "good", "price": p["price"],
                                 "text": f"放量急跌 {chg:.1f}%（量 {vmul:.1f}×）+ 大盘同步 {it:+.1f}% → 正T买点候选"})
                else:
                    sigs.append({"t": p["t"], "kind": "独立杀跌", "tone": "bad", "price": p["price"],
                                 "text": f"个股独立急跌 {chg:.1f}%（大盘 {it if it is not None else 0:+.1f}%）→ 不做多T"})
            if chg >= 0.6 and vmul >= 1.8:
                sigs.append({"t": p["t"], "kind": "急涨T出", "tone": "warn", "price": p["price"],
                             "text": f"放量急涨 {chg:+.1f}%（量 {vmul:.1f}×）→ T 卖出参考"})
            if i and p["avg"]:
                a0, a1 = pts[i - 1]["avg"], p["avg"]
                dev1 = (p["price"] / a1 - 1) * 100 if a1 else 0
                if abs(dev1) >= 0.3:   # 过滤贴着均价来回抖的假信号
                    if pts[i - 1]["price"] <= a0 and p["price"] > a1:
                        sigs.append({"t": p["t"], "kind": "上穿均价", "tone": "good", "price": p["price"],
                                     "text": f"上穿分时均价（+{dev1:.1f}%）→ 转强"})
                    elif pts[i - 1]["price"] >= a0 and p["price"] < a1:
                        sigs.append({"t": p["t"], "kind": "下穿均价", "tone": "warn", "price": p["price"],
                                     "text": f"下穿分时均价（{dev1:.1f}%）→ 转弱"})
            if p["avg"]:
                dev = (p["price"] / p["avg"] - 1) * 100
                if dev >= 1.5:
                    sigs.append({"t": p["t"], "kind": "偏离均价", "tone": "warn", "price": p["price"],
                                 "text": f"高于均价 {dev:+.1f}% → T 出参考"})
                elif dev <= -1.5:
                    sigs.append({"t": p["t"], "kind": "低于均价", "tone": "good", "price": p["price"],
                                 "text": f"低于均价 {dev:.1f}% → 回补参考"})

        # 当日最强 T 机会（按 |涨跌| × 量能倍数 排序，间隔 20 分钟去重）
        cand = []
        for i, p in enumerate(pts):
            if i < 5:
                continue   # 09:30 集合竞价 + 开盘前几分钟量比失真
            base = pts[i - 1]["price"]
            chg = (p["price"] / base - 1) * 100 if base else 0
            win = vols[max(1, i - 20):i] or [1]
            vmul = p["vol"] / (sum(win) / len(win)) if sum(win) else 0
            if vmul <= 0:
                continue
            cand.append({"t": p["t"], "price": p["price"], "chg": round(chg, 2),
                         "vmul": round(vmul, 1), "index_pct": idx_map.get(p["t"]),
                         "score": abs(chg) * min(vmul, 6), "dir": "up" if chg > 0 else "down"})
        cand.sort(key=lambda x: x["score"], reverse=True)
        top, used = [], []
        for c in cand:
            if any(abs(int(c["t"]) - int(u)) < 20 for u in used):
                continue
            used.append(c["t"])
            top.append(c)
            if len(top) >= 3:
                break
        top.sort(key=lambda x: x["t"])

        # 去重：同类信号 10 分钟内只留第一个
        dedup, last = [], {}
        for s in sigs:
            gap = 20 if "均价" in s["kind"] else 10
            if s["kind"] in last and int(s["t"]) - last[s["kind"]] < gap:
                continue
            last[s["kind"]] = int(s["t"])
            dedup.append(s)

        # 适合度（11-intraday.md：波动 + 成交 + 趋势）
        try:
            st = stock(code)
            state, d20 = st["state"], st["dist_ma20"]
        except Exception:  # noqa: BLE001
            state, d20 = "—", None
        amount_yi = round(amt / 1e8, 2)
        tags = []
        if amp >= 2:
            tags.append(f"振幅 {amp:.1f}% 够做T")
        else:
            tags.append(f"振幅仅 {amp:.1f}%，做T空间不足")
        if amount_yi >= 3:
            tags.append(f"成交 {amount_yi} 亿，量能充足")
        else:
            tags.append(f"成交 {amount_yi} 亿，量能偏弱")
        if state == "多头排列":
            tags.append("日线多头，适合正T")
        elif state == "空头排列":
            tags.append("日线空头，不做多T")
        else:
            tags.append(f"日线{state}，只做小仓T")
        score = (1 if amp >= 2 else 0) + (1 if amount_yi >= 3 else 0) + (1 if state == "多头排列" else 0)

        # 早盘双杀（做T式加仓前置）
        morning = [p for p in pts if "0930" <= p["t"] <= "1000"]
        m_low = min((p["price"] for p in morning), default=None)
        early = None
        if m_low and prev:
            early_chg = (m_low / prev - 1) * 100
            i_low = min((v for k, v in idx_map.items() if "0930" <= k <= "1000"), default=None)
            early = {"stock_pct": round(early_chg, 2), "index_pct": i_low,
                     "ok": bool(early_chg <= -0.5 and (i_low is not None and i_low <= -0.5))}

        return {
            "code": sym[2:], "name": m["name"], "date": m["date"], "prev_close": prev,
            "last": pts[-1]["price"], "chg": round((pts[-1]["price"] / prev - 1) * 100, 2) if prev else 0,
            "high": high, "low": low, "amp": round(amp, 2), "amount_yi": amount_yi,
            "state": state, "dist_ma20": d20, "score": score, "tags": tags,
            "early": early,
            "topT": top,
            "range_pos": round((pts[-1]["price"] - low) / (high - low) * 100, 0) if high > low else 50,
            "points": pts[:600], "index": [{"t": k, "pct": v} for k, v in list(idx_map.items())[:600]],
            "signals": dedup[-40:],
        }
    return _cached(key, build, ttl=60)
