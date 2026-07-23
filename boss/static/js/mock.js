/* ===== 模拟面试 ===== */

var mockWs = null;
var mockState = 'idle';  // idle | configured | interviewing | evaluating | finished
var mockTotalRounds = 5;
var mockCurrentRound = 0;
var mockSessionSummary = null;

function initMockTab() {
  // 配置表单事件
  var f = document.getElementById('mockConfig');
  if (f) f.addEventListener('submit', function(e){ e.preventDefault(); mockConfigure(); });

  // 开始/停止按钮
  var startBtn = document.getElementById('mockStartBtn');
  if (startBtn) startBtn.addEventListener('click', mockStart);

  // 手动回答
  var ansBtn = document.getElementById('mockAnswerBtn');
  if (ansBtn) ansBtn.addEventListener('click', function(){ submitMockAnswer(); });

  // 回答输入框回车
  var ansInput = document.getElementById('mockAnswerInput');
  if (ansInput) ansInput.addEventListener('keydown', function(e){
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); submitMockAnswer(); }
  });

  // 跳过按钮
  var skipBtn = document.getElementById('mockSkipBtn');
  if (skipBtn) skipBtn.addEventListener('click', mockSkip);

  // 语音按钮
  var micBtn = document.getElementById('mockMicBtn');
  if (micBtn) micBtn.addEventListener('click', toggleMockMic);

  // 结束面试
  var endBtn = document.getElementById('mockEndBtn');
  if (endBtn) endBtn.addEventListener('click', mockGetReport);

  // 查看评估报告
  var reportBtn = document.getElementById('mockReportBtn');
  if (reportBtn) reportBtn.addEventListener('click', mockGetReport);

  // 查看过往记录
  loadMockHistory();
}

function mockConfigure() {
  if (mockWs) {
    try { mockWs.close(); } catch(e){}
    mockWs = null;
  }

  var posEl = document.getElementById('mockPosition');
  var topicEl = document.getElementById('mockTopic');
  var diffEl = document.getElementById('mockDifficulty');
  var roundsEl = document.getElementById('mockRounds');

  var assistantTab = document.getElementById('tab-assistant');

  // 检查 AI面试助手是否已启动
  fetch('/api/assistant/status').then(function(r){ return r.json(); }).then(function(d){
    if (!d.running) {
      showMockError('请先在「AI面试」Tab 中启动面试助手服务');
      return;
    }

    // 连接 WebSocket
    var wsUrl = 'ws://127.0.0.1:8001/ws/mock';
    mockWs = new WebSocket(wsUrl);

    mockWs.onopen = function() {
      // 发送配置
      mockWs.send(JSON.stringify({
        type: 'configure',
        payload: {
          position: posEl.value.trim() || '全栈开发工程师',
          topic: topicEl.value.trim() || '综合技术面试',
          difficulty: diffEl.value,
          max_rounds: parseInt(roundsEl.value) || 5
        }
      }));
    };

    mockWs.onmessage = function(e) {
      var msg = JSON.parse(e.data);
      handleMockMessage(msg);
    };

    mockWs.onerror = function() {
      showMockError('WebSocket 连接失败，请确保面试助手已启动');
    };

    mockWs.onclose = function() {
      mockState = 'idle';
    };
  });
}

function mockStart() {
  if (!mockWs || mockWs.readyState !== WebSocket.OPEN) {
    mockConfigure();
    setTimeout(function(){ mockStart(); }, 800);
    return;
  }
  mockWs.send(JSON.stringify({ type: 'start' }));
}

function handleMockMessage(msg) {
  var type = msg.type;
  var payload = msg.payload || {};

  var configPanel = document.getElementById('mockConfigPanel');
  var interviewPanel = document.getElementById('mockInterviewPanel');
  var reportPanel = document.getElementById('mockReportPanel');
  var qaArea = document.getElementById('mockQA');
  var questionEl = document.getElementById('mockQuestion');
  var roundEl = document.getElementById('mockRound');
  var answerInput = document.getElementById('mockAnswerInput');
  var answerBtn = document.getElementById('mockAnswerBtn');
  var skipBtn = document.getElementById('mockSkipBtn');
  var endBtn = document.getElementById('mockEndBtn');
  var micBtn = document.getElementById('mockMicBtn');

  if (type === 'configured') {
    mockState = 'configured';
    mockTotalRounds = payload.max_rounds;
    mockCurrentRound = 0;
    configPanel.style.display = 'none';
    interviewPanel.style.display = 'block';
    reportPanel.style.display = 'none';
    qaArea.innerHTML = '';
    questionEl.textContent = '';
    answerInput.style.display = 'block';
    showMockStatus('点击「AI 出题」开始面试');
    if (document.getElementById('mockStartBtn')) document.getElementById('mockStartBtn').style.display = 'inline-block';
    document.getElementById('mockAnswerBtn').style.display = 'none';
    if (micBtn) micBtn.style.display = 'none';
    if (skipBtn) skipBtn.style.display = 'none';
    if (endBtn) endBtn.style.display = 'none';

  } else if (type === 'question') {
    mockState = 'interviewing';
    mockCurrentRound = payload.round;
    mockTotalRounds = payload.total;
    qaArea.innerHTML = '';
    questionEl.textContent = payload.question;
    if (roundEl) roundEl.textContent = '第 ' + payload.round + ' / ' + payload.total + ' 题';
    answerInput.value = '';
    answerInput.disabled = false;
    answerInput.style.display = 'block';
    answerBtn.disabled = false;
    answerBtn.style.display = 'inline-block';
    if (document.getElementById('mockStartBtn')) document.getElementById('mockStartBtn').style.display = 'none';
    skipBtn.style.display = 'inline-block';
    if (micBtn) micBtn.style.display = 'inline-block';
    endBtn.style.display = 'inline-block';
    document.getElementById('mockReportBtn').style.display = 'none';
    var exitBtn2 = document.getElementById('mockExitBtn');
    if (exitBtn2) exitBtn2.style.display = 'none';
    answerInput.focus();
    showMockStatus('请回答');

  } else if (type === 'evaluating') {
    mockState = 'evaluating';
    answerInput.disabled = true;
    answerBtn.disabled = true;
    micBtn.style.display = 'none';
    skipBtn.style.display = 'none';
    showMockStatus('AI 正在评估...');

  } else if (type === 'evaluation') {
    mockState = 'idle';
    var qaItem = document.createElement('div');
    qaItem.className = 'mock-qa-item';
    qaItem.innerHTML = '<div class="mock-q"><strong>Q:</strong> ' + escapeHtml(questionEl.textContent) + '</div>' +
      '<div class="mock-a"><strong>A:</strong> ' + escapeHtml(answerInput.value) + '</div>' +
      '<div class="mock-score">评分: <span class="score-badge">' + (payload.score || 0) + '/10</span></div>' +
      '<div class="mock-comment">' + escapeHtml(payload.comment || '') + '</div>';
    qaArea.appendChild(qaItem);

    if (mockCurrentRound >= mockTotalRounds) {
      endBtn.style.display = 'none';
      answerInput.style.display = 'none';
      answerBtn.style.display = 'none';
      skipBtn.style.display = 'none';
      var micBtn2 = document.getElementById('mockMicBtn');
      if (micBtn2) micBtn2.style.display = 'none';
      showMockStatus('面试结束');
      var reportBtn2 = document.getElementById('mockReportBtn');
      if (reportBtn2) reportBtn2.style.display = 'inline-block';
      // 退出按钮
      var exitBtn = document.getElementById('mockExitBtn');
      if (!exitBtn) {
        exitBtn = document.createElement('button');
        exitBtn.id = 'mockExitBtn';
        exitBtn.textContent = '← 退出';
        exitBtn.className = 'btn';
        exitBtn.style.marginLeft = '8px';
        exitBtn.onclick = function(){ resetMock(); };
        var btnRow = endBtn.parentNode;
        if (btnRow) btnRow.appendChild(exitBtn);
      }
      if (exitBtn) exitBtn.style.display = 'inline-block';
    } else {
      var nextBtn = document.getElementById('mockNextBtn');
      if (!nextBtn) {
        nextBtn = document.createElement('button');
        nextBtn.id = 'mockNextBtn';
        nextBtn.textContent = '下一题 →';
        nextBtn.className = 'btn';
        nextBtn.style.marginLeft = '8px';
        nextBtn.onclick = function(){ mockNextQuestion(); };
        answerBtn.parentNode.appendChild(nextBtn);
      }
      showMockStatus('请点击「下一题」继续');
      answerInput.disabled = true;
      answerBtn.disabled = true;
    }

  } else if (type === 'report') {
    mockState = 'finished';
    interviewPanel.style.display = 'none';
    reportPanel.style.display = 'block';
    renderMockReport(payload);
    loadMockHistory();

  } else if (type === 'error') {
    showMockError(payload.message);
  }
}

function mockNextQuestion() {
  var nextBtn = document.getElementById('mockNextBtn');
  if (nextBtn) { nextBtn.remove(); }
  if (!mockWs) return;
  mockWs.send(JSON.stringify({ type: 'next' }));
}

function submitMockAnswer() {
  if (mockState !== 'interviewing') return;
  var input = document.getElementById('mockAnswerInput');
  var text = input.value.trim();
  if (!text) return;
  if (!mockWs || mockWs.readyState !== WebSocket.OPEN) return;

  mockState = 'submitting';
  input.disabled = true;
  document.getElementById('mockAnswerBtn').disabled = true;

  mockWs.send(JSON.stringify({
    type: 'answer',
    payload: { text: text }
  }));
}

function mockSkip() {
  if (!mockWs) return;
  mockWs.send(JSON.stringify({ type: 'skip' }));
}

function mockGetReport() {
  if (!mockWs || mockWs.readyState !== WebSocket.OPEN) return;
  if (mockState === 'finished' || mockState === 'evaluating' || mockState === 'submitting') return;
  mockState = 'evaluating';
  mockWs.send(JSON.stringify({ type: 'report' }));
  var reportBtn = document.getElementById('mockReportBtn');
  if (reportBtn) { reportBtn.disabled = true; reportBtn.textContent = '⏳ 生成中...'; }
  var endBtn = document.getElementById('mockEndBtn');
  if (endBtn) endBtn.disabled = true;
}

function renderMockReport(report) {
  var html = '<div class="mock-report">';
  html += '<h3>📊 面试评估报告</h3>';
  html += '<div class="report-score">综合评分: <span class="big-score">' + (report.overall_score || 0) + '</span> / 100</div>';

  html += '<div class="report-grid">';
  html += '<div class="report-item"><span class="rlabel">技术能力</span><span>' + (report.technical_score || 0) + '/10</span></div>';
  html += '<div class="report-item"><span class="rlabel">沟通表达</span><span>' + (report.communication_score || 0) + '/10</span></div>';
  html += '<div class="report-item"><span class="rlabel">解决问题</span><span>' + (report.problem_solving_score || 0) + '/10</span></div>';
  html += '</div>';

  html += '<p class="report-summary">' + escapeHtml(report.summary || '') + '</p>';

  if (report.strengths && report.strengths.length) {
    html += '<h4>✅ 强项</h4><ul>';
    report.strengths.forEach(function(s){ html += '<li>' + escapeHtml(s) + '</li>'; });
    html += '</ul>';
  }

  if (report.weaknesses && report.weaknesses.length) {
    html += '<h4>⚠️ 待改进</h4><ul>';
    report.weaknesses.forEach(function(w){ html += '<li>' + escapeHtml(w) + '</li>'; });
    html += '</ul>';
  }

  if (report.suggestion) {
    html += '<h4>💡 提升建议</h4><p>' + escapeHtml(report.suggestion) + '</p>';
  }

  html += '<div style="display:flex;gap:8px;margin-top:16px;">';
  html += '<button class="btn" onclick="resetMock()">← 退出</button>';
  html += '<button class="btn btn-primary" onclick="resetMock()">🔄 重新开始</button>';
  html += '</div>';
  html += '</div>';

  document.getElementById('mockReportPanel').innerHTML = html;
}

function resetMock() {
  if (mockWs) { try { mockWs.close(); } catch(e){} mockWs = null; }
  mockState = 'idle';
  document.getElementById('mockConfigPanel').style.display = 'block';
  document.getElementById('mockInterviewPanel').style.display = 'none';
  document.getElementById('mockReportPanel').style.display = 'none';
  document.getElementById('mockQA').innerHTML = '';
  document.getElementById('mockAnswerInput').value = '';
  loadMockHistory();
}

/* ===== Speech Recognition ===== */
var mockRecognition = null;
var mockIsListening = false;

function toggleMockMic() {
  if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
    alert('当前浏览器不支持语音识别，请使用 Chrome。');
    return;
  }

  if (mockIsListening) {
    stopMockMic();
    return;
  }

  var SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  mockRecognition = new SR();
  mockRecognition.lang = 'zh-CN';
  mockRecognition.interimResults = true;
  mockRecognition.continuous = true;
  mockRecognition.maxAlternatives = 1;

  var micBtn = document.getElementById('mockMicBtn');
  var answerInput = document.getElementById('mockAnswerInput');
  var originalText = '';
  var transcriptFinal = '';
  var transcriptInterim = '';

  mockRecognition.onstart = function() {
    mockIsListening = true;
    micBtn.textContent = '🔴 停止';
    micBtn.style.background = '#ef4444';
    originalText = answerInput.value.trim();
    transcriptFinal = '';
    transcriptInterim = '';
    showMockStatus('🎤 正在聆听... 说完点按钮停止');
  };

  mockRecognition.onresult = function(event) {
    var interim = '';
    var final = '';
    for (var i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        final += event.results[i][0].transcript;
      } else {
        interim += event.results[i][0].transcript;
      }
    }
    transcriptFinal += final;
    transcriptInterim = interim;

    // 基准 = 本次识别前的原文 + 本次累积的识别结果
    var sep = originalText ? ' ' : '';
    answerInput.value = originalText + sep + transcriptFinal + transcriptInterim;
    showMockStatus('🎤 聆听中... (' + (transcriptFinal + transcriptInterim).length + '字)');
  };

  mockRecognition.onerror = function(event) {
    mockIsListening = false;
    micBtn.textContent = '🎤';
    micBtn.style.background = '';
    console.error('[Mock] Speech error:', event.error);
    showMockStatus('语音识别出错，请重试');
  };

  mockRecognition.onend = function() {
    mockIsListening = false;
    micBtn.textContent = '🎤';
    micBtn.style.background = '';
    if (!answerInput.value.trim()) {
      showMockStatus('未识别到内容，请重试');
    } else {
      showMockStatus('✅ 识别完成 (' + (transcriptFinal + transcriptInterim).length + '字)，可编辑后手动提交');
    }
  };

  mockRecognition.start();
}

function stopMockMic() {
  if (mockRecognition) {
    try { mockRecognition.stop(); } catch(e){}
    mockRecognition = null;
  }
  mockIsListening = false;
  var micBtn = document.getElementById('mockMicBtn');
  if (micBtn) { micBtn.textContent = '🎤'; micBtn.style.background = ''; }
}

/* ===== 历史记录 ===== */
function loadMockHistory() {
  fetch('/api/mock/list?limit=10').then(function(r){ return r.json(); }).then(function(d){
    var listEl = document.getElementById('mockHistory');
    if (!listEl) return;
    if (!d.ok || !d.data.length) {
      listEl.innerHTML = '';
      return;
    }
    var html = '<h4>📜 过往记录</h4><div class="mock-history-list">';
    d.data.forEach(function(item){
      var date = item.created_at ? item.created_at.substring(0, 16).replace('T', ' ') : '';
      html += '<div class="mock-history-item" onclick="viewMockDetail(' + item.id + ')">' +
        '<span class="hpos">' + escapeHtml(item.position) + '</span>' +
        '<span class="htopic">' + escapeHtml(item.topic) + '</span>' +
        '<span class="hscore">' + (item.score || '-') + '分</span>' +
        '<span class="hdate">' + date + '</span>' +
        '<button class="btn-sm" onclick="event.stopPropagation();deleteMock(' + item.id + ')" title="删除">🗑</button>' +
        '</div>';
    });
    html += '</div>';
    listEl.innerHTML = html;
  });
}

function viewMockDetail(id) {
  fetch('/api/mock/' + id).then(function(r){ return r.json(); }).then(function(d){
    if (!d.ok) { alert('加载失败'); return; }
    var item = d.data;
    var qa;
    try { qa = JSON.parse(item.qa_json || '[]'); } catch(e) { qa = []; }
    var html = '<div class="mock-report"><button class="btn-sm" onclick="resetMock()">← 返回</button>';
    html += '<h3>📊 面试详情</h3>';
    html += '<p>岗位: ' + escapeHtml(item.position) + ' | 方向: ' + escapeHtml(item.topic) + ' | 难度: ' + (item.difficulty||'') + '</p>';
    html += '<div class="report-score">评分: <span class="big-score">' + (item.score || 0) + '</span> / 100</div>';

    // 评估
    var ev;
    try { ev = JSON.parse(item.overall_evaluation || '{}'); } catch(e) { ev = {}; }
    if (ev.summary) html += '<p>' + escapeHtml(ev.summary) + '</p>';

    // Q&A
    html += '<h4>问答记录</h4>';
    qa.forEach(function(qaItem, i){
      html += '<div class="mock-qa-item"><strong>Q' + (i+1) + ':</strong> ' + escapeHtml(qaItem.q || '') + '</div>';
      html += '<div class="mock-qa-item"><strong>A' + (i+1) + ':</strong> ' + escapeHtml(qaItem.a || '(未回答)') + '</div>';
      html += '<div style="color:#22c55e;font-size:12px;">评分: ' + (qaItem.score || 0) + '/10</div>';
    });

    html += '</div>';
    document.getElementById('mockConfigPanel').style.display = 'none';
    document.getElementById('mockInterviewPanel').style.display = 'none';
    document.getElementById('mockReportPanel').style.display = 'block';
    document.getElementById('mockReportPanel').innerHTML = html;
  });
}

function deleteMock(id) {
  if (!confirm('确定删除这条记录？')) return;
  fetch('/api/mock/' + id, { method: 'DELETE' }).then(function(r){ return r.json(); }).then(function(d){
    if (d.ok) loadMockHistory();
  });
}

/* ===== Helpers ===== */
function showMockStatus(msg) {
  var el = document.getElementById('mockStatus');
  if (el) el.textContent = msg;
}

function showMockError(msg) {
  showMockStatus(msg);
  console.error('[Mock]', msg);
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}
