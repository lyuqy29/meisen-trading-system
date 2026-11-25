"""梅森体系数据层：指数/板块/个股 日K + 均线 + 量能。"""
import json, urllib.request, statistics as st

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
      "Referer": "https://gu.qq.com/"}
TX = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={sym},day,,,{n},qfq"
EM_LIST = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz={pz}&po=1&np=1&fltt=2&invt=2"
           "&fid=f3&fs={fs}&fields=f12,f14,f2,f3,f4,f5,f6,f8,f20,f62,f104,f105,f128,f136,f109,f24")
EM_K = ("https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid}&klt=101&fqt=1"
        "&beg=0&end=20500101&lmt={n}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57")


def get(url, ref="https://gu.qq.com/"):
    h = dict(UA); h["Referer"] = ref
    return json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=25).read().decode())


def kline(sym, n=120):
    d = get(TX.format(sym=sym, n=n))["data"][sym]
    rows = d.get("qfqday") or d.get("day")
    out = []
    for r in rows:
        out.append({"date": r[0], "open": float(r[1]), "close": float(r[2]),
                    "high": float(r[3]), "low": float(r[4]), "vol": float(r[5])})
    return out


def ma(closes, n):
    return sum(closes[-n:]) / n if len(closes) >= n else None


def state_of(closes):
    m5, m10, m20 = ma(closes, 5), ma(closes, 10), ma(closes, 20)
    if None in (m5, m10, m20):
        return "数据不足", m5, m10, m20
    if m5 > m10 > m20 and closes[-1] > m5:
        return "多头排列(朝上)", m5, m10, m20
    if m5 < m10 < m20 and closes[-1] < m5:
        return "空头排列(朝下)", m5, m10, m20
    spread = (max(m5, m10, m20) - min(m5, m10, m20)) / m20
    if spread < 0.015:
        return "均线粘合", m5, m10, m20
    return "缠绕", m5, m10, m20


def summarize(rows):
    c = [r["close"] for r in rows]
    v = [r["vol"] for r in rows]
    last = rows[-1]
    ret = lambda k: (c[-1] / c[-1 - k] - 1) * 100 if len(c) > k else None
    m5, m10, m20 = ma(c, 5), ma(c, 10), ma(c, 20)
    state, *_ = state_of(c)
    vol5 = st.mean(v[-6:-1]) if len(v) > 6 else None
    return {
        "date": last["date"], "close": c[-1],
        "ret1": ret(1), "ret5": ret(5), "ret20": ret(20), "ret60": ret(60),
        "ma5": m5, "ma10": m10, "ma20": m20, "state": state,
        "dist_ma20": (c[-1] / m20 - 1) * 100 if m20 else None,
        "dist_ma5": (c[-1] / m5 - 1) * 100 if m5 else None,
        "vol_ratio": v[-1] / vol5 if vol5 else None,
        "high20": max(c[-20:]) if len(c) >= 20 else None,
        "low20": min(c[-20:]) if len(c) >= 20 else None,
        "new_high20": c[-1] >= max(c[-21:-1]) if len(c) >= 21 else None,
        "new_low5": c[-1] <= min(c[-5:]) if len(c) >= 5 else None,
        "bars": len(c),
    }


def em_sectors(pz=500):
    r = get(EM_LIST.format(pz=pz, fs="m:90+t:2"), "https://quote.eastmoney.com/")
    return r["data"]["diff"]


def board_kline(code, n=90):
    r = get(EM_K.format(secid=f"90.{code}", n=n), "https://quote.eastmoney.com/")
    kl = r["data"]["klines"]
    out = []
    for s in kl:
        p = s.split(",")
        out.append({"date": p[0], "open": float(p[1]), "close": float(p[2]),
                    "high": float(p[3]), "low": float(p[4]), "vol": float(p[5])})
    return out


def em_constituents(board, pz=60):
    r = get(EM_LIST.format(pz=pz, fs=f"b:{board}"), "https://quote.eastmoney.com/")
    return (r.get("data") or {}).get("diff") or []


# ---------------------------------------------------------------- CLI
INDEX = {"上证": "sh000001", "深成": "sz399001", "创业板": "sz399006",
         "科创50": "sh000688", "沪深300": "sh000300"}


def _sym(code: str) -> str:
    code = code.strip().lower()
    if code[:2] in ("sh", "sz", "bj"):
        return code
    if code.startswith(("60", "68", "90")):
        return "sh" + code
    if code.startswith(("00", "30", "39")):
        return "sz" + code
    return "bj" + code


def cmd_index(_args: list[str]) -> None:
    print(f"{'指数':8s}{'日期':12s}{'收盘':>10s}{'日':>8s}{'5日':>8s}{'20日':>8s}{'距MA20':>9s}  {'均线':16s}")
    for name, sym in INDEX.items():
        try:
            s = summarize(kline(sym, 130))
            print(f"{name:8s}{s['date']:12s}{s['close']:10.2f}{s['ret1']:+8.2f}{s['ret5']:+8.2f}"
                  f"{s['ret20']:+8.2f}{s['dist_ma20']:+9.2f}  {s['state']:16s}")
        except Exception as e:  # noqa: BLE001
            print(f"{name:8s} 数据获取失败: {type(e).__name__}: {e}")


def cmd_sectors(_args: list[str]) -> None:
    """按 5 日涨幅取前 30 个板块，再用板块 K 线算 20 日/均线，按 (20日+5日) 排序。"""
    secs = em_sectors()
    secs = sorted(secs, key=lambda x: (x.get("f109") or -99), reverse=True)[:30]
    rows = []
    for it in secs:
        try:
            s = summarize(board_kline(it["f12"], 70))
        except Exception:  # noqa: BLE001
            continue
        up, dn = it.get("f104") or 0, it.get("f105") or 0
        rows.append((it["f14"], it["f12"], s, up, dn, it.get("f128")))
    rows.sort(key=lambda r: (r[2]["ret20"] or -99) + (r[2]["ret5"] or -99), reverse=True)
    print(f"{'板块':14s}{'今日':>8s}{'5日':>8s}{'20日':>8s}{'60日':>8s}{'距MA20':>9s}  {'均线':14s}{'涨/跌':>9s}  领涨")
    for name, code, s, up, dn, lead in rows[:20]:
        print(f"{name[:12]:14s}{s['ret1']:+8.2f}{s['ret5']:+8.2f}{s['ret20']:+8.2f}{s['ret60']:+8.2f}"
              f"{s['dist_ma20']:+9.2f}  {s['state']:14s}{up:>4d}/{dn:<4d}  {lead}")


def cmd_stock(args: list[str]) -> None:
    codes = [a for a in args if not a.startswith("-")]
    if not codes:
        print("用法: python3 scripts/ms_data.py stock 601985 688172 ...")
        return
    print(f"{'代码':8s}{'收盘':>10s}{'日':>8s}{'5日':>8s}{'20日':>8s}{'距MA20':>9s}{'距MA5':>8s}  {'均线':16s}{'量比':>6s}")
    for c in codes:
        try:
            s = summarize(kline(_sym(c), 130))
            print(f"{c:8s}{s['close']:10.2f}{s['ret1']:+8.2f}{s['ret5']:+8.2f}{s['ret20']:+8.2f}"
                  f"{s['dist_ma20']:+9.2f}{s['dist_ma5']:+8.2f}  {s['state']:16s}{s['vol_ratio']:6.2f}")
        except Exception as e:  # noqa: BLE001
            print(f"{c:8s} 获取失败: {type(e).__name__}: {e}")


def main(argv: list[str] | None = None) -> int:
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    cmds = {"index": cmd_index, "sectors": cmd_sectors, "stock": cmd_stock}
    if not argv or argv[0] in ("-h", "--help", "help"):
        print("用法: python3 scripts/ms_data.py <index|sectors|stock [代码...]>")
        print("  index    大盘指数状态（均线三态/涨跌/距MA20）")
        print("  sectors  板块持续性排名（今日/5日/20日/均线/涨跌家数）")
        print("  stock    个股状态，如: stock 601985 688172")
        return 0
    fn = cmds.get(argv[0])
    if not fn:
        print(f"未知命令: {argv[0]}")
        return 2
    fn(argv[1:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
