# 梅森交易体系 · meisen-trading-system

> 把「梅森（巴叔）· 梅家圈」系统课的内容，整理成一套可执行、可校验、可自动跑的 A 股交易体系，
> 同时打包为 DSH Skill（`SKILL.md` + `references/` + `assets/`）。

```
先占时机 → 后占逻辑 → 最后占位置
```

- **方法论**：19 个课程视频（约 7.7 小时）逐字转录 + 官方思维导图，交叉整理为 17 个模块
- **可执行**：每个模块都落到触发条件、仓位比例、止损位、证伪条件
- **可校验**：`scripts/ms_check.py` 盘中直接判断「否决线 / 买点 / 止损」是否触发
- **可测试**：`tests/test_skill.py` 离线校验结构完整性（CI 已接入）

---

## 一、体系速览

```
时机（大盘势能：双涨双跌 / 取势）
  └─ 方向（主线四特征 + BEAT 法则 + 利好四象限）
       └─ 位置（三大买点 + 5/10/20 均线 + 热点三段）
            └─ 执行（撩妹法则：试仓 → 盈利加仓 → 严格止损）
                 └─ 约束（层次感：纪律 > 仓位管理 > 主观认知）
                      └─ 目标（账户全红，风险敞口朝上）
```

| 层级 | 回答什么 | 关键文件 |
|---|---|---|
| 哲学 | 市场为什么这样运行 | `references/01-framework.md` |
| 研究 | 买什么方向 | `references/02-mainline.md`、`references/13-beat.md` |
| 交易 | 何时、什么价、多少仓 | `references/03-timing.md` ~ `references/11-intraday.md` |
| 自我 | 我适合什么、怎么不重复犯错 | `references/14-self.md` |

## 二、仓库结构

```
meisen-trading-system/
├── SKILL.md                  # 技能入口：使用顺序 / 十条原则 / 输出格式
├── references/               # 17 个方法论模块
│   ├── 01-framework.md       # 体系总纲（四层结构）
│   ├── 02-mainline.md        # 主线：四特征 / 扩散收敛 / 推倒重来
│   ├── 03-timing.md          # 时机感：双涨双跌、取势、买点分级
│   ├── 04-stop-loss.md       # 定线 -15% / 定量 = 手笔×15%
│   ├── 05-position.md        # 账户全红、持仓上限、加盈利减微利
│   ├── 05-position-layers.md # 层次感：纪律 > 仓位 > 主观
│   ├── 06-pickup-law.md      # 撩妹法则
│   ├── 07-buy-points.md      # 三大买点 + 两大卖点
│   ├── 08-signals.md         # 试错四信号
│   ├── 09-wave-pattern.md    # 热点三段 / 趋势三态
│   ├── 10-ma-trend.md        # 均线三态 + 大盘×个股矩阵
│   ├── 11-intraday.md        # 做T四图形 + 做T式加仓
│   ├── 12-bottom.md          # 抄底两结构 / 逃顶
│   ├── 13-beat.md            # BEAT 法则 + 利好四象限
│   ├── 14-self.md            # 投资周期 / 短线价值投机 / 中线波段
│   ├── 15-checklist.md       # 下单前 / 持仓中 / 平仓后 + 红黄牌
│   └── 16-course-notes.md    # 19 讲课程地图
├── assets/                   # 交易计划 / 持仓表 / 复盘表 / 一页速查卡
├── scripts/
│   ├── ms_data.py            # 行情数据层（腾讯日K + 东财板块）
│   └── ms_check.py           # 盘中触发器检查（否决线/买点/止损）
├── dashboard/                # 网页看板（双体系：量价时空 + 梅森，零依赖）
├── plans/                    # 真实跑过的交易计划（示例）
├── tests/test_skill.py       # 离线结构校验
├── install-skill.sh / .ps1   # 安装到 ${DSH_HOME}/skills
├── Makefile                  # make test / install / check / index / sectors
└── .github/workflows/ci.yml  # CI：结构校验
```

## 三、安装为 DSH Skill

```bash
make install          # 等价于 bash install-skill.sh → ~/.dsh/skills/meisen-trading-system
bash install-skill.sh --project    # 项目级：./.dsh/skills/
bash install-skill.sh --uninstall  # 卸载
```

Windows：

```powershell
powershell -ExecutionPolicy Bypass -File .\install-skill.ps1
```

安装后在 DSH 里直接说：

- 「用梅森体系分析一下 XX 股票 / XX 板块」
- 「按梅森体系写一份交易计划」
- 「按梅森体系复盘这笔交易」

## 四、网页看板（与量价时空共用）

`dashboard/` 是一个零依赖（Python 标准库）的本地看板，**顶部可切换「量价时空 / 梅森体系」**——
同一个应用里两套体系并存，梅森这边有 5 个页面：

| 页面 | 内容 |
|---|---|
| 大盘时机 | 三大指数均线三态、三天不新低、否决线 → 防守/试探/进攻 |
| 主线板块 | 板块今日/5日/60日、涨跌家数、领涨股（按 5 日强度排序） |
| 个股位置 | 均线三态、距 MA20 分区、三大买点信号、止损与建议仓位、60 日走势 |
| 日内做T | 分时价格/均价/大盘同步、急跌急涨信号、当日最强 T 机会、早盘双杀前置 |
| 交易计划 | 解析 `plans/*.md`，用实时价校验触发/等待/已破止损 |
| 体系自检 | 16 项下单前清单，勾选进度本地保存 |

```bash
cd dashboard
bash start.sh            # http://127.0.0.1:8777
PORT=9000 bash start.sh
```

深链：`/?sys=ms&view=timing`、`/?sys=ms&view=plan`、`/?sys=ms&view=stock&code=601985`

> 同一份 `dashboard/` 也随 `liuliu-trading-system` 仓库发布，两个仓库内容一致。

## 五、跑一次完整流程

**1）看时机（大盘）**

```bash
python3 scripts/ms_data.py index
```

输出上证 / 深成 / 创业板 / 科创50 的 5/10/20 均线状态、20 日涨跌、距 MA20。

**2）找主线（板块持续性）**

```bash
python3 scripts/ms_data.py sectors
```

按「今日 + 5 日 + 20 日 + 均线状态 + 涨跌家数」给板块排序，用于主线四特征检验。

**3）看个股**

```bash
python3 scripts/ms_data.py stock 601985 688172 688981
```

**4）盘中检查触发器**

```bash
python3 scripts/ms_check.py
```

输出：三大指数否决线是否跌破、每只票是否满足买点 / 是否破止损，并给出「执行 / 取消」结论。

**5）复盘**

交易结束后按 `assets/review.md` 填四层归因（时机 / 方向 / 位置 / 执行）。

> ⚠️ 本机 `git` 命令不可用（Xcode CLT 缺失）。仓库自带了基于 dulwich 的替代：
> `python3 scripts/git.py status|log|commit "msg"|remote <url>|push`。

> 完整示例见 [`plans/2026-11-25-交易计划.md`](plans/2026-11-25-交易计划.md)。

## 六、开发

```bash
make test      # 离线结构校验（与 CI 相同）
make check     # 盘中触发器检查（需联网）
make install   # 安装到 DSH skill 目录
```

CI：`.github/workflows/ci.yml`，push / PR 时运行 `python tests/test_skill.py`（Python 3.11/3.12，无网络依赖）。

## 七、数据源

| 用途 | 接口 | 说明 |
|---|---|---|
| 个股 / 指数日 K（前复权） | `web.ifzq.gtimg.cn`（腾讯） | 稳定，无需鉴权 |
| 实时行情 | `qt.gtimg.cn`（腾讯） | `ms_check.py` 使用 |
| 板块行情 / 成分 | `push2.eastmoney.com`（东财） | 偶发限流，脚本带重试 |

> 数据仅用于学习与研究；交易决策与风险由使用者自行承担。

## 八、免责声明

- 本项目是**个人学习笔记 + 工程化封装**。方法论与观点来源于第三方课程（梅森/巴叔《梅家圈》系统课）与课程官方思维导图，
  相关内容著作权归原作者所有；笔记仅供个人学习研究，**不得商用或再分发**（详见 `LICENSE`）。
- 所有规则均为概率工具，不是收益保证；**不构成任何投资建议**。
- 实盘前请用自己的资金属性、风险承受能力重新校准仓位与止损参数。

## 九、发布到 GitHub

本机 `git` 不可用，仓库自带两条发布路径（远端已设为 `git@github.com:lyuqy29/meisen-trading-system.git`）。

### 方式一：Deploy Key（当前采用）

前置两步（一次性）：

1. 在 https://github.com/new 新建空仓库 `meisen-trading-system`（**不要**勾 README / .gitignore / license）
2. 把 `../.deploy/id_ed25519.pub` 的内容加到 https://github.com/settings/keys

然后：

```bash
bash scripts/push_ssh.sh        # 自动检查认证 → 推 main 分支
```

### 方式二：Token

```bash
export GH_TOKEN=ghp_xxx         # classic token 勾 repo
python3 scripts/publish_github.py --dry-run
python3 scripts/publish_github.py    # 自动建仓 + 推送完整提交历史
```

## 十、Roadmap

- [ ] `ms_data.py` 板块成分股查询（东财限流兜底：本地缓存）
- [ ] `ms_check.py` 从 `plans/*.md` 解析计划参数，免手写阈值
- [ ] 「账户全红」持仓表自动核对（结构化 `assets/position-sheet.md`）
- [ ] 历史回测：对「双杀买点 / 当弱不弱」做信号胜率统计
