#!/usr/bin/env python3
"""溜溜交易手册 —— 本地服务（体系：源自量价时空交易方法论）。

只依赖标准库。启动后浏览器打开 http://127.0.0.1:8777

接口：
  GET  /api/analyze?code=600519      单票分析（模型匹配 + 交易计划）
  GET  /api/compare?codes=a,b,c      多票对比排序
  GET  /api/watchlist                读自选
  POST /api/watchlist                增删自选 {"code":"600519","action":"add|remove"}
  GET  /api/positions                持仓盯盘（浮盈/止损距离/离场信号）
  POST /api/positions                增删持仓 {"code","cost","weight","action"}
  GET  /api/health
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import market          # noqa: E402
import models          # noqa: E402
import ms_engine as ms # noqa: E402  梅森体系引擎

WEB = os.path.join(HERE, "web")
DATA = os.path.join(HERE, "data")
WATCHLIST = os.path.join(DATA, "watchlist.json")
POSITIONS = os.path.join(DATA, "positions.json")
CACHE_TTL = 90
MAX_COMPARE = 30
_cache = {}
_cache_lock = threading.Lock()

DEFAULT_WATCHLIST = ["600519", "300750", "002594", "601127", "600030"]

# 通用兜底文案：任何非 DataSourceError 的异常都只说这一句，
# 细节（类型、堆栈、原始 message）只进服务端日志，永不出现在 web 界面。
GENERIC_ERROR = "这次没算出来，请稍后重试或换一个代码"


def _fix_path(raw: str) -> str:
    """http.server 把 path 按 latin-1 解码，中文参数会变乱码；这里还原成 utf-8。"""
    try:
        return raw.encode("latin-1").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return raw


def user_error(exc: BaseException) -> str:
    """把异常翻译成可以直接展示给用户的文案。"""
    if isinstance(exc, market.DataSourceError):
        return str(exc)
    traceback.print_exc()
    return GENERIC_ERROR


def analyze(code: str) -> dict:
    key = code.strip().lower()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]
    ctx = market.build_context(code)
    ev = models.evaluate(ctx)
    payload = {
        "ok": True,
        "ctx": {k: v for k, v in ctx.items()
                if k not in ("bars_full", "events_raw")},
        "result": ev,
        "accuracy_note": "机械口径检测，仅覆盖可量化的部分；筹码分布与题材级别需人工确认。",
    }
    with _cache_lock:
        _cache[key] = (now, payload)
    return payload


def compare(codes: list[str]) -> dict:
    """多票横向对比。并发拉取，最多 MAX_COMPARE 只，返回真实总数便于前端提示。"""
    total = len(codes)
    codes = codes[:MAX_COMPARE]
    workers = max(1, min(8, len(codes)))

    def one(c):
        try:
            p = analyze(c)
            ctx, plan = p["ctx"], p["result"]["plan"]
            return {
                "code": ctx["code"], "name": ctx["name"],
                "close": ctx["close"], "chg": round(ctx["chg"], 2),
                "trend": ctx["trend"], "position": ctx["position"],
                "bias60": round(ctx["bias60"], 1),
                "model": plan["model"], "level": plan["level"],
                "decision": plan["decision"], "tone": plan["tone"],
                "grade": plan["grade"], "cap": plan["cap_max"],
                "cap_now": plan["cap_now"],
                "events": len(ctx["recent_events"]),
                "score": p["result"]["models"][0]["score"] if p["result"]["models"] else 0,
            }
        except Exception as exc:  # noqa: BLE001
            return {"code": c, "error": user_error(exc)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(one, codes))

    ok = [r for r in rows if "error" not in r]

    def rank(r):
        # 可交易性优先，其次模型等级，再比模型得分与活跃度
        dec = {"可试仓": 3, "观察待确认": 2, "观察区": 1, "规避": 0}.get(r["decision"], 0)
        lv = 2 if r["level"] == "标准版" else 1 if r["level"] == "弱化版" else 0
        return (dec, lv, r["score"], r["events"])
    ok.sort(key=rank, reverse=True)
    rows = ok + [r for r in rows if "error" in r]
    return {"ok": True, "rows": rows, "total": total,
            "shown": len(rows), "limit": MAX_COMPARE,
            "truncated": total > MAX_COMPARE}


def load_watchlist() -> list[str]:
    try:
        with open(WATCHLIST, encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, list) and d:
                return d
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001
        pass
    return list(DEFAULT_WATCHLIST)


def save_watchlist(codes: list[str]) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(WATCHLIST, "w", encoding="utf-8") as f:
        json.dump(codes, f, ensure_ascii=False, indent=2)



# ---------------------------------------------------------------- 持仓管理
#
# 口径（risk.md）：
#   开仓时必须写明止损位 —— 建仓时把「结构位与 -12% 取先到者」落库，
#   之后每天用现价对比这个已锁定的止损位，而不是随行情漂移。
#   离场优先级：止损触发 > 跌破中期组清仓 > 跌破短期组减仓 > 止盈区 > 模型转弱。

STATUS_ORDER = ["止损触发", "破位清仓", "减仓预警", "止盈区", "模型转弱", "持有"]


def load_positions() -> list[dict]:
    try:
        with open(POSITIONS, encoding="utf-8") as f:
            d = json.load(f)
            return d if isinstance(d, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_positions(rows: list[dict]) -> None:
    os.makedirs(DATA, exist_ok=True)
    with open(POSITIONS, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def position_state(pos: dict) -> dict:
    """把一条持仓和最新行情合并成盯盘状态。"""
    p = analyze(pos["code"])
    ctx, plan = p["ctx"], p["result"]["plan"]
    close = ctx["close"]
    cost = float(pos["cost"])
    weight = float(pos.get("weight") or 0)
    exit_price = float(pos.get("entry_stop") or round(cost * 0.88, 2))
    ma13, ma55 = ctx["ma"]["13"], ctx["ma"]["55"]
    bias = ctx["bias60"]
    has_model = plan["model"] != "无模型命中"

    if close <= exit_price:
        status, tone, action = "止损触发", "bad", f"现价已跌破 {exit_price:.2f}，按纪律无条件离场"
    elif close < ma55:
        status, tone, action = "破位清仓", "bad", f"跌破中期均线组 {ma55:.2f}（纪律：清仓）"
    elif close < ma13:
        status, tone, action = "减仓预警", "warn", f"跌破短期组 MA13 {ma13:.2f}（纪律：减仓）"
    elif bias >= 30:
        status, tone, action = "止盈区", "good", f"BIAS60 {bias:+.1f}%，进入 +30% 分批止盈区"
    elif not has_model:
        status, tone, action = "模型转弱", "warn", "当前无模型命中，按失效条件复核"
    else:
        status, tone, action = "持有", "good", f"{plan['model']} {plan['level']}，结构未破"

    return {
        "code": ctx["code"], "name": ctx["name"], "cost": cost, "weight": weight,
        "close": close, "pl_pct": round((close / cost - 1) * 100, 2),
        "pl_amount_hint": round((close - cost) * float(pos.get("shares") or 0), 2)
        if pos.get("shares") else None,
        "exit_price": round(exit_price, 2),
        "exit_basis": pos.get("entry_stop_basis") or "开仓时锁定",
        "entry_warning": pos.get("entry_warning"),
        "dist_exit_pct": round((exit_price / close - 1) * 100, 2),
        "entry_model": pos.get("entry_model") or "—",
        "model": plan["model"], "level": plan["level"], "decision": plan["decision"],
        "ma13": round(ma13, 2), "ma55": round(ma55, 2), "bias60": round(bias, 1),
        "status": status, "tone": tone, "action": action,
        "opened_at": pos.get("opened_at"),
    }


def positions_summary(rows: list[dict]) -> dict:
    live = [r for r in rows if "error" not in r]
    if not live:
        return {"count": 0, "avg_pl": 0, "weight": 0, "alerts": 0, "over_cap": 0}
    return {
        "count": len(live),
        "avg_pl": round(sum(r["pl_pct"] for r in live) / len(live), 2),
        "weight": round(sum(r["weight"] for r in live), 1),
        "alerts": len([r for r in live if r["tone"] == "bad"]),
        "over_cap": len([r for r in live if r["weight"] > 20]),
    }


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **kw):
        super().__init__(*a, directory=WEB, **kw)

    def log_message(self, fmt, *args):  # 精简日志
        sys.stderr.write("[dash] %s\n" % (fmt % args))

    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, msg, status=400):
        self._json({"ok": False, "error": msg}, status)

    def do_GET(self):
        u = urlparse(_fix_path(self.path))
        q = parse_qs(u.query)
        try:
            if u.path == "/api/health":
                return self._json({"ok": True, "ts": time.strftime("%Y-%m-%d %H:%M:%S")})
            if u.path == "/api/analyze":
                code = (q.get("code") or [""])[0]
                if not code:
                    return self._err("缺少 code 参数")
                return self._json(analyze(code))
            if u.path == "/api/compare":
                codes = [x for x in (q.get("codes") or [""])[0].split(",") if x]
                if not codes:
                    return self._err("缺少 codes 参数")
                return self._json(compare(codes))
            if u.path == "/api/watchlist":
                return self._json({"ok": True, "codes": load_watchlist()})
            if u.path == "/api/positions":
                rows = []
                for pos in load_positions():
                    try:
                        rows.append(position_state(pos))
                    except Exception as exc:  # noqa: BLE001
                        rows.append({"code": pos.get("code"), "error": user_error(exc)})
                rows.sort(key=lambda r: STATUS_ORDER.index(r["status"]) if "status" in r else 99)
                return self._json({"ok": True, "rows": rows,
                                   "summary": positions_summary(rows)})
            # ---- 梅森交易体系
            if u.path == "/api/ms/overview":
                return self._json({"ok": True, **ms.overview()})
            if u.path == "/api/ms/sectors":
                return self._json({"ok": True, **ms.sectors()})
            if u.path == "/api/ms/stock":
                code = (q.get("code") or [""])[0].strip()
                if not code:
                    return self._err("缺少 code 参数")
                return self._json({"ok": True, **ms.stock(code)})
            if u.path == "/api/ms/reviews":
                return self._json({"ok": True, **ms.reviews()})
            if u.path == "/api/ms/sentiment":
                return self._json({"ok": True, **ms.sentiment()})
            if u.path == "/api/ms/scan/bottom":
                try:
                    limit = int((q.get("limit") or ["30"])[0])
                except ValueError:
                    limit = 30
                return self._json({"ok": True, **ms.bottom_scan(max(10, min(limit, 100)))})
            if u.path == "/api/ms/scan/top":
                name = (q.get("index") or ["上证"])[0]
                return self._json({"ok": True, **ms.top_signal(name)})
            if u.path == "/api/ms/superexpect":
                code = (q.get("code") or [""])[0].strip()
                date = (q.get("date") or [""])[0].strip()
                if not code or not date:
                    return self._err("缺少 code 或 date 参数")
                return self._json({"ok": True, **ms.superexpect(code, date)})
            if u.path == "/api/ms/intraday":
                code = (q.get("code") or [""])[0].strip()
                if not code:
                    return self._err("缺少 code 参数")
                return self._json({"ok": True, **ms.intraday(code)})
            if u.path == "/api/ms/plan":
                return self._json(ms.plan())
            if u.path.startswith("/api/"):
                return self._err(f"未知接口：{u.path}（若刚更新过代码，重启看板进程后再试）", 404)
        except Exception as exc:  # noqa: BLE001
            return self._err(user_error(exc),
                             400 if isinstance(exc, market.DataSourceError) else 500)
        return super().do_GET()

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        if not isinstance(body, dict):
            raise ValueError("body")
        return body

    def do_POST(self):
        u = urlparse(_fix_path(self.path))
        if u.path == "/api/ms/review":
            try:
                body = self._read_json()
                action = body.get("action", "add")
                if action == "del":
                    return self._json(ms.del_review(int(body.get("id") or 0)))
                return self._json(ms.add_review(body))
            except Exception as exc:  # noqa: BLE001
                return self._err(user_error(exc), 400)
        if u.path == "/api/ms/plan":
            try:
                body = self._read_json()
                action = body.get("action")
                if action == "del":
                    return self._json(ms.del_plan(int(body.get("id") or 0)))
                if action == "del-md":
                    return self._json(ms.del_plan_md(str(body.get("code") or "")))
                return self._json({"ok": True, "item": ms.add_plan(body)})
            except Exception as exc:  # noqa: BLE001
                return self._err(user_error(exc), 400)
        if u.path == "/api/ms/make-plan":
            try:
                body = self._read_json()
                made = ms.make_plan(
                    str(body.get("code") or ""),
                    float(body.get("account") or 1_000_000),
                    float(body.get("weight") or 15),
                    float(body["trigger"]) if body.get("trigger") else None,
                    float(body["stop"]) if body.get("stop") else None,
                    str(body.get("kind") or "回踩"),
                    str(body.get("note") or ""),
                )
                try:
                    ms.add_plan({"code": made["row"]["code"], "kind": body.get("kind") or "回踩",
                                 "trigger": made["row"]["trigger"], "stop": made["row"]["stop"],
                                 "weight": f'{made["row"]["weight"]:g}%',
                                 "note": f'由个股页生成 · {made["file"]}'})
                except Exception:  # noqa: BLE001
                    pass
                return self._json({"ok": True, **made})
            except Exception as exc:  # noqa: BLE001
                return self._err(user_error(exc), 400)
        if u.path not in ("/api/watchlist", "/api/positions"):
            return self._err("未知接口", 404)
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                return self._err("请求内容格式有误", 400)
            action = body.get("action", "add")
            raw_code = str(body.get("code", "")).strip()
            try:
                code = market.symbol_of(raw_code)[2:]
            except market.DataSourceError:
                # 删除时允许原样匹配，历史遗留的非法条目（如 12 位拼接码）也能清掉
                if action != "remove" or not raw_code:
                    raise
                code = raw_code.lower()
        except market.DataSourceError as exc:
            return self._err(str(exc), 400)
        except (ValueError, TypeError):
            return self._err("请求内容格式有误", 400)
        except Exception as exc:  # noqa: BLE001
            return self._err(user_error(exc), 500)

        if u.path == "/api/watchlist":
            try:
                codes = load_watchlist()
                if action == "add" and code not in codes:
                    codes.append(code)
                elif action == "remove":
                    codes = [c for c in codes if c != code]
                save_watchlist(codes)
                return self._json({"ok": True, "codes": codes})
            except Exception as exc:  # noqa: BLE001
                return self._err(user_error(exc), 500)

        # ---- 持仓
        try:
            rows = load_positions()
            if action == "remove":
                rows = [r for r in rows if r.get("code") != code]
                save_positions(rows)
                return self._json({"ok": True, "rows": rows})

            try:
                cost = float(body.get("cost") or 0)
                weight = float(body.get("weight") or 0)
                shares = float(body.get("shares")) if body.get("shares") else None
            except (TypeError, ValueError):
                return self._err("成本价、仓位、股数都需要填数字", 400)
            if cost <= 0:
                return self._err("成本价必须大于 0")
            if weight < 0 or weight > 100:
                return self._err("仓位百分比需在 0—100 之间")

            # 建仓即锁定止损：结构位与 -12% 取先到者（risk.md）
            p = analyze(code)
            ctx, plan = p["ctx"], p["result"]["plan"]
            struct = plan["stop"]["struct"]
            static_stop = round(cost * 0.88, 2)
            warning = None
            if not struct or float(struct) >= cost * 0.97:
                # 结构位不在成本下方 = 开仓时模型结构已失效，止损位失去意义
                entry_stop = static_stop
                basis = "12% 静态止损" + ("（结构位高于成本，模型已失效）" if struct else "")
                if struct:
                    warning = f"建仓时结构位 {float(struct):.2f} 高于成本 {cost:.2f}，模型已失效"
            else:
                entry_stop = round(max(float(struct), static_stop), 2)
                basis = plan["stop"]["basis"]

            entry = {
                "code": ctx["code"], "name": ctx["name"], "cost": cost,
                "weight": weight, "shares": shares,
                "opened_at": body.get("opened_at") or time.strftime("%Y-%m-%d"),
                "entry_stop": entry_stop, "entry_stop_basis": basis,
                "entry_model": plan["model"], "entry_warning": warning,
            }
            rows = [r for r in rows if r.get("code") != code] + [entry]
            save_positions(rows)
            return self._json({"ok": True, "entry": entry, "rows": rows})
        except Exception as exc:  # noqa: BLE001
            return self._err(user_error(exc),
                             400 if isinstance(exc, market.DataSourceError) else 500)


def _warm_cache() -> None:
    """启动后台预热：梅森板块接口首次拉取约 20s，预热后首屏不再干等。"""
    for name, fn in (("overview", ms.overview), ("sectors", ms.sectors), ("sentiment", ms.sentiment)):
        try:
            fn()
            print(f"[warm] {name} ok", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[warm] {name} 跳过：{type(exc).__name__}", flush=True)


def main():
    port = int(os.environ.get("PORT", "8777"))
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"看板已启动: http://127.0.0.1:{port}", flush=True)
    threading.Thread(target=_warm_cache, daemon=True).start()
    srv.serve_forever()


if __name__ == "__main__":
    main()
