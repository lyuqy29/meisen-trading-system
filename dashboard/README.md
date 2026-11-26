# 双体系交易看板（量价时空 + 梅森）

把两套技能里的文字体系，变成能点、能看、能给结论的本地看板：

- **量价时空**（`liuliu-trading-system`）：九大模型、移动平均带、自选对比、持仓纪律
- **日内策略**（原「梅森体系」，仓库 `meisen-trading-system`）：时机/主线/买点/仓位/止损、日内做T、交易计划触发器、复盘、消息与扫描

顶部「量价时空 / 日内策略」一键切换，两套体系共用一套行情层与页面框架。

> 说明：界面上的「日内策略」= 仓库 `meisen-trading-system`（原名梅森体系）；
> 内部标识（`sys=ms`、`#msRoot`、`/api/ms/*`）保持不变，改的只是显示文案。

```bash
cd dashboard          # 仓库内是 dashboard/；本地工作区是 tools/dashboard
bash start.sh         # 默认 http://127.0.0.1:8777
PORT=9000 bash start.sh
```

深链（便于收藏/写进笔记）：

```
http://127.0.0.1:8777/?sys=ms&view=timing          # 大盘时机
http://127.0.0.1:8777/?sys=ms&view=sectors         # 主线板块
http://127.0.0.1:8777/?sys=ms&view=stock&code=601985
http://127.0.0.1:8777/?sys=ms&view=intraday&code=601985  # 日内做T
http://127.0.0.1:8777/?sys=ms&view=plan            # 交易计划触发器
http://127.0.0.1:8777/?sys=ms&view=check           # 体系自检
http://127.0.0.1:8777/?code=600519                 # 量价时空：单票分析
http://127.0.0.1:8777/?tab=positions               # 量价时空：持仓管理
```

## 页面

### 量价时空（4 页）

| 页面 | 作用 |
|---|---|
| **单票分析** | 输入代码 → 日 K → 均线带/BIAS/异动 → 九模型打分 → 交易计划（买点/仓位/止损/止盈/失效条件） |
| **自选对比** | 自选池横向排序：可交易性 > 模型等级 > 得分 > 活跃度，用于同板块选强 |
| **持仓管理** | 开仓即锁定止损位；每日对照：止损触发 / 破位清仓 / 减仓预警 / 止盈区 / 模型转弱 |
| **体系说明书** | 把 references 里的口径搬到界面上，便于对照 |

### 梅森体系（5 页）

| 页面 | 作用 | 对应引擎 |
|---|---|---|
| **大盘时机** | 三大指数均线三态 + 三天不新低 + 否决线 → 防守/试探/进攻结论 | `ms_engine.overview()` |
| **主线板块** | 板块今日/5日/60日涨跌、涨跌家数、领涨股，按 5 日强度排序 | `ms_engine.sectors()` |
| **个股位置** | 均线三态、距 MA20 分区（回踩/追高/破位）、三大买点信号、止损与建议仓位、60 日走势 | `ms_engine.stock()` |
| **交易计划** | 解析 `plans/*.md` 表格，用实时价校验「触发 / 等待 / 已破止损取消」 | `ms_engine.plan()` |
| **体系自检** | 16 项下单前自检（时机/方向/位置/风险/层次感），勾选进度本地保存 | `15-checklist.md` |

## 接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/analyze?code=` | 量价时空单票分析 |
| GET | `/api/compare?codes=a,b` | 多票对比 |
| GET/POST | `/api/watchlist` | 自选增删查 |
| GET/POST | `/api/positions` | 持仓增删查（建仓锁定止损） |
| GET | `/api/ms/overview` | 大盘时机 |
| GET | `/api/ms/sectors` | 板块持续性 |
| GET | `/api/ms/stock?code=` | 个股位置 |
| GET | `/api/ms/intraday?code=` | 日内做T（分时/均价/大盘同步/信号） |
| GET | `/api/ms/plan` | 交易计划 + 触发器状态 |
| GET | `/api/ms/reviews` | 复盘列表 + 统计 |
| POST | `/api/ms/review` | 新增 / 删除复盘 |
| GET | `/api/ms/sentiment` | 市场情绪（涨停池） |
| GET | `/api/ms/scan/top?index=` | 逃顶信号 |
| GET | `/api/ms/scan/bottom?limit=` | 抄底扫描 |
| GET | `/api/ms/superexpect?code=&date=` | 超预期判定 |
| POST | `/api/ms/make-plan` | 生成交易计划并写入 plans/ |
| GET | `/api/health` | 健康检查 |

## 数据源与降级

| 数据 | 来源 | 说明 |
|---|---|---|
| 指数/个股日 K | 腾讯 `web.ifzq.gtimg.cn`（前复权） | 稳定，无需鉴权 |
| 板块列表 | 东财 `push2.eastmoney.com` | 偶发限流，带重试 |
| 板块 K 线 | 东财 `push2his` | 当前网络下常被重置 → **20日/均线状态标注为「—」**，不伪造数据 |
| 板块快照 | `dashboard/data/ms_sectors.json` | 接口失败时回退上次成功结果（界面标注「缓存」） |
| 分时数据 | 腾讯 `appstock/app/minute/query` | 主板 cum_vol 单位为「手」、科创板/创业板为「股」，引擎按首行自动识别 |
| 涨停/跌停池 | 东财 `push2ex` | `tc`=家数、`lbc`=连板；涨跌家数接口不可用，温度用指数涨跌+涨跌停家数+最高板合成 |
| 日K 兜底 | 腾讯 ifzq → 新浪 → 腾讯 proxy | 单源被限流（HTTP 501/超时）时自动切换 |

## 功能开关

`web/ms.js` 顶部：

```js
const FEATURES = { plan: false };   // 交易计划：false = 关闭
```

关闭时隐藏：顶部「交易计划」页签、个股页「按体系生成交易计划」卡片；
`?view=plan` 深链会自动回落到「大盘时机」。

**数据不受影响**：`data/ms_plans.json` 与 `plans/*.md` 都还在，改回 `true` 即恢复原样。

## 做T怎么和持仓打通

`ms_engine.intraday()` 会读同一份 `data/positions.json`（与量价时空的持仓管理共用）：

- 找到该票 → 返回底仓成本、股数、仓位、锁定止损、浮动盈亏、距止损
- 页面据此生成计算器：**T 仓比例**（10/20/30/50%）× 底仓 → 可T股数（100 股整数倍）
- 两种情形：
  - **A 当日平T**：摊薄后成本 = 成本 − 毛收益 / 原股数
  - **B 转加仓**（做T式加仓）：新成本 = (成本×原股数 + 买价×T股数) / (原股数 + T股数)
- 纪律拦截：浮亏时红字提示「只允许当日平T，禁止做T式加仓」；日线非多头时提示「只做小仓T」

## 交易计划怎么接

`ms_engine.plan()` 读 `plans/` 下**最新**的 `.md`，按表头（标的/触发/仓位/止损）解析，
再用实时价判定状态。按 `assets/trade-plan.md` 的表格格式写计划，看板会自动校验。

查找顺序：`MS_PLANS_DIR` 环境变量 → `dashboard/plans` → `../plans`。

## 自测

`web/_smoke.html` 是一个切换冒烟页（同一服务下打开）：

```
http://127.0.0.1:8777/_smoke.html
```

它会加载看板 → 切到梅森 → 切回量价时空 → 依次点四个页签，输出每个 section 的 `hidden/active/高度`，
用于排查「切换后空白」这类前端问题。

## 免责

机械口径只覆盖可量化部分；筹码、题材级别、消息面需人工判断。**不构成投资建议。**
