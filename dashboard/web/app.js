/* 溜溜交易手册 —— 前端逻辑（无依赖） */
'use strict';

const $ = (id) => document.getElementById(id);
const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);
const pct = (v, d = 1) => (v === null || v === undefined) ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
const cls = (v) => v >= 0 ? 'up' : 'down';

/* 服务端已把技术异常换成中文文案，这里再兜一层：
   任何异常类型名、英文报错、堆栈、HTTP 状态码都不许出现在界面上。 */
const TECH = /TypeError|ValueError|KeyError|IndexError|AttributeError|RuntimeError|JSONDecode|Traceback|Exception|\bError\b|list indices|object has no attribute|could not convert|invalid literal|NoneType|not defined|unsupported operand|object of type|urllib|socket|ENOENT|EADDRINUSE|ECONN|Failed to fetch|NetworkError|HTTP \d{3}|127\.0\.0\.1:\d+/i;
function cleanError(msg) {
  const s = (msg === undefined || msg === null) ? '' : String(msg).trim();
  if (!s || TECH.test(s)) return '暂时没拿到数据，请稍后重试或换个代码';
  return s;
}

const STATE = { data: null, code: new URLSearchParams(location.search).get('code')
  || localStorage.getItem('lf_code') || '600519', watch: [], tab: 'analysis' };

/* ---------------------------------------------------------------- 通用 */

function toast(msg, ms = 2200) {
  const t = $('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(t._t);
  t._t = setTimeout(() => t.classList.remove('show'), ms);
}

async function api(path, opts) {
  const r = await fetch(path, opts);
  const j = await r.json().catch(() => ({ ok: false, error: `HTTP ${r.status}` }));
  if (!j.ok) throw new Error(cleanError(j.error || j.message));
  return j;
}

/* ---------------------------------------------------------------- 分析 */

async function analyze(code) {
  if (!code) return;
  $('status').innerHTML = '<span class="loading"></span> 拉取行情…';
  try {
    const d = await api('/api/analyze?code=' + encodeURIComponent(code));
    STATE.data = d;
    STATE.code = d.ctx.code;
    localStorage.setItem('lf_code', d.ctx.code);
    render(d);
    $('status').innerHTML = `<b>${d.ctx.name}</b> 数据截至 ${d.ctx.last_date}<br>机械口径 · 人工复核筹码与题材`;
  } catch (e) {
    $('status').textContent = '出错了';
    toast('分析失败：' + cleanError(e.message), 4000);
  }
}

function render(d) {
  const c = d.ctx, p = d.result.plan, r = d.result;
  const up = c.chg >= 0;

  /* 头部 */
  $('heroName').textContent = c.name;
  $('heroCode').textContent = `${c.symbol.toUpperCase()} · ${c.last_date} · ${c.position} · ${c.trend}`;
  $('heroPrice').textContent = fmt(c.close);
  $('heroPrice').style.color = up ? 'var(--up)' : 'var(--down)';
  $('heroChg').textContent = pct(c.chg);
  $('heroChg').style.color = up ? 'var(--up)' : 'var(--down)';
  $('heroBadge').innerHTML =
    `<span class="badge ${p.tone}">${p.decision}</span>` +
    ` <span class="badge dim">${p.model}</span>`;

  /* 位置与趋势 */
  $('kvTrend').textContent = c.trend;
  $('kvTrend').style.color = c.trend === '多头排列' ? 'var(--up)' : c.trend === '空头排列' ? 'var(--down)' : 'var(--dim)';
  $('kvPos').textContent = c.position;
  $('kvRange').innerHTML = `<span style="color:var(--down)">${fmt(c.drop_hi)}%</span> / <span style="color:var(--up)">${fmt(c.rise_lo)}%</span>`;
  $('kvVol').textContent = fmt(c.vol5_20);
  $('kvBias').textContent = pct(c.bias60);
  $('kvBias').style.color = c.bias60 < -20 ? '#3ddc97' : c.bias60 > 30 ? '#ff8a80' : 'var(--txt)';
  const left = Math.max(0, Math.min(100, (c.bias60 + 60) / 160 * 100));
  const nd = $('biasNeedle');
  nd.style.left = left + '%';
  nd.dataset.v = pct(c.bias60, 0);

  /* 九模型 */
  const grid = $('modelGrid');
  grid.innerHTML = '';
  (r.all_models || []).forEach((m) => {
    const k = m.status === '标准版' ? 'std' : m.status === '弱化版' ? 'weak'
      : m.status === '不成立' ? 'fail' : 'none';
    const el = document.createElement('div');
    el.className = 'model-cell ' + k;
    el.innerHTML = `<span class="nm">${m.name}</span><span class="st">${m.status}${m.passed ? ` · ${m.passed}/${m.total}` : ''}</span>`;
    grid.appendChild(el);
  });

  /* 要素核对 */
  const best = (r.models || [])[0];
  const cl = $('checksList');
  if (!best) {
    cl.innerHTML = '<span class="empty-note">无模型命中：按体系不做，等异动出现。</span>';
  } else {
    cl.innerHTML = `<div style="margin-bottom:10px;font-size:12.5px;color:var(--dim2)">
        ${best.name} · <b style="color:${best.level === '标准版' ? '#3ddc97' : '#fdb022'}">${best.level}</b>
        · ${best.passed}/${best.total} 项通过</div>` +
      best.checks.map((k) => {
        const icon = k.missing ? '○' : k.pass ? '✅' : '❌';
        const c2 = k.missing ? 'miss' : k.pass ? 'ok' : 'no';
        return `<div class="check ${c2}"><span class="ic">${icon}</span>
          <span><b>${k.name}</b><br><span class="ev">${k.evidence}</span></span></div>`;
      }).join('') +
      (best.note ? `<div class="empty-note" style="margin-top:8px">※ ${best.note}</div>` : '');
  }

  /* 交易计划 */
  $('planDecision').textContent = p.decision;
  $('planDecision').style.color = p.tone === 'good' ? '#3ddc97' : p.tone === 'warn' ? '#fdb022' : '#ff8a80';
  $('planGrade').textContent = `${p.grade} 级`;
  $('planGrade').className = 'badge ' + (p.grade === 'A' ? 'good' : p.grade === 'B' ? 'warn' : 'bad');
  $('planLevel').textContent = p.level;
  const reason = $('planReason');
  if (reason) reason.textContent = `依据：${c.trend} · ${c.position} · 模型 ${p.level}` +
    (p.veto.length ? ' · 触发否决项' : '');
  $('planLevel').className = 'badge ' + (p.level === '标准版' ? 'good' : p.level === '弱化版' ? 'warn' : 'dim');

  const invalid = !p.stop.valid;
  const rows = [
    ['买点类型', invalid ? '不适用（结构已破）' : p.model === '无模型命中' ? '不适用（无模型）' : p.buy_type],
    ['触发条件', invalid ? '不适用（结构已破，重新等信号）'
      : (p.trigger ? `${fmt(p.trigger)} 以上（${p.buy_desc}）` : p.buy_desc)],
    ['仓位', p.cap_max ? `试仓 ${p.cap_now}% · 上限 ${p.cap_max}%（${p.sizing.desc}）` : '0% — 空仓观察'],
    ['止损', invalid ? '结构位失效，不持仓即无止损问题'
      : `${fmt(p.stop.price)}（${p.stop.basis}，距现价 ${pct(p.stop.risk_pct)}）`],
    ['止盈', p.targets.map((t) => `${fmt(t.price)}(+${t.bias}%)`).join(' / ')],
    ['失效条件', p.model === '无模型命中' ? '无模型，不适用' : p.invalidation],
  ];
  $('planRows').innerHTML = rows.map(([k, v]) =>
    `<div class="kv"><span>${k}</span><span style="${k === '止损' ? 'color:#ff8a80' : k === '止盈' ? 'color:#3ddc97' : ''}">${v}</span></div>`).join('');

  const note = [];
  if (invalid) note.push('⚠ 结构位已高于现价：模型结构被跌破，按纪律不参与。');
  const otherVeto = p.veto.filter((v) => !(invalid && v.includes('结构止损位')));
  if (otherVeto.length) note.push('⚠ ' + otherVeto.join('；'));
  if (!invalid) note.push(`※ ${p.buy_desc}`);
  $('planNote').innerHTML = note.map((n) => `<div class="empty-note">${n}</div>`).join('');

  /* 否决与共振 */
  $('vetoBox').innerHTML = p.veto.length
    ? p.veto.map((v) => `<div class="veto-item">${v}</div>`).join('')
    : '<span class="empty-note">无否决项</span>';
  $('kvCombo').textContent = p.resonance.组合 || '无';
  $('kvEvents').textContent = (c.recent_events || []).length;

  /* 异动清单 */
  const evs = (c.recent_events || []).slice(-14).reverse();
  $('eventList').innerHTML = evs.length
    ? `<table class="wl"><thead><tr><th>日期</th><th>收盘</th><th>涨跌</th><th>量比</th><th>异动标签</th></tr></thead><tbody>` +
      evs.map((e) => `<tr><td class="mono">${e.dt}</td><td class="mono">${fmt(e.close)}</td>
        <td class="mono" style="color:${e.chg >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(e.chg, 2)}</td>
        <td class="mono">${fmt(e.vol_ratio)}x</td>
        <td>${e.tags.join(' · ')}</td></tr>`).join('') + '</tbody></table>'
    : '<span class="empty-note">近 60 日无异动：按体系「中性 K 线不解读」，不构成交易机会。</span>';

  drawChart(c);
}

/* ---------------------------------------------------------------- 图表 */

const MA_DEF = [
  ['ma5', '#f6c85f'], ['ma8', '#e879f9'], ['ma13', '#60a5fa'],
  ['ma55', '#34d399'], ['ma60', '#fb923c'], ['ma65', '#a78bfa'],
];

function drawChart(c) {
  const cv = $('chart');
  const wrap = $('chartWrap');
  const dpr = window.devicePixelRatio || 1;
  const w = wrap.clientWidth || 800;
  const h = 400;
  cv.width = w * dpr;
  cv.height = h * dpr;
  cv.style.height = h + 'px';
  const g = cv.getContext('2d');
  g.setTransform(dpr, 0, 0, dpr, 0, 0);
  g.clearRect(0, 0, w, h);

  const bars = c.chart.bars;
  const n = bars.length;
  const padL = 6, padR = 58, padT = 12;
  const priceH = h * 0.70;
  const volTop = h * 0.78, volH = h - volTop - 14;
  const plotW = w - padL - padR;
  const step = plotW / n;
  const cw = Math.max(1.4, step * 0.62);

  let lo = Infinity, hi = -Infinity;
  bars.forEach((b) => { lo = Math.min(lo, b.l); hi = Math.max(hi, b.h); });
  MA_DEF.forEach(([k]) => (c.chart[k] || []).forEach((v) => {
    if (v !== null && v !== undefined) { lo = Math.min(lo, v); hi = Math.max(hi, v); }
  }));
  const padP = (hi - lo) * 0.06 || 1;
  lo -= padP; hi += padP;
  const py = (v) => padT + (hi - v) / (hi - lo) * (priceH - padT);
  const px = (i) => padL + step * i + step / 2;

  /* 网格与价格轴 */
  g.font = '10px ui-monospace, Menlo, monospace';
  g.textAlign = 'left';
  for (let i = 0; i <= 4; i++) {
    const v = lo + (hi - lo) * i / 4;
    const y = py(v);
    g.strokeStyle = 'rgba(36,52,79,.55)';
    g.beginPath(); g.moveTo(padL, y); g.lineTo(w - padR, y); g.stroke();
    g.fillStyle = '#5f7391';
    g.fillText(v.toFixed(2), w - padR + 6, y + 3);
  }

  /* 成交量 */
  const vmax = Math.max(...bars.map((b) => b.v));
  bars.forEach((b, i) => {
    const bh = (b.v / vmax) * volH;
    const up = b.c >= b.o;
    g.fillStyle = up ? 'rgba(240,68,56,.55)' : 'rgba(18,183,106,.55)';
    g.fillRect(px(i) - cw / 2, volTop + volH - bh, cw, bh);
  });
  g.strokeStyle = 'rgba(36,52,79,.8)';
  g.beginPath(); g.moveTo(padL, volTop + volH); g.lineTo(w - padR, volTop + volH); g.stroke();
  g.fillStyle = '#5f7391';
  g.fillText('成交量', padL + 2, volTop + 10);

  /* K 线 */
  bars.forEach((b, i) => {
    const up = b.c >= b.o;
    g.strokeStyle = up ? '#f04438' : '#12b76a';
    g.fillStyle = up ? '#f04438' : '#12b76a';
    const x = px(i);
    g.beginPath();
    g.moveTo(x, py(b.h)); g.lineTo(x, py(b.l));
    g.lineWidth = 1;
    g.stroke();
    const y1 = py(Math.max(b.o, b.c)), y2 = py(Math.min(b.o, b.c));
    if (up) g.fillRect(x - cw / 2, y1, cw, Math.max(1, y2 - y1));
    else {
      g.fillRect(x - cw / 2, y1, cw, Math.max(1, y2 - y1));
    }
  });

  /* 均线 */
  MA_DEF.forEach(([k, color]) => {
    const arr = c.chart[k] || [];
    g.strokeStyle = color;
    g.lineWidth = 1.2;
    g.beginPath();
    let started = false;
    arr.forEach((v, i) => {
      if (v === null || v === undefined) return;
      const x = px(i), y = py(v);
      if (!started) { g.moveTo(x, y); started = true; } else g.lineTo(x, y);
    });
    g.stroke();
  });

  /* 异动标记 */
  (c.recent_events || []).forEach((e) => {
    if (e.idx === null || e.idx === undefined || e.idx < 0 || e.idx >= n) return;
    const x = px(e.idx);
    const b = bars[e.idx];
    const tag = e.tags.join('');
    let color = null;
    if (tag.includes('涨停')) color = '#fdb022';
    else if (tag.includes('跌停')) color = '#12b76a';
    else if (tag.includes('天量')) color = '#b78bff';
    if (!color) return;
    g.fillStyle = color;
    g.beginPath();
    g.arc(x, py(b.l) + 6, 2.4, 0, Math.PI * 2);
    g.fill();
  });

  /* 当前价横线 */
  const yc = py(c.close);
  g.setLineDash([4, 4]);
  g.strokeStyle = c.chg >= 0 ? 'rgba(240,68,56,.7)' : 'rgba(18,183,106,.7)';
  g.beginPath(); g.moveTo(padL, yc); g.lineTo(w - padR, yc); g.stroke();
  g.setLineDash([]);

  cv._geo = { px, py, step, padL, n, bars, lo, hi };
  bindHover(cv);
}

let hoverBound = false;
function bindHover(cv) {
  const tip = $('tooltip');
  if (hoverBound) return;
  hoverBound = true;
  cv.addEventListener('mousemove', (ev) => {
    const geo = cv._geo;
    if (!geo || !STATE.data) return;
    const c = STATE.data.ctx;
    const rect = cv.getBoundingClientRect();
    const x = ev.clientX - rect.left;
    let i = Math.round((x - geo.padL - geo.step / 2) / geo.step);
    i = Math.max(0, Math.min(geo.n - 1, i));
    const b = geo.bars[i];
    const prev = i > 0 ? geo.bars[i - 1].c : b.o;
    const chg = (b.c / prev - 1) * 100;
    const ma = {};
    ['ma5', 'ma8', 'ma13', 'ma55', 'ma60', 'ma65'].forEach((k) => { ma[k] = (c.chart[k] || [])[i]; });
    tip.innerHTML = `<b>${b.dt}</b><br>
      开 ${fmt(b.o)}　高 ${fmt(b.h)}<br>低 ${fmt(b.l)}　收 ${fmt(b.c)}<br>
      <span style="color:${chg >= 0 ? '#ff8a80' : '#3ddc97'}">${pct(chg, 2)}</span>　量 ${(b.v / 1e4).toFixed(1)} 万手<br>
      <span style="color:#8fa3bf">MA5 ${fmt(ma.ma5)} · MA13 ${fmt(ma.ma13)}<br>
      MA55 ${fmt(ma.ma55)} · MA60 ${fmt(ma.ma60)}</span>`;
    tip.style.display = 'block';
    const tx = Math.min(ev.clientX - rect.left + 14, rect.width - 190);
    tip.style.left = tx + 'px';
    tip.style.top = Math.max(4, ev.clientY - rect.top - 70) + 'px';
  });
  cv.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
}

/* ---------------------------------------------------------------- 自选 */

async function loadWatchlist() {
  try {
    const d = await api('/api/watchlist');
    STATE.watch = d.codes;
  } catch (e) { STATE.watch = []; }
}

async function renderWatchlist() {
  const tbl = $('wlTable');
  tbl.innerHTML = '<tr><td class="empty-note">加载中…</td></tr>';
  try {
    const d = await api('/api/compare?codes=' + encodeURIComponent(STATE.watch.join(',')));
    const rows = d.rows;
    let html = `<thead><tr>
      <th>#</th><th>名称</th><th>收盘</th><th>涨跌</th><th>趋势</th><th>位置</th>
      <th>BIAS60</th><th>命中模型</th><th>判定</th><th>仓位上限</th><th></th></tr></thead><tbody>`;
    rows.forEach((r, i) => {
      if (r.error) {
        html += `<tr><td>${i + 1}</td><td colspan="9" class="empty-note">${r.code} 读取失败：${cleanError(r.error)}</td><td></td></tr>`;
        return;
      }
      const tcls = r.trend === '多头排列' ? 'bull' : r.trend === '空头排列' ? 'bear' : '';
      html += `<tr class="row" data-code="${r.code}">
        <td class="mono" style="color:var(--dim2)">${i + 1}</td>
        <td><b>${r.name}</b><div style="color:var(--dim2);font-size:11px" class="mono">${r.code}</div></td>
        <td class="mono">${fmt(r.close)}</td>
        <td class="mono" style="color:${r.chg >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(r.chg, 2)}</td>
        <td><span class="trend-pill ${tcls}">${r.trend}</span></td>
        <td>${r.position}</td>
        <td class="mono" style="color:${r.bias60 < -20 ? '#3ddc97' : r.bias60 > 30 ? '#ff8a80' : 'var(--dim)'}">${fmt(r.bias60)}%</td>
        <td>${r.model}</td>
        <td><span class="badge ${r.tone}" style="padding:3px 9px;font-size:11.5px">${r.decision}</span></td>
        <td class="mono">${r.cap}%</td>
        <td><button class="ghost" data-del="${r.code}" style="padding:4px 9px;font-size:11.5px">移除</button></td>
      </tr>`;
    });
    html += '</tbody>';
    tbl.innerHTML = html;
    tbl.querySelectorAll('tr.row').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target.dataset.del) return;
        switchTab('analysis');
        $('codeInput').value = tr.dataset.code;
        analyze(tr.dataset.code);
      });
    });
    tbl.querySelectorAll('button[data-del]').forEach((b) => {
      b.addEventListener('click', async () => {
        await api('/api/watchlist', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: b.dataset.del, action: 'remove' }),
        });
        await loadWatchlist();
        renderWatchlist();
        toast('已移除 ' + b.dataset.del);
      });
    });
  } catch (e) {
    tbl.innerHTML = `<tr><td class="empty-note">加载失败：${cleanError(e.message)}</td></tr>`;
  }
}

/* ---------------------------------------------------------------- 持仓 */

async function renderPositions() {
  const tbl = $('posTable');
  const sum = $('posSummary');
  tbl.innerHTML = '<tr><td class="empty-note">加载中…</td></tr>';
  try {
    const d = await api('/api/positions');
    const s = d.summary;
    const cell = (k, v, color) => `<div class="pos-stat"><div class="k">${k}</div>
      <div class="v" style="${color ? 'color:' + color : ''}">${v}</div></div>`;
    sum.innerHTML =
      cell('持仓只数', s.count) +
      cell('平均浮盈', (s.avg_pl >= 0 ? '+' : '') + fmt(s.avg_pl) + '%',
        s.avg_pl === 0 ? 'var(--dim)' : s.avg_pl > 0 ? 'var(--up)' : 'var(--down)') +
      cell('总仓位', fmt(s.weight, 1) + '%', s.weight > 100 ? '#ff8a80' : '') +
      cell('风险预警', s.alerts + ' 只', s.alerts ? '#ff8a80' : '#3ddc97');

    if (!d.rows.length) {
      tbl.innerHTML = '<tr><td class="empty-note">还没有持仓。上面填代码 + 成本价，建仓即锁定止损位。</td></tr>';
      return;
    }
    let html = `<thead><tr>
      <th>名称</th><th>成本</th><th>现价</th><th>盈亏</th><th>仓位</th>
      <th>锁定止损</th><th>距止损</th><th>MA13 / MA55</th><th>当前模型</th><th>信号</th><th></th>
    </tr></thead><tbody>`;
    d.rows.forEach((r) => {
      if (r.error) {
        html += `<tr><td colspan="11" class="empty-note">${r.code} 读取失败：${cleanError(r.error)}</td></tr>`;
        return;
      }
      const cls = r.tone === 'bad' ? 'alert-row' : '';
      const over = r.weight > 20 ? ' over-cap' : '';
      html += `<tr class="row ${cls}" data-code="${r.code}">
        <td><b>${r.name}</b><div style="color:var(--dim2);font-size:11px" class="mono">${r.code} · ${r.entry_model}</div>
          ${r.entry_warning ? `<div style="color:#fdb022;font-size:11px;margin-top:3px">⚠ ${r.entry_warning}</div>` : ''}</td>
        <td class="mono">${fmt(r.cost)}</td>
        <td class="mono">${fmt(r.close)}</td>
        <td class="mono" style="color:${r.pl_pct >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(r.pl_pct, 2)}</td>
        <td class="mono${over}">${r.weight ? fmt(r.weight, 1) + '%' : '—'}</td>
        <td class="mono">${fmt(r.exit_price)}</td>
        <td class="mono" style="color:${r.dist_exit_pct > -3 ? '#ff8a80' : 'var(--dim)'}">${pct(r.dist_exit_pct, 1)}</td>
        <td class="mono" style="color:var(--dim2)">${fmt(r.ma13)} / ${fmt(r.ma55)}</td>
        <td style="font-size:12px">${r.model}<div style="color:var(--dim2);font-size:11px">${r.level}</div></td>
        <td><span class="pill ${r.tone}">${r.status}</span>
          <div style="color:var(--dim2);font-size:11px;margin-top:4px;max-width:220px">${r.action}</div></td>
        <td><button class="ghost" data-close="${r.code}" style="padding:4px 9px;font-size:11.5px">平仓</button></td>
      </tr>`;
    });
    html += '</tbody>';
    tbl.innerHTML = html;

    tbl.querySelectorAll('tr.row').forEach((tr) => {
      tr.addEventListener('click', (e) => {
        if (e.target.dataset.close) return;
        switchTab('analysis');
        $('codeInput').value = tr.dataset.code;
        analyze(tr.dataset.code);
      });
    });
    tbl.querySelectorAll('button[data-close]').forEach((b) => {
      b.addEventListener('click', async () => {
        await api('/api/positions', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: b.dataset.close, action: 'remove' }),
        });
        renderPositions();
        toast('已移除持仓 ' + b.dataset.close);
      });
    });
  } catch (e) {
    tbl.innerHTML = `<tr><td class="empty-note">加载失败：${cleanError(e.message)}</td></tr>`;
  }
}

/* ---------------------------------------------------------------- 交互 */

function switchTab(name) {
  STATE.tab = name;
  document.querySelectorAll('nav.tabs button').forEach((b) =>
    b.classList.toggle('active', b.dataset.view === name));
  document.querySelectorAll('section.view').forEach((s) =>
    s.classList.toggle('active', s.id === 'view-' + name));
  if (name === 'watchlist') renderWatchlist();
  if (name === 'positions') renderPositions();
  if (name === 'analysis' && STATE.data) drawChart(STATE.data.ctx);
}

document.addEventListener('DOMContentLoaded', async () => {
  document.querySelectorAll('nav.tabs button').forEach((b) =>
    b.addEventListener('click', () => switchTab(b.dataset.view)));

  $('goBtn').addEventListener('click', () => analyze($('codeInput').value.trim()));
  $('codeInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('goBtn').click(); });
  $('codeInput').value = STATE.code;

  $('addBtn').addEventListener('click', async () => {
    const code = $('codeInput').value.trim();
    if (!code) return toast('先输入代码');
    try {
      await api('/api/watchlist', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, action: 'add' }),
      });
      await loadWatchlist();
      toast('已加入自选：' + code);
    } catch (e) { toast('加入失败：' + cleanError(e.message)); }
  });

  $('wlAddBtn').addEventListener('click', async () => {
    const codes = $('wlInput').value.split(/[,，\s]+/).filter(Boolean);
    if (!codes.length) return toast('输入代码');
    try {
      for (const c of codes) {
        await api('/api/watchlist', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ code: c, action: 'add' }),
        });
      }
      $('wlInput').value = '';
      await loadWatchlist();
      renderWatchlist();
      toast('已加入 ' + codes.length + ' 只');
    } catch (e) { toast('加入失败：' + cleanError(e.message)); }
  });
  $('wlRefresh').addEventListener('click', renderWatchlist);

  $('posAdd').addEventListener('click', async () => {
    const code = $('posCode').value.trim();
    const cost = parseFloat($('posCost').value);
    const weight = parseFloat($('posWeight').value || '0');
    if (!code || !cost) return toast('代码和成本价必填');
    try {
      const r = await api('/api/positions', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code, cost, weight, action: 'add' }),
      });
      toast(`已建仓 ${r.entry.name}：锁定止损 ${r.entry.entry_stop}`);
      $('posCode').value = ''; $('posCost').value = ''; $('posWeight').value = '';
      renderPositions();
    } catch (e) { toast('建仓失败：' + cleanError(e.message)); }
  });

  await loadWatchlist();
  // 直接看梅森页时跳过量价时空的自动分析（?sys=ms 或 ?nolf=1），避免被慢行情拖住
  const skipLf = new URLSearchParams(location.search).get('sys') === 'ms'
    || new URLSearchParams(location.search).get('nolf');
  if (!skipLf) await analyze(STATE.code);
  const tabParam = new URLSearchParams(location.search).get('tab');
  if (tabParam) switchTab(tabParam);
  window.addEventListener('resize', () => { if (STATE.data) drawChart(STATE.data.ctx); });
});
