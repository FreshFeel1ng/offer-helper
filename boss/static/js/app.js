// ── Tab switching ──
document.addEventListener('DOMContentLoaded', function() {
  var nav = document.querySelector('nav.sidebar');
  if (!nav) { console.error('nav.sidebar not found in DOM'); return; }
  nav.addEventListener('click', function(e) {
    var a = e.target.closest('a[data-tab]');
    if (!a) return;
    e.preventDefault();
    switchTab(a.getAttribute('data-tab'));
  });
});

function switchTab(tab) {
  document.querySelectorAll('.tab').forEach(function(t) { t.style.display = 'none'; });
  var target = document.getElementById('tab-' + tab);
  if (target) target.style.display = 'block';
  document.querySelectorAll('nav a').forEach(function(a) { a.classList.remove('active'); });
  var nav = document.querySelector('nav a[data-tab="' + tab + '"]');
  if (nav) nav.classList.add('active');
  var titles = {
    search:'岗位搜索',applications:'投递记录',chat:'聊天',wechat:'微信记录',
    transfer:'转人工',settings:'设置',agent:'AI Agent',kb:'知识库管理',
    'qa-ask':'知识库问答',review:'模拟面试',assistant:'AI实时面试助手'
  };
  var el = document.getElementById('pageTitle');
  if (el) el.textContent = titles[tab] || '';

  // auto-load
  if (tab === 'applications') loadApplications();
  if (tab === 'chat') loadConversations();
  if (tab === 'settings') loadSettings();
  if (tab === 'wechat') loadWechatExchanges();
  if (tab === 'transfer') loadTransferRequests();
  if (tab === 'kb') loadKbStats();
  if (tab === 'review') { if (typeof initMockTab === 'function') initMockTab(); }
  if (tab === 'assistant') { if (typeof assistantCheckStatus === 'function') assistantCheckStatus(); }
}

// ── State ──
var _statusData = {}, _statsData = {}, _jobList = [], _convList = [];
var _ws = null;

function connectWS() {
  if (_ws) _ws.close();
  _ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
  _ws.onmessage = function(e) {
    try { var d = JSON.parse(e.data); if (d.type === 'connected') { _statusData = d.status; renderStatus(); } } catch(ex) {}
  };
  _ws.onclose = function() { setTimeout(connectWS, 3000); };
}

function renderStatus() {
  var r = _statusData || {};
  var b = document.getElementById('browserDot');
  if (b) b.className = r.browser_running ? 'dot on' : 'dot off';
  var bs = document.getElementById('browserStatus');
  if (bs) bs.textContent = r.browser_running ? '浏览器在线' : '浏览器离线';
  var ms = document.getElementById('monitorStatus');
  if (ms) ms.textContent = r.monitor_running ? '监控中' : '已停止';
  var md = document.getElementById('monitorDot');
  if (md) md.className = r.monitor_running ? 'dot on' : 'dot off';
}

function renderStats() {
  var s = _statsData || {};
  ['statToday','statPending','statReplied','statLimit'].forEach(function(id) {
    var el = document.getElementById(id); if (el) el.textContent = s[id.replace('stat','').toLowerCase()] || 0;
  });
  var el = document.getElementById('statToday'); if (el) el.textContent = (s.today || s.today_applications || 0);
  el = document.getElementById('statPending'); if (el) el.textContent = s.pending || 0;
  el = document.getElementById('statReplied'); if (el) el.textContent = s.replied || 0;
  el = document.getElementById('statLimit'); if (el) el.textContent = s.limit || 0;
}

function renderJobs() {
  var tbody = document.getElementById('appTableBody');
  if (!tbody) return;
  if (!_jobList.length) { tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:var(--text-3)">暂无数据</td></tr>'; return; }
  var h = '';
  _jobList.forEach(function(j) {
    h += '<tr><td>' + esc(j.job_title) + '</td><td>' + esc(j.company||'') + '</td><td>' + esc(j.salary||'') +
      '</td><td>' + esc(j.city||'') + '</td><td>' + esc(j.status||'') + '</td><td>' + (j.created_at||'').substring(0,10) + '</td></tr>';
  });
  tbody.innerHTML = h;
}

function renderConversations() {
  var list = document.getElementById('conversationList');
  if (!list) return;
  if (!_convList.length) { list.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-3)">暂无活跃会话</div>'; return; }
  var h = '';
  _convList.forEach(function(c) {
    h += '<div class="card" style="margin-bottom:8px;padding:10px 14px;"><div style="font-weight:500;">' + esc(c.hr_name||'') +
      ' <span style="font-size:10px;color:var(--text-3)">' + esc(c.hr_company||'') + '</span></div>' +
      '<div style="font-size:11px;color:var(--text-2)">' + esc(c.last_message_text||'') + '</div></div>';
  });
  list.innerHTML = h;
}

// ── Data loaders ──
async function getStatus() { try { var r = await fetch('/api/status'); _statusData = await r.json(); renderStatus(); } catch(e) {} }
async function getStats() { try { var r = await fetch('/api/stats'); _statsData = await r.json(); renderStats(); } catch(e) {} }
async function loadApplications() { try { var r = await fetch('/api/jobs?limit=500'); var d = await r.json(); _jobList = Array.isArray(d) ? d : (d.jobs||[]); renderJobs(); } catch(e) {} }
async function loadConversations() { try { var r = await fetch('/api/conversations'); _convList = await r.json(); renderConversations(); } catch(e) {} }

// ── BOSS 操作 ──
async function startSystem() {
  var btn = document.getElementById('sysStartBtn');
  if (btn) { btn.disabled = true; btn.textContent = '启动中...'; }
  try {
    var r = await fetch('/api/system/start', { method: 'POST' }); var d = await r.json();
    if (d.status === 'started' || d.status === 'already_started') { getStatus(); }
    else { alert('启动失败: ' + (d.message || d.status)); }
  } catch(e) { alert('启动失败: ' + e.message); }
  if (btn) { btn.disabled = false; btn.textContent = '启动浏览器'; }
}
async function stopSystem() { try { await fetch('/api/system/stop', { method: 'POST' }); getStatus(); } catch(e) {} }
async function doRelogin() { try { var r = await fetch('/api/system/relogin', { method: 'POST' }); alert('请在浏览器中扫码登录'); } catch(e) {} }
async function navigateBrowserToChat() { try { await fetch('/api/system/navigate-chat', { method: 'POST' }); } catch(e) {} }

async function toggleAutoReply() {
  try {
    var r = await fetch('/api/settings'); var d = await r.json();
    var cur = d.auto_reply_enabled === 'true';
    await fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ key: 'auto_reply_enabled', value: cur ? 'false' : 'true' }) });
    getStatus();
  } catch(e) {}
}

async function doSearch() {
  var kw = document.getElementById('searchKeyword'), city = document.getElementById('searchCity');
  if (!kw || !kw.value.trim()) { alert('请输入搜索关键词'); return; }

  // 检查浏览器状态
  try {
    var sr = await fetch('/api/status'); var sd = await sr.json();
    if (!sd.browser_running) { alert('请先点击「启动浏览器」'); return; }
  } catch(e) {}

  var kwVal = kw.value.trim();
  var cityVal = city ? city.value.trim() : '';
  var btn = document.getElementById('btnSearch');
  if (btn) { btn.disabled = true; btn.textContent = '搜索中...'; }
  try {
    var r = await fetch('/api/jobs/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword: kwVal, city: cityVal, limit: 30 })
    });
    if (!r.ok) {
      var ed = await r.json().catch(function() { return { detail: r.statusText }; });
      alert('搜索失败: ' + (ed.detail || ed.message || 'HTTP ' + r.status));
      return;
    }
    var d = await r.json();
    if (d.error) { alert('搜索失败: ' + d.error); return; }
    if (d.jobs_found !== undefined) {
      alert('找到 ' + d.jobs_found + ' 个岗位');
      // 切换 tab 时渲染
      setTimeout(function() { switchTab('applications'); loadApplications(); }, 300);
    } else {
      alert('搜索完成');
      setTimeout(function() { loadApplications(); }, 300);
    }
  } catch(e) { alert('搜索失败: ' + e.message); }
  if (btn) { btn.disabled = false; btn.textContent = '搜索'; }
}
function batchSearch() { doSearch(); }

// ── Settings ──
async function loadSettings() {
  try {
    var r = await fetch('/api/settings'); var d = await r.json();
    // 填充原有表单字段（设置页是硬编码的 input 表单，不是动态表格）
    var mapping = {
      setLocation: 'default_city', setWechat: 'wechat_id', setResume: 'resume_summary',
      setGreeting: 'greeting_template', setDailyLimit: 'daily_apply_limit',
      setMinDelay: 'min_reply_delay_sec', setMaxDelay: 'max_reply_delay_sec',
      setSearchKeywords: 'search_keywords', setAutoReply: 'auto_reply_enabled'
    };
    Object.keys(mapping).forEach(function(elId) {
      var el = document.getElementById(elId), key = mapping[elId];
      if (el && d[key] !== undefined) { el.value = d[key]; }
    });
    var ak = document.getElementById('setAIApiKey'); if (ak && d.ai_api_key) ak.value = d.ai_api_key;
    var au = document.getElementById('setAIBaseUrl'); if (au && d.ai_base_url) au.value = d.ai_base_url;
    var am = document.getElementById('setAIModel'); if (am && d.ai_model) am.value = d.ai_model;
    var mt = document.getElementById('setMineruToken'); if (mt && d.mineru_api_token) mt.value = d.mineru_api_token;
    var sk = document.getElementById('setSiliconflowKey'); if (sk && d.siliconflow_api_key) sk.value = d.siliconflow_api_key;
    var em = document.getElementById('setEmbeddingModel'); if (em && d.embedding_model) em.value = d.embedding_model;
  } catch(e) {}
}
async function saveSettings() {
  try {
    var fields = {
      setLocation: 'default_city', setWechat: 'wechat_id', setResume: 'resume_summary',
      setGreeting: 'greeting_template', setDailyLimit: 'daily_apply_limit',
      setMinDelay: 'min_reply_delay_sec', setMaxDelay: 'max_reply_delay_sec',
      setSearchKeywords: 'search_keywords', setAutoReply: 'auto_reply_enabled',
      setAIApiKey: 'ai_api_key', setAIBaseUrl: 'ai_base_url', setAIModel: 'ai_model',
      setMineruToken: 'mineru_api_token',
      setSiliconflowKey: 'siliconflow_api_key',
      setEmbeddingModel: 'embedding_model'
    };
    var ps = [];
    Object.keys(fields).forEach(function(elId) {
      var el = document.getElementById(elId);
      if (el && el.value !== undefined) ps.push(saveSetting(fields[elId], el.value));
    });
    await Promise.all(ps);
    alert('设置已保存');
  } catch(e) { alert('保存失败: ' + e.message); }
}
async function saveSetting(key, val) {
  var body = {}; body[key] = val || '';
  try { await fetch('/api/settings', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }); } catch(e) {}
}

// ── Wechat / Transfer ──
async function loadWechatExchanges() {
  try {
    var r = await fetch('/api/wechat-exchanges'); var list = await r.json();
    var el = document.getElementById('wechatList'); if (!el) return;
    if (!list.length) { el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-3)">暂无记录</div>'; return; }
    var h = '';
    list.forEach(function(w) {
      h += '<div class="card" style="margin-bottom:8px;padding:10px 14px;"><div><strong>' + esc(w.hr_name||'') + '</strong> | ' + esc(w.hr_company||'') +
        '</div><div style="font-size:12px;color:var(--accent)">' + esc(w.hr_wechat||'') + '</div><div style="font-size:11px;color:var(--text-3)">' + esc(w.job_title||'') + ' | ' + esc(w.city||'') + '</div></div>';
    });
    el.innerHTML = h;
  } catch(e) {}
}
async function loadTransferRequests() {
  try {
    var r = await fetch('/api/transfer-requests'); var list = await r.json();
    var el = document.getElementById('transferList'); if (!el) return;
    if (!list.length) { el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-3)">暂无请求</div>'; return; }
    var h = '';
    list.forEach(function(t) {
      h += '<div class="card" style="margin-bottom:8px;padding:10px 14px;"><div><strong>' + esc(t.hr_name||'') + '</strong> | ' + esc(t.hr_company||'') +
        '</div><div style="font-size:12px;">' + esc(t.last_message_text||'') + '</div><div style="font-size:11px;color:var(--text-3)">' + esc(t.job_title||'') + ' | ' + (t.transfer_requested_at||'') + '</div></div>';
    });
    el.innerHTML = h;
  } catch(e) {}
}

// ── Utils ──
function esc(s) { return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
function toast(msg) { console.log('[BOSS]', msg); }
function loadReviewDashboard() {}
function loadKbStats() {}
function loadShortlists() {}
function batchApplyPending() { toast('请先搜索岗位后调用投递 API'); }
function batchApplyAll() { batchApplyPending(); }
function selectAllScale() {}
function toggleScaleMulti() {}
function doKbImport() {}
function switchKbMode() {}
function qaAsk() {}
// ── AI Agent ──
var _agentRunning = false;

async function submitAgentGoal() {
  if (_agentRunning) return;
  var goalEl = document.getElementById('agentGoal'), stepsEl = document.getElementById('agentMaxSteps');
  var goal = goalEl ? goalEl.value.trim() : '';
  if (!goal || goal.length < 5) { alert('请输入求职目标（至少5个字）'); return; }
  var maxSteps = parseInt(stepsEl ? stepsEl.value : '12') || 12;

  // 检查浏览器状态
  try {
    var sr = await fetch('/api/status'); var sd = await sr.json();
    if (!sd.browser_running) { alert('请先点击「启动浏览器」'); return; }
  } catch(e) {}

  _agentRunning = true;
  var btn = document.getElementById('agentSubmitBtn');
  var stopBtn = document.getElementById('agentStopBtn');
  var running = document.getElementById('agentRunning');
  var progress = document.getElementById('agentProgress');
  if (btn) { btn.disabled = true; btn.textContent = '执行中...'; }
  if (stopBtn) stopBtn.style.display = '';
  if (running) running.style.display = 'flex';
  if (progress) { progress.innerHTML = ''; progress.style.display = 'block'; }

  try {
    var r = await fetch('/api/agent/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ goal: goal, max_steps: maxSteps, auto_execute: true })
    });
    if (!r.ok) { var ed = await r.json().catch(function(){return{detail:r.statusText}}); alert('Agent 启动失败: ' + (ed.detail||'')); resetAgentUI(); return; }
    var d = await r.json();
    showAgentResult(d);
  } catch(e) { alert('Agent 启动失败: ' + e.message); }
  resetAgentUI();
}

function stopAgent() {
  if (!_agentRunning) return;
  resetAgentUI();
}

function resetAgentUI() {
  _agentRunning = false;
  var btn = document.getElementById('agentSubmitBtn');
  var stopBtn = document.getElementById('agentStopBtn');
  if (btn) { btn.disabled = false; btn.textContent = '启动 Agent'; }
  if (stopBtn) stopBtn.style.display = 'none';
}

function showAgentResult(d) {
  var progress = document.getElementById('agentProgress');
  if (!progress) return;
  var h = '';
  if (d.message) h += '<div class="agent-msg">' + esc(d.message) + '</div>';
  if (d.plan) {
    h += '<div class="agent-plan"><strong>执行计划:</strong><ol>';
    (d.plan.steps||[]).forEach(function(s) { h += '<li>' + esc(s.description||s) + '</li>'; });
    h += '</ol></div>';
  }
  if (d.steps_executed !== undefined) h += '<div style="color:var(--green)">已完成 ' + d.steps_executed + ' 步</div>';
  progress.innerHTML = h || '<div>任务已提交</div>';
  progress.style.display = 'block';
}
function sendManualMessage() {}

// ── Init ──
document.addEventListener('DOMContentLoaded', function() {
  connectWS();
  setTimeout(function() { getStatus(); getStats(); }, 500);
});
