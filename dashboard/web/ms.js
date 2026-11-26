/* 梅森交易体系 —— 看板前端（与量价时空模块共存，独立命名空间） */
'use strict';

(function () {
  const $ = (id) => document.getElementById(id);
  const fmt = (v, d = 2) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(d);
  const pct = (v, d = 1) => (v === null || v === undefined) ? '—' : (v >= 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const tone = (v) => v > 0 ? 'up' : v < 0 ? 'down' : '';
  const esc = (s) => String(s === undefined || s === null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const LF_TAB_KEY = 'lf_last_tab';
  const ST = { view: 'timing', ov: null, sec: null, plan: null, stock: null, code: localStorage.getItem('ms_code') || '601985' };

  async function api(path, opts) {
    const r = await fetch(path, opts);
    const j = await r.json().catch(() => ({ ok: false, error: 'HTTP ' + r.status }));
    if (!j.ok) throw new Error(j.error || '接口异常');
    return j;
  }

  function toast(msg) {
    if (window.toast) window.toast(msg); else console.log(msg);
  }

  /* ------------------------------------------------ 模式切换 */
  function setSys(sys) {
    document.querySelectorAll('#sysSwitch button').forEach((b) => b.classList.toggle('active', b.dataset.sys === sys));
    const toMs = sys === 'ms';
    $('msRoot').classList.toggle('hidden', !toMs);
    $('tabsLf').classList.toggle('hidden', toMs);
    document.querySelectorAll('main > section.view').forEach((s) => {
      if (toMs) { s.classList.add('hidden'); s.classList.remove('active'); }
      else { s.classList.remove('hidden'); s.classList.remove('active'); }   // 全部解除隐藏，避免切回后空白
    });
    document.body.dataset.sys = sys;
    if (toMs) {
      localStorage.setItem('ms_sys', 'ms');
      showMs(ST.view);
      if (!ST.ov) loadOverview();
    } else {
      localStorage.setItem('ms_sys', 'lf');
      // 回到切走前的那个页签（默认单票分析），并把画布按当前宽度重绘
      let tab = localStorage.getItem(LF_TAB_KEY) || 'analysis';
      try { if (STATE.tab && document.getElementById('view-' + STATE.tab)) tab = STATE.tab; } catch (e) { /* noop */ }
      if (!document.getElementById('view-' + tab)) tab = 'analysis';
      if (window.switchTab) window.switchTab(tab);
      else document.getElementById('view-' + tab).classList.add('active');
      if (ST.tab && typeof STATE !== 'undefined' && STATE.data && tab === 'analysis' && window.drawChart) {
        requestAnimationFrame(() => { try { window.drawChart(STATE.data.ctx); } catch (e) { /* noop */ } });
      }
    }
  }

  function showMs(view) {
    ST.view = view;
    document.querySelectorAll('#msTabs button').forEach((b) => b.classList.toggle('active', b.dataset.ms === view));
    document.querySelectorAll('.msview').forEach((s) => s.classList.toggle('active', s.id === 'msview-' + view));
    if (view === 'sectors' && !ST.sec) loadSectors();
    if (view === 'plan' && !ST.plan) loadPlan();
    if (view === 'intraday' && !ST.min) analyzeIntraday(ST.code);
    if (window.MSOnView) { try { window.MSOnView(view); } catch (e) { /* noop */ } }
    if (view === 'timing' && !ST.ov) loadOverview();
  }

  /* ------------------------------------------------ 大盘时机 */
  async function loadOverview() {
    $('msTimingBody').innerHTML = '<div class="empty-note"><span class="loading"></span> 拉取指数行情…</div>';
    try {
      ST.ov = await api('/api/ms/overview');
      renderOverview();
      $('msStatus').textContent = `梅森体系 · 数据 ${ST.ov.asof}`;
    } catch (e) {
      $('msTimingBody').innerHTML = `<div class="empty-note">取数失败：${esc(e.message)}</div>`;
    }
  }

  function pill(state) {
    const m = { '多头排列': ['good', '多头排列'], '空头排列': ['bad', '空头排列'],
                '均线粘合': ['warn', '均线粘合'], '缠绕': ['dim', '缠绕'] };
    const [cls, txt] = m[state] || ['dim', state || '—'];
    return `<span class="pill ${cls}">${esc(txt)}</span>`;
  }

  function renderOverview() {
    const d = ST.ov, v = d.verdict;
    const toneMap = { defense: 'bad', attack: 'good', probe: 'warn', wait: 'dim' };
    let html = `
      <div class="card msveto ${toneMap[v.level] || 'dim'}">
        <div class="msveto-main">
          <div class="msveto-title">${esc(v.text)}</div>
          <div class="empty-note" style="margin-top:6px">
            空头指数 ${v.down} / 多头指数 ${v.up} / 三天不新低确认 ${v.confirm} · 口径：03-timing.md + 10-ma-trend.md
          </div>
        </div>
        <button class="ghost" id="msRefreshOv">刷新</button>
      </div>
      <div class="card">
        <h3>指数均线三态 <span class="tag">5/10/20 均线 · 前复权日线</span></h3>
        <table class="mstable">
          <thead><tr><th>指数</th><th>收盘</th><th>今日</th><th>5日</th><th>20日</th><th>距MA20</th><th>均线</th><th>不新低</th></tr></thead>
          <tbody>`;
    for (const [name, s] of Object.entries(d.indices)) {
      html += `<tr>
        <td>${esc(name)}</td>
        <td class="mono">${fmt(s.close)}</td>
        <td class="mono ${tone(s.ret1)}">${pct(s.ret1, 2)}</td>
        <td class="mono ${tone(s.ret5)}">${pct(s.ret5, 2)}</td>
        <td class="mono ${tone(s.ret20)}">${pct(s.ret20, 2)}</td>
        <td class="mono ${tone(s.dist_ma20)}">${pct(s.dist_ma20)}</td>
        <td>${pill(s.state)}</td>
        <td class="mono">${s.no_new_low ? s.no_new_low + ' 天' : '—'}</td>
      </tr>`;
    }
    html += `</tbody></table>
      <div class="empty-note" style="margin-top:10px">
        体系口径：三大指数同时朝下 → 防守；出现三天不新低 → 只允许 1/6~1/5 试仓；均线联合朝上才进入波段级。
        单指数「不新低」= 连续收盘低点高于近 10 日低点。
      </div>
      <div class="card">
        <h3>关键位（否决线）<span class="tag">跌破即当日计划全部取消</span></h3>
        <div class="msstats">
          ${Object.entries(d.indices).map(([n, s]) => `
            <div><b class="mono">${fmt(s.swing_low)}</b><span>${esc(n)} · 近10日低点</span>
            <div class="empty-note">现价距此 ${s.close && s.swing_low ? pct((s.close / s.swing_low - 1) * 100) : '—'}</div></div>`).join('')}
        </div>
        <div class="empty-note" style="margin-top:10px">
          体系动作：任一指数跌破自己近 10 日低点 → 当天不进新仓；已持仓者按 04-stop-loss 先减仓控制回撤。
        </div>
      </div>`;
    $('msTimingBody').innerHTML = html;
    $('msRefreshOv').addEventListener('click', () => { ST.ov = null; loadOverview(); });
  }

  /* ------------------------------------------------ 板块 */
  async function loadSectors() {
    $('msSectorsBody').innerHTML = '<div class="empty-note"><span class="loading"></span> 拉取板块数据（首次约 10–20 秒）…</div>';
    try {
      ST.sec = await api('/api/ms/sectors');
      renderSectors();
    } catch (e) {
      $('msSectorsBody').innerHTML = `<div class="empty-note">取数失败：${esc(e.message)}</div>`;
    }
  }

  function renderSectors() {
    const d = ST.sec;
    const maxAbs = Math.max(...d.rows.map((r) => Math.abs(r.ret5 || 0)), 1);
    let html = `<div class="card">
      <h3>板块持续性 <span class="tag">按 5日 涨幅排序 · ${esc(d.asof)}${d.stale ? ' · 缓存' : ''}</span></h3>
      <table class="mstable">
        <thead><tr><th>板块</th><th>今日</th><th>5日</th><th>5日强度</th><th>60日</th><th>涨/跌</th><th>领涨</th></tr></thead><tbody>`;
    for (const r of d.rows) {
      const w = Math.round(Math.abs(r.ret5 || 0) / maxAbs * 100);
      html += `<tr>
        <td>${esc(r.name)}</td>
        <td class="mono ${tone(r.today)}">${pct(r.today, 2)}</td>
        <td class="mono ${tone(r.ret5)}">${pct(r.ret5, 2)}</td>
        <td><div class="bar"><i class="${r.ret5 >= 0 ? 'up' : 'down'}" style="width:${w}%"></i></div></td>
        <td class="mono ${tone(r.ret60)}">${pct(r.ret60, 1)}</td>
        <td class="mono">${r.up}/${r.dn}</td>
        <td>${esc(r.lead || '—')}</td>
      </tr>`;
    }
    html += `</tbody></table>
      <div class="empty-note" style="margin-top:10px">
        主线判定（02-mainline.md）：持续性 + 整体性（涨家数占比）+ 与大盘节奏一致。${esc(d.note || '')}
      </div></div>`;
    $('msSectorsBody').innerHTML = html;
  }

  /* ------------------------------------------------ 个股位置 */
  async function analyzeStock(code) {
    if (!code) return;
    $('msStockBody').innerHTML = '<div class="empty-note"><span class="loading"></span> 分析中…</div>';
    try {
      ST.stock = await api('/api/ms/stock?code=' + encodeURIComponent(code));
      ST.code = ST.stock.code;
      localStorage.setItem('ms_code', ST.code);
      renderStock();
    } catch (e) {
      $('msStockBody').innerHTML = `<div class="empty-note">分析失败：${esc(e.message)}</div>`;
    }
  }

  function renderStock() {
    const s = ST.stock;
    const toneCls = { good: 'good', warn: 'warn', bad: 'bad', dim: 'dim' }[s.tone] || 'dim';
    const sig = s.signals && s.signals.length
      ? s.signals.map((x) => `<li>${esc(x)}</li>`).join('')
      : '<li class="empty-note">暂无买点信号：不符合体系出手条件</li>';
    const html = `
      <div class="card">
        <div class="mshead">
          <div>
            <div class="title">${esc(s.name)} <span class="code">${esc(s.code)}</span></div>
            <div class="empty-note">数据 ${esc(s.date)} · 上证 20日 ${pct(s.index_ret20)}（${esc(s.index_state || '—')}）</div>
          </div>
          <div class="price mono">${fmt(s.close)}</div>
          <span class="pill ${toneCls}">${esc(s.zone)}</span>
        </div>
        <div class="msstats">
          <div><b>${pill(s.state)}</b><span>均线三态</span></div>
          <div><b class="mono ${tone(s.dist_ma20)}">${pct(s.dist_ma20)}</b><span>距 MA20</span></div>
          <div><b class="mono ${tone(s.ret5)}">${pct(s.ret5)}</b><span>5 日</span></div>
          <div><b class="mono ${tone(s.ret20)}">${pct(s.ret20)}</b><span>20 日</span></div>
          <div><b class="mono">${fmt(s.vol_ratio)}</b><span>量比</span></div>
          <div><b class="mono">${s.no_new_low} 天</b><span>不新低</span></div>
        </div>
      </div>
      <div class="grid2">
        <div class="card">
          <h3>买点信号 <span class="tag">三大买点 / 抄底结构</span></h3>
          <ul class="mslist">${sig}</ul>
          <div class="empty-note" style="margin-top:8px">
            双杀要求「大盘跌 + 个股跌」；当弱不弱要求大盘 20 日为负而个股为正。
          </div>
        </div>
        <div class="card">
          <h3>风险与仓位 <span class="tag">04-stop-loss · 05-position</span></h3>
          <div class="mskv">
            <div><span>止损位（结构位/-15% 取先到）</span><b class="mono">${fmt(s.stop)} <em class="${tone(s.stop_pct)}">${pct(s.stop_pct)}</em></b></div>
            <div><span>结构位（MA20）</span><b class="mono">${fmt(s.stop_struct)}</b></div>
            <div><span>-15% 定线</span><b class="mono">${fmt(s.stop_line)}</b></div>
            <div><span>建议仓位</span><b>${esc(s.cap)} <em class="empty-note">${esc(s.cap_note)}</em></b></div>
          </div>
        </div>
      </div>
      <div class="card">
        <h3>近 60 日走势 <span class="tag">收盘价</span></h3>
        <canvas id="msSpark" height="120"></canvas>
      </div>`;
    $('msStockBody').innerHTML = html;
    requestAnimationFrame(() => drawSpark(s.closes));
  }

  function drawSpark(vals) {
    const cv = $('msSpark');
    if (!cv || !vals || !vals.length) return;
    cv.style.width = '100%';
    const dpr = window.devicePixelRatio || 1;
    const w = cv.parentElement.clientWidth - 24 || 800, h = 120;
    cv.width = w * dpr; cv.height = h * dpr;
    const ctx = cv.getContext('2d');
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);
    const min = Math.min(...vals), max = Math.max(...vals);
    const x = (i) => 8 + i * (w - 16) / (vals.length - 1);
    const y = (v) => h - 12 - (v - min) / (max - min || 1) * (h - 24);
    ctx.beginPath();
    vals.forEach((v, i) => (i ? ctx.lineTo(x(i), y(v)) : ctx.moveTo(x(i), y(v))));
    ctx.strokeStyle = vals[vals.length - 1] >= vals[0] ? '#12b76a' : '#f04438';
    ctx.lineWidth = 2;
    ctx.stroke();
    ctx.lineTo(x(vals.length - 1), h - 4); ctx.lineTo(x(0), h - 4); ctx.closePath();
    ctx.fillStyle = 'rgba(96,165,250,.10)'; ctx.fill();
  }

  /* ------------------------------------------------ 交易计划 */
  async function loadPlan() {
    $('msPlanBody').innerHTML = '<div class="empty-note"><span class="loading"></span> 读取计划…</div>';
    try {
      ST.plan = await api('/api/ms/plan');
      renderPlan();
    } catch (e) {
      $('msPlanBody').innerHTML = `<div class="empty-note">读取失败：${esc(e.message)}</div>`;
    }
  }

  function renderPlan() {
    const p = ST.plan;
    if (!p.rows || !p.rows.length) {
      $('msPlanBody').innerHTML = `<div class="card"><h3>交易计划</h3>
        <div class="empty-note">${esc(p.note || '还没有计划')}</div></div>`;
      return;
    }
    let html = `<div class="card"><h3>交易计划 <span class="tag">${p.rows.length} 条 · 触发器实时校验</span></h3>
      <table class="mstable"><thead><tr>
        <th>标的</th><th>性质</th><th>触发价</th><th>现价</th><th>仓位</th><th>止损</th><th>状态</th><th>来源</th><th></th>
      </tr></thead><tbody>`;
    for (const r of p.rows) {
      const t = { good: 'good', warn: 'warn', bad: 'bad', dim: 'dim' }[r.tone] || 'dim';
      html += `<tr>
        <td>${esc(r.name)} <span class="code">${esc(r.code)}</span></td>
        <td>${esc(r.kind || '—')}</td>
        <td class="mono">${esc(r.trigger_text || (r.trigger ? r.trigger.join('–') : '—'))}</td>
        <td class="mono">${fmt(r.close)}</td>
        <td class="mono">${esc(r.weight || '—')}</td>
        <td class="mono">${fmt(r.stop)}</td>
        <td><span class="pill ${t}">${esc(r.status || '—')}</span></td>
        <td class="empty-note">${esc(r.source || '')}</td>
        <td>${r.id ? `<button class="ghost" data-pland="${r.id}">删</button>` : ''}</td>
      </tr>`;
    }
    html += `</tbody></table>
      <div class="empty-note" style="margin-top:10px">
        规则：跌破止损 → 取消；进入触发区间 → 可试仓；高于触发价 → 等回踩，不追高（07-buy-points.md）。
        「手动」来自本页添加或个股页生成，「plans 文件」来自 plans/*.md。
      </div>
      <div style="margin-top:10px"><button class="ghost" id="msRefreshPlan">刷新</button></div></div>`;
    $('msPlanBody').innerHTML = html;
    $('msRefreshPlan').addEventListener('click', () => { ST.plan = null; loadPlan(); });
    $('msPlanBody').querySelectorAll('button[data-pland]').forEach((b) => b.addEventListener('click', async () => {
      try {
        await api('/api/ms/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'del', id: Number(b.dataset.pland) }) });
        ST.plan = null; loadPlan();
      } catch (e) { toast('删除失败：' + e.message); }
    }));
  }

  async function addPlanFromForm() {
    const code = ($('plCode').value || '').trim();
    if (!code) return toast('先填代码');
    const raw = ($('plTrigger').value || '').trim();
    const m = raw.match(/(\d+(?:\.\d+)?)\s*[-–~]\s*(\d+(?:\.\d+)?)/);
    const trigger = m ? [parseFloat(m[1]), parseFloat(m[2])]
      : raw ? [parseFloat(raw), parseFloat(raw)] : null;
    try {
      await api('/api/ms/plan', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          code, kind: $('plKind').value, trigger,
          weight: ($('plWeight').value || '') + '%',
          stop: $('plStop').value || null, note: ($('plNote').value || '').trim(),
        }) });
      $('plCode').value = ''; $('plTrigger').value = ''; $('plStop').value = ''; $('plNote').value = '';
      ST.plan = null; loadPlan();
      toast('已添加计划');
    } catch (e) { toast('添加失败：' + e.message); }
  }

  /* ------------------------------------------------ 自检清单 */
  const CHECKS = [
    ['时机', ['大盘处于下跌/震荡/上涨？我是否说清了取的是哪一段势能',
              '三大指数是否同时朝上？不是的话，总仓是否 ≤ 35%',
              '是否出现「三天不新低」或「均线联合朝上」']],
    ['方向', ['是主线还是题材？BEAT 四要素成立几条',
              '板块处于主升/盘整/回落段？',
              '买的是龙头还是跟风？回落段之后不做']],
    ['位置', ['命中哪类买点：双杀 / 当弱不弱 / 回踩 / 形态',
              '5/10/20 均线是朝上、缠绕还是朝下？朝下不做',
              '周线级别确认过吗']],
    ['风险', ['定线止损（-15%）写下来了吗',
              '定量止损额 = 手笔×15% 算了吗',
              '持仓只数是否超上限（100万内≤3只）',
              '这是试仓还是盈利加仓？加的是盈利标的吗']],
    ['层次感', ['这笔操作是否违反纪律',
               '不处理会破坏账户全红吗',
               '我的主观看法是否在推翻上面两条']],
  ];

  function renderChecklist() {
    const saved = JSON.parse(localStorage.getItem('ms_checks') || '{}');
    let html = '';
    for (const [group, items] of CHECKS) {
      html += `<div class="card"><h3>${esc(group)}</h3><ul class="mscheck">`;
      items.forEach((it, i) => {
        const id = group + '-' + i;
        html += `<li><label><input type="checkbox" data-ck="${esc(id)}" ${saved[id] ? 'checked' : ''}> ${esc(it)}</label></li>`;
      });
      html += '</ul></div>';
    }
    const total = CHECKS.reduce((n, g) => n + g[1].length, 0);
    const done = Object.values(saved).filter(Boolean).length;
    $('msCheckBody').innerHTML = `<div class="card msveto ${done === total ? 'good' : 'dim'}">
        <div class="msveto-main"><div class="msveto-title">自检完成 ${done}/${total}</div>
        <div class="empty-note">全部勾选才允许下单（15-checklist.md）；未勾选的项就是你不敢下单的原因</div></div>
        <button class="ghost" id="msResetCk">重置</button></div>` + html;
    $('msCheckBody').querySelectorAll('input[data-ck]').forEach((el) => {
      el.addEventListener('change', () => {
        const cur = JSON.parse(localStorage.getItem('ms_checks') || '{}');
        cur[el.dataset.ck] = el.checked;
        localStorage.setItem('ms_checks', JSON.stringify(cur));
        const n = Object.values(cur).filter(Boolean).length;
        $('msCheckBody').querySelector('.msveto-title').textContent = `自检完成 ${n}/${total}`;
      });
    });
    $('msResetCk').addEventListener('click', () => {
      localStorage.removeItem('ms_checks'); renderChecklist();
    });
  }

  window.msSetSys = setSys;   // 便于调试与冒烟测试
  window.MS = { api, $, esc, fmt, pct, toast, state: ST, drawSpark };

  /* ------------------------------------------------ 初始化 */
  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('#sysSwitch button').forEach((b) =>
      b.addEventListener('click', () => setSys(b.dataset.sys)));
    document.querySelectorAll('#msTabs button').forEach((b) =>
      b.addEventListener('click', () => showMs(b.dataset.ms)));
    document.querySelectorAll('#tabsLf button').forEach((b) =>
      b.addEventListener('click', () => localStorage.setItem(LF_TAB_KEY, b.dataset.view)));
    $('msGoBtn').addEventListener('click', () => analyzeStock($('msCode').value.trim()));
    $('msCode').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('msGoBtn').click(); });
    $('msCode').value = ST.code;
    $('msTCode').value = ST.code;
    $('msTGo').addEventListener('click', () => analyzeIntraday($('msTCode').value.trim()));
    $('plAdd').addEventListener('click', addPlanFromForm);
    $('msTCode').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('msTGo').click(); });
    renderChecklist();
    const qp = new URLSearchParams(location.search);
    const sys = qp.get('sys') || localStorage.getItem('ms_sys');
    const view = qp.get('view');
    if (qp.get('code')) { ST.code = qp.get('code'); localStorage.setItem('ms_code', ST.code); }
    if (view) ST.view = view;
    if (sys === 'ms') setSys('ms');
    if (view === 'intraday') {
      const c0 = qp.get('code') || ST.code;
      $('msTCode').value = c0;
      analyzeIntraday(c0);
    } else if (view === 'stock' || qp.get('code')) {
      const c = qp.get('code') || ST.code;
      $('msCode').value = c;
      analyzeStock(c);
    }
    window.addEventListener('resize', () => { if (ST.stock) drawSpark(ST.stock.closes); });
  });
})();
