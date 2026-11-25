/* 梅森体系 · 第二批页面：复盘 / 消息 / 扫描 / 计划生成 */
'use strict';
(function () {
  const { api, $, esc, fmt, pct } = window.MS;
  const ST = window.MS.state;
  const toneCls = (t) => ({ good: 'good', warn: 'warn', bad: 'bad', dim: 'dim' }[t] || 'dim');

  /* ------------------------------------------------ 复盘（A1/A2） */
  let TAG_LIST = [], SEL_TAGS = new Set();

  async function loadReviews() {
    $('rvStats').innerHTML = '<div class="card empty-note">加载中…</div>';
    try {
      const d = await api('/api/ms/reviews');
      ST.reviews = d;
      TAG_LIST = d.stats.tags || [];
      renderTagPicker();
      renderStats(d.stats, d.rows);
      renderList(d.rows);
    } catch (e) {
      $('rvStats').innerHTML = `<div class="card empty-note">加载失败：${esc(e.message)}</div>`;
    }
  }

  function renderStats(st, rows) {
    const tags = (st.by_tag || []).map((t) => `<span class="pill warn">${esc(t.tag)} ×${t.n}</span>`).join(' ') || '<span class="empty-note">还没有数据</span>';
    const layers = (st.layers || []).map((L) => {
      const v = st.by_layer[L] || { '对': 0, '错': 0 };
      const tot = v['对'] + v['错'];
      const bad = tot ? Math.round(v['错'] / tot * 100) : 0;
      return `<div><span>${esc(L)}</span><b class="mono ${bad > 50 ? 'down' : ''}">错 ${v['错']} / 对 ${v['对']}</b></div>`;
    }).join('');
    const months = (st.by_month || []).map((m) =>
      `<div><span>${esc(m.month)}</span><b class="mono">${m.n} 笔 · 胜率 ${m.win}/${m.n} · 均值 ${m.avg}%</b></div>`).join('');
    $('rvStats').innerHTML = `
      <div class="card">
        <h3>复盘统计 <span class="tag">胜率只看纪律执行，不看单笔盈亏</span></h3>
        <div class="msstats">
          <div><b class="mono">${st.total}</b><span>总笔数</span></div>
          <div><b class="mono">${st.win_rate === null ? '—' : st.win_rate + '%'}</b><span>胜率</span></div>
          <div><b class="mono ${(st.avg_pl || 0) >= 0 ? 'up' : 'down'}">${st.avg_pl === null ? '—' : st.avg_pl + '%'}</b><span>平均收益</span></div>
        </div>
        <div style="margin-top:12px"><b style="font-size:12px;color:#93a2c4">错误标签 TOP</b><div style="margin-top:8px">${tags}</div></div>
        <div class="mskv" style="margin-top:12px">${layers}</div>
        ${months ? `<div class="mskv" style="margin-top:10px">${months}</div>` : ''}
        ${(st.by_tag && st.by_tag.length) ? `<div class="empty-note" style="margin-top:10px">出现最多的标签 = 当前最该改的那一条</div>` : ''}
      </div>`;
  }

  function renderList(rows) {
    if (!rows.length) { $('rvList').innerHTML = '<div class="card empty-note">还没有复盘记录，先在上面记一笔。</div>'; return; }
    let html = `<div class="card"><h3>复盘记录 <span class="tag">最近 ${Math.min(rows.length, 20)} 条</span></h3>
      <table class="mstable"><thead><tr><th>日期</th><th>标的</th><th>买点</th><th>结果</th><th>四层</th><th>标签</th><th>教训</th><th></th></tr></thead><tbody>`;
    rows.slice(0, 20).forEach((r) => {
      const L = r.layers || {};
      const ltxt = ['时机', '方向', '位置', '执行'].map((k) =>
        `<span class="pill ${L[k] === '错' ? 'bad' : 'good'}">${k[0]}${L[k] === '错' ? '✗' : '✓'}</span>`).join(' ');
      html += `<tr>
        <td class="mono">${esc(r.date || '')}</td>
        <td>${esc(r.name || r.code || '')}</td>
        <td>${esc(r.buy_type || '')}</td>
        <td class="mono ${(parseFloat(r.pl_pct) || 0) >= 0 ? 'up' : 'down'}">${r.pl_pct === undefined || r.pl_pct === '' ? '—' : r.pl_pct + '%'}</td>
        <td>${ltxt}</td>
        <td>${(r.tags || []).map((t) => `<span class="pill warn">${esc(t)}</span>`).join(' ') || '—'}</td>
        <td class="empty-note" style="max-width:260px">${esc(r.lesson || '')}</td>
        <td><button class="ghost" data-del="${r.id}">删</button></td>
      </tr>`;
    });
    html += '</tbody></table></div>';
    $('rvList').innerHTML = html;
    $('rvList').querySelectorAll('button[data-del]').forEach((b) => b.addEventListener('click', async () => {
      await api('/api/ms/review', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'del', id: Number(b.dataset.del) }) });
      loadReviews();
    }));
  }

  function renderTagPicker() {
    const box = $('rvTags');
    box.innerHTML = TAG_LIST.map((t) =>
      `<label class="${SEL_TAGS.has(t) ? 'on' : ''}" data-tag="${esc(t)}"><input type="checkbox" ${SEL_TAGS.has(t) ? 'checked' : ''}>${esc(t)}</label>`).join('');
    box.querySelectorAll('label[data-tag]').forEach((el) => {
      el.addEventListener('click', (ev) => {
        ev.preventDefault();
        const t = el.dataset.tag;
        SEL_TAGS.has(t) ? SEL_TAGS.delete(t) : SEL_TAGS.add(t);
        renderTagPicker();
      });
    });
  }

  async function saveReview() {
    const body = {
      code: ($('rvCode').value || '').trim(),
      date: $('rvDate').value || new Date().toISOString().slice(0, 10),
      buy_type: $('rvBuy').value, index_state: $('rvIdx').value, phase: $('rvPhase').value,
      weight: $('rvWeight').value, pl_pct: $('rvPl').value,
      layers: { 时机: $('rvL0').value, 方向: $('rvL1').value, 位置: $('rvL2').value, 执行: $('rvL3').value },
      tags: [...SEL_TAGS],
      lesson: ($('rvLesson').value || '').trim(),
    };
    if (!body.code) return window.MS.toast('先填标的');
    body.name = body.code;
    try {
      await api('/api/ms/review', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      window.MS.toast('已保存复盘');
      SEL_TAGS.clear(); $('rvLesson').value = ''; $('rvPl').value = '';
      renderTagPicker();
      loadReviews();
    } catch (e) { window.MS.toast('保存失败：' + esc(e.message)); }
  }

  /* ------------------------------------------------ 消息（D1/D2） */
  const QUAD = {
    'few|eps': ['第一象限', '买入价值（唯一确定的买点）', 'good', '少数人知道 + 直接影响业绩：可快速试错，短平快，但必须渠道可靠。'],
    'few|mood': ['第二象限', '可买可不买', 'warn', '少数人知道 + 影响行业情绪：小仓试错，最多看三天（消息很快公开）。'],
    'all|mood': ['第三象限', '卖出价值', 'bad', '大多数人都知道 + 只影响情绪：这是给持股者出货的机会，散户最容易在这里接盘。'],
    'all|eps': ['第四象限', '可买可不买（看持续性）', 'warn', '公开 + 直接影响业绩：短期有空间但持续性差，要看后续订单/业绩能否延续。'],
  };

  function calcQuad() {
    const key = $('nzGap').value + '|' + $('nzImpact').value;
    const [name, value, tone, text] = QUAD[key];
    const d = $('nzDate').value;
    let fresh = '';
    if (d) {
      const days = Math.floor((Date.now() - new Date(d).getTime()) / 86400000);
      const left = 3 - days;
      fresh = days < 0 ? '消息日期在未来？'
        : left > 0 ? `保鲜期还剩约 ${left} 天（第 ${days} 天）` : `已过保鲜期（第 ${days} 天，1–3 天内有效）`;
    }
    $('nzResult').innerHTML = `
      <div class="msveto ${tone}"><div class="msveto-main">
        <div class="msveto-title">${name} · ${value}</div>
        <div class="empty-note" style="margin-top:6px">${text}</div>
        ${fresh ? `<div class="empty-note" style="margin-top:6px">${fresh}</div>` : ''}
      </div></div>
      <div class="empty-note" style="margin-top:8px">口诀：95% 的利好不是用来买股票的；普通投资者拿到的多是第三象限 → 卖出价值。</div>`;
  }

  function calcBeat() {
    const on = [...document.querySelectorAll('[data-beat]')].filter((x) => x.checked).length;
    const [tone, verdict, advice] = on === 4 ? ['good', '可以当主线做', '四要素齐备：可回踩买、可趋势持有。']
      : on >= 2 ? ['warn', '只能当题材做', '缺 E 或 T 的话，退潮后没有底：快进快出，不做长。']
      : ['bad', '不参与', '讲故事而已，没有业绩和容量，别用真金白银验证别人的想象力。'];
    $('beatResult').innerHTML = `<div class="msveto ${tone}"><div class="msveto-main">
      <div class="msveto-title">${on}/4 · ${verdict}</div>
      <div class="empty-note" style="margin-top:6px">${advice}</div></div></div>`;
  }

  async function checkSuper() {
    const code = ($('seCode').value || '').trim();
    const date = $('seDate').value;
    if (!code || !date) return window.MS.toast('填代码和消息日');
    $('seResult').innerHTML = '<div class="empty-note">判定中…</div>';
    try {
      const d = await api(`/api/ms/superexpect?code=${encodeURIComponent(code)}&date=${encodeURIComponent(date)}`);
      $('seResult').innerHTML = `
        <div class="msveto ${toneCls(d.tone)}"><div class="msveto-main">
          <div class="msveto-title">${esc(d.name)} · ${esc(d.verdict)}</div>
          <div class="empty-note" style="margin-top:6px">
            消息日 ${esc(d.date)} 当天 ${pct(d.msg_pct, 2)} · 次日 ${pct(d.d1, 2)} · 第3日 ${pct(d.d3, 2)} · 至今 ${pct(d.now, 2)}；
            均线 ${esc(d.state)}，距 MA20 ${pct(d.dist_ma20)}</div>
        </div></div>`;
    } catch (e) { $('seResult').innerHTML = `<div class="empty-note">判定失败：${esc(e.message)}</div>`; }
  }

  /* ------------------------------------------------ 扫描（E1/E2/E3） */
  async function loadSentiment() {
    $('scanSent').innerHTML = '<div class="card empty-note"><span class="loading"></span> 拉取涨停池…</div>';
    try {
      const d = await api('/api/ms/sentiment');
      ST.sent = d;
      const tone = d.temp >= 60 ? 'good' : d.temp >= 40 ? 'warn' : 'bad';
      const zt = (d.zt_top || []).map((x) => `<span class="pill good">${esc(x.name)} ${x.board}板</span>`).join(' ') || '—';
      $('scanSent').innerHTML = `
        <div class="card">
          <h3>市场情绪 <span class="tag">${esc(d.asof)}</span></h3>
          <div class="msstats">
            <div><b><span class="pill ${tone}">${esc(d.level)}</span></b><span>温度 ${d.temp}/100</span></div>
            <div><b class="mono up">${d.limit_up}</b><span>涨停家数</span></div>
            <div><b class="mono down">${d.limit_down}</b><span>跌停家数</span></div>
            <div><b class="mono">${d.max_board} 板</b><span>最高连板</span></div>
            <div><b class="mono ${(d.index_chg || 0) >= 0 ? 'up' : 'down'}">${pct(d.index_chg, 2)}</b><span>上证涨跌</span></div>
          </div>
          <div class="mskv" style="margin-top:12px">
            <div><span>连板梯队</span><b>${zt}</b></div>
          </div>
          <div class="empty-note" style="margin-top:8px">${esc(d.note || '')}</div>
        </div>`;
    } catch (e) {
      $('scanSent').innerHTML = `<div class="card empty-note">情绪取数失败：${esc(e.message)}</div>`;
    }
  }

  async function checkTop() {
    const idx = $('tpIdx').value;
    $('tpResult').innerHTML = '<div class="empty-note">检查中…</div>';
    try {
      const d = await api('/api/ms/scan/top?index=' + encodeURIComponent(idx));
      const rows = d.signals.map((s) => `<li><span class="pill ${toneCls(s.tone)}">${esc(s.kind)}</span> ${esc(s.text)}</li>`).join('');
      $('tpResult').innerHTML = `
        <div class="msveto ${d.verdict === '减仓' ? 'bad' : d.verdict === '警惕' ? 'warn' : 'good'}">
          <div class="msveto-main"><div class="msveto-title">${esc(d.index)} · ${esc(d.verdict)}</div>
          <div class="empty-note" style="margin-top:6px">${esc(d.date)} 收 ${fmt(d.close)} · ${esc(d.state)} · 5日 ${pct(d.ret5)} · 20日 ${pct(d.ret20)} · 5日量能/20日 ${d.vol5_vs_20}%</div></div>
        </div>
        <ul class="mslist" style="margin-top:10px">${rows}</ul>`;
    } catch (e) { $('tpResult').innerHTML = `<div class="empty-note">检查失败：${esc(e.message)}</div>`; }
  }

  async function runScan() {
    const limit = parseInt($('bsLimit').value || '30', 10);
    $('bsResult').innerHTML = `<div class="empty-note"><span class="loading"></span> 扫描中（行情源限流时较慢）…</div>`;
    try {
      const d = await api(`/api/ms/scan/bottom?limit=${limit}`);
      if (!d.rows.length) {
        $('bsResult').innerHTML = `<div class="empty-note">扫了 ${d.scanned} 只（${esc(d.source)}），没有符合条件的标的。
          说明当前市场还没出现「三天不新低 + 均线不再空头」的抄底结构——这本身是个结论。</div>`;
        return;
      }
      let html = `<table class="mstable"><thead><tr><th>代码</th><th>名称</th><th>均线</th><th>不新低</th><th>5日</th><th>20日</th><th>距MA20</th><th>现价</th></tr></thead><tbody>`;
      d.rows.forEach((r) => {
        html += `<tr><td class="mono">${esc(r.code)}</td><td>${esc(r.name)}</td>
          <td><span class="pill ${r.state === '多头排列' ? 'good' : 'warn'}">${esc(r.state)}</span></td>
          <td class="mono">${r.no_new_low} 天</td>
          <td class="mono ${(r.ret5 || 0) >= 0 ? 'up' : 'down'}">${pct(r.ret5)}</td>
          <td class="mono ${(r.ret20 || 0) >= 0 ? 'up' : 'down'}">${pct(r.ret20)}</td>
          <td class="mono">${pct(r.dist_ma20)}</td><td class="mono">${fmt(r.close)}</td></tr>`;
      });
      html += `</tbody></table><div class="empty-note" style="margin-top:8px">扫描 ${d.scanned} 只（${esc(d.source)}）· ${esc(d.asof)}。
        命中只是「结构候选」，还要看大盘时机与主线（03/07）。</div>`;
      $('bsResult').innerHTML = html;
    } catch (e) {
      $('bsResult').innerHTML = `<div class="empty-note">扫描失败：${esc(e.message)}（行情源限流时请稍后重试）</div>`;
    }
  }

  /* ------------------------------------------------ 计划生成（F1） */
  async function makePlan() {
    if (!ST.stock) return window.MS.toast('先在上面分析一只票');
    const body = {
      code: ST.stock.code,
      account: (parseFloat($('mpAccount').value || '100') || 100) * 1e4,
      weight: parseFloat($('mpWeight').value || '15') || 15,
      trigger: $('mpTrigger').value || null,
      stop: $('mpStop').value || null,
      kind: $('mpKind').value,
    };
    $('mpResult').innerHTML = '<div class="empty-note">生成中…</div>';
    try {
      const d = await api('/api/ms/make-plan', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body) });
      $('mpResult').innerHTML = `<div class="empty-note">已写入 plans/${esc(d.file)}（${d.row.shares} 股，最大亏损 ${d.row.loss} 元）</div>
        <pre class="rev-preview">${esc(d.markdown)}</pre>`;
      ST.plan = null;   // 让交易计划页重新加载
    } catch (e) { $('mpResult').innerHTML = `<div class="empty-note">生成失败：${esc(e.message)}</div>`; }
  }

  /* ------------------------------------------------ 绑定 */
  window.MSOnView = (view) => {
    if (view === 'review' && !ST.reviews) loadReviews();
    if (view === 'scan' && !ST.sent) loadSentiment();
  };

  document.addEventListener('DOMContentLoaded', () => {
    // 复盘（标签等到数据回来再渲染）
    $('rvDate').value = new Date().toISOString().slice(0, 10);
    $('rvSave').addEventListener('click', saveReview);
    // 消息
    $('nzDate').value = new Date().toISOString().slice(0, 10);
    ['nzGap', 'nzImpact', 'nzDate'].forEach((id) => $(id).addEventListener('change', calcQuad));
    document.querySelectorAll('[data-beat]').forEach((x) => x.addEventListener('change', calcBeat));
    $('seGo').addEventListener('click', checkSuper);
    $('seDate').value = new Date().toISOString().slice(0, 10);
    // 扫描
    $('tpGo').addEventListener('click', checkTop);
    $('bsGo').addEventListener('click', runScan);
    // 计划生成
    $('mpGo').addEventListener('click', makePlan);
    calcQuad(); calcBeat();
  });
})();
