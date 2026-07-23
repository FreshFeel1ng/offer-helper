async function assistantCheckStatus(){
  try{
    let r=await fetch('/api/assistant/status');let d=await r.json();
    asstRunning=d.running;
    updateAssistantUI();
  }catch(e){}
  loadTokenStats();
}

function updateAssistantUI(){
  let dot=document.getElementById('asstStatusDot');
  let txt=document.getElementById('asstStatusText');
  let startBtn=document.getElementById('asstStartBtn');
  let stopBtn=document.getElementById('asstStopBtn');
  let navDot=document.getElementById('assistantDot');
  if(asstRunning){
    if(dot){dot.className='dot on';}if(txt)txt.textContent='运行中 (端口 8001)';
    if(startBtn)startBtn.style.display='none';if(stopBtn)stopBtn.style.display='';
    if(navDot){navDot.className='dot on';}
  }else{
    if(dot){dot.className='dot off';}if(txt)txt.textContent='未启动';
    if(startBtn)startBtn.style.display='';if(stopBtn)stopBtn.style.display='none';
    if(navDot){navDot.className='dot off';}
  }
}

async function assistantStart(){
  let load=document.getElementById('asstLoading');load.style.display='';
  try{
    let r=await fetch('/api/assistant/start',{method:'POST'});let d=await r.json();
    if(d.status==='no_api_key'){
      alert(d.detail);
    }else if(d.status==='started'||d.status==='already_running'){
      asstRunning=true;updateAssistantUI();
      setTimeout(()=>assistantConnectWS(),1000);
    }else{alert('启动失败: '+(d.detail||d.status));}
  }catch(e){alert('启动失败: '+e.message);}
  load.style.display='none';
}

async function assistantStop(){
  let load=document.getElementById('asstLoading');load.style.display='';
  try{
    if(asstWs){asstWs.close();asstWs=null;}
    let r=await fetch('/api/assistant/stop',{method:'POST'});let d=await r.json();
    asstRunning=false;updateAssistantUI();
    let area=document.getElementById('asstAnswerArea');
    area.innerHTML='<div style="color:var(--text-3);padding:20px;text-align:center;">服务已停止</div>';
  }catch(e){alert('停止失败: '+e.message);}
  load.style.display='none';
}

function assistantConnectWS(){
  if(asstWs){asstWs.close();}
  asstWs=new WebSocket('ws://127.0.0.1:8001/ws/assistant');
  let area=document.getElementById('asstAnswerArea');
  area.innerHTML='<div style="color:var(--text-2);padding:20px;text-align:center;">已连接到面试助手，等待问答...</div>';

  _asstCurrentAnswer=null;

  asstWs.onmessage=function(e){
    let d;try{d=JSON.parse(e.data);}catch(ex){return;}
    if(d.type==='config'){
      let r=d.payload?.resume;
      let rs=document.getElementById('resumeStatus');
      if(r?.resumeLoaded)rs.textContent='已加载: '+r.name+' ('+r.projectCount+'个项目)';
    }
    if(d.type==='status'){return;}
    if(d.type==='transcript_update'){
      // 系统音频捕获 → 转写文字
      var transDiv=document.getElementById('asstSysTranscript');
      if(transDiv){
        transDiv.style.display='block';
        transDiv.textContent=d.payload.text||'';
        transDiv.style.color='var(--text-2)';
      }
      return;
    }
    if(d.type==='answer_chunk'){
      // 流式拼接：所有 chunk 写入同一个回答框
      if(!_asstCurrentAnswer){
        _asstCurrentAnswer=document.createElement('div');
        _asstCurrentAnswer.style.cssText='margin-bottom:12px;padding:8px 12px;background:var(--bg-card);border-radius:8px;border-left:3px solid var(--accent);';
        _asstCurrentAnswer.innerHTML='<div style="font-size:10px;color:var(--accent);margin-bottom:4px;">🤖 AI 回答</div><div class="ansBody" style="line-height:1.6;white-space:pre-wrap;"></div>';
        area.prepend(_asstCurrentAnswer);
      }
      let body=_asstCurrentAnswer.querySelector('.ansBody');
      body.textContent+=d.payload.chunk;
      _asstCurrentAnswer.scrollIntoView({behavior:'smooth',block:'nearest'});
      if(d.payload.isComplete){
        let dot=document.createElement('span');
        dot.style.cssText='color:var(--green);font-size:10px;margin-left:6px;';
        dot.textContent=' ✓ 完成';
        body.appendChild(dot);
        _asstCurrentAnswer=null;
      }
    }
  };
  asstWs.onclose=function(){
    asstWs=null;asstRunning=false;_asstSysAudioActive=false;
    updateAssistantUI();updateSysAudioUI();assistantStopMic2();
  };
  asstWs.onerror=function(){
    asstWs=null;asstRunning=false;_asstSysAudioActive=false;
    updateAssistantUI();updateSysAudioUI();assistantStopMic2();
  };
}

function assistantAsk(){
  if(!asstWs||asstWs.readyState!==WebSocket.OPEN){
    alert('请先启动面试服务');return;
  }
  let q=document.getElementById('asstQuestion').value.trim();
  if(!q)return;
  _asstCurrentAnswer=null;  // 新问题 → 新回答框
  let area=document.getElementById('asstAnswerArea');
  let qDiv=document.createElement('div');
  qDiv.style.cssText='margin-bottom:8px;padding:8px 12px;background:var(--bg);border-radius:8px;border-left:3px solid var(--text-2);';
  qDiv.innerHTML='<div style="font-size:10px;color:var(--text-2);margin-bottom:4px;">问题</div><div style="line-height:1.6;">'+esc(q)+'</div>';
  area.prepend(qDiv);
  asstWs.send(JSON.stringify({type:'direct_question',payload:{question:q}}));
  document.getElementById('asstQuestion').value='';
}

async function assistantUploadResume(){
  let file=document.getElementById('resumeFile').files[0];
  if(!file){alert('请先选择文件');return;}
  let form=new FormData();form.append('file',file);
  let rs=document.getElementById('resumeStatus');rs.textContent='上传中...';
  try{
    let r=await fetch('/api/assistant/resume/upload',{method:'POST',body:form});
    let d=await r.json();
    if(d.status==='ok'){
      rs.textContent='已上传: '+d.filename+' ('+Math.round(d.size/1024)+'KB)';
      rs.style.color='var(--green)';
      // 如果面试服务在运行，通知 assistant 重新加载简历
      if(asstRunning){
        try{await fetch('http://127.0.0.1:8001/api/assistant/resume/upload',{method:'POST',body:form});}catch(e){}
      }
    }else{
      rs.textContent='上传失败';rs.style.color='var(--red)';
    }
  }catch(e){rs.textContent='上传失败: '+e.message;rs.style.color='var(--red)';}
}

/* ===== 语音识别 (Web Speech API) ===== */
let _asstRecognition=null,_asstListening=false;
let _asstCurrentAnswer=null;  // 当前流式回答的 DOM 元素

function assistantToggleMic(){
  if(!asstRunning||!asstWs||asstWs.readyState!==WebSocket.OPEN){
    alert('请先启动面试服务并等待连接建立');return;
  }
  if(!('SpeechRecognition' in window)&&!('webkitSpeechRecognition' in window)){
    alert('您的浏览器不支持语音识别，请使用 Chrome 或 Edge');return;
  }
  if(_asstListening){assistantStopMic2();return;}
  assistantStartMic();
}

function assistantStartMic(){
  if(_asstListening)return;
  var SR=window.SpeechRecognition||window.webkitSpeechRecognition;
  var rec=new SR();
  rec.continuous=true;rec.interimResults=true;rec.lang='zh-CN';

  rec.onresult=function(e){
    var final='',interim='';
    for(var i=e.resultIndex;i<e.results.length;i++){
      var r=e.results[i];
      if(r.isFinal)final+=r[0].transcript;
      else interim+=r[0].transcript;
    }
    var text=final||interim;
    var transDiv=document.getElementById('asstTranscript');
    if(text){
      transDiv.style.display='block';
      transDiv.textContent=text;
      transDiv.style.color=final?'var(--text)':'var(--text-2)';
    }
    if(final&&final.trim()){
      _sendAsstQuestion(final.trim());
      transDiv.style.display='none';transDiv.textContent='';
    }
  };

  rec.onerror=function(e){
    if(e.error==='no-speech'){
      setTimeout(function(){if(_asstListening)try{rec.start();}catch(e){}},200);
      return;
    }
    if(e.error==='aborted')return;
    console.log('[Speech] error:',e.error);
    assistantStopMic2();
  };

  rec.onend=function(){
    if(!_asstListening)return;
    try{rec.start();}catch(e){_asstListening=false;updateMicUI();}
  };

  try{rec.start();}catch(e){console.log('[Speech] start error:',e);return;}
  _asstRecognition=rec;_asstListening=true;
  updateMicUI();
}

function assistantStopMic2(){
  _asstListening=false;
  try{_asstRecognition&&_asstRecognition.abort();}catch(e){}
  _asstRecognition=null;
  var transDiv=document.getElementById('asstTranscript');
  transDiv.style.display='none';transDiv.textContent='';
  updateMicUI();
}

function updateMicUI(){
  var btn=document.getElementById('asstMicBtn');
  var label=document.getElementById('asstMicLabel');
  if(_asstListening){
    if(btn){btn.classList.add('listening');btn.textContent='🔴';}
    if(label){label.textContent='正在聆听...';label.style.color='var(--red)';}
  }else{
    if(btn){btn.classList.remove('listening');btn.textContent='🎤';}
    if(label){label.textContent='点击麦克风开始';label.style.color='var(--text-3)';}
  }
}

function _sendAsstQuestion(q){
  _asstCurrentAnswer=null;  // 新问题 → 新回答框
  var area=document.getElementById('asstAnswerArea');
  var qDiv=document.createElement('div');
  qDiv.style.cssText='margin-bottom:8px;padding:8px 12px;background:var(--bg);border-radius:8px;border-left:3px solid var(--green);';
  qDiv.innerHTML='<div style="font-size:10px;color:var(--green);margin-bottom:4px;">语音问题</div><div style="line-height:1.6;">'+esc(q)+'</div>';
  area.prepend(qDiv);
  asstWs.send(JSON.stringify({type:'direct_question',payload:{question:q}}));
}

// 重载 assistantStop: 停止时也关闭麦克风和系统音频
var _origAsstStop=assistantStop;
assistantStop=async function(){
  assistantStopMic2();
  if(_asstSysAudioActive){assistantToggleSysAudio();}
  return _origAsstStop();
};

/* ===== 系统音频捕获 ===== */
let _asstSysAudioActive=false;

function assistantToggleSysAudio(){
  if(!asstRunning||!asstWs||asstWs.readyState!==WebSocket.OPEN){
    alert('请先启动面试服务');return;
  }
  if(_asstSysAudioActive){
    asstWs.send(JSON.stringify({type:'stop_audio_capture'}));
    _asstSysAudioActive=false;
    updateSysAudioUI();
  }else{
    asstWs.send(JSON.stringify({type:'start_audio_capture'}));
    _asstSysAudioActive=true;
    updateSysAudioUI();
    // 自动开启麦克风捕获（让浏览器也监听 CABLE Output）
    if(!_asstListening)assistantStartMic();
  }
}

function updateSysAudioUI(){
  var btn=document.getElementById('asstSysAudioBtn');
  var label=document.getElementById('asstSysAudioLabel');
  if(_asstSysAudioActive){
    if(btn){btn.textContent='■ 停止捕获';btn.classList.add('listening');}
    if(label){label.textContent='捕获中...';label.style.color='var(--green)';}
  }else{
    if(btn){btn.textContent='▶ 开始捕获';btn.classList.remove('listening');}
    if(label){label.textContent='未启用';label.style.color='var(--text-3)';}
  }
}

/* ===== Token 用量 ===== */
async function loadTokenStats(){
  try {
    var r = await fetch('/api/llm-stats'); var d = await r.json();
    var s = d.summary || {};
    document.getElementById('tokCalls').textContent = s.total_calls || 0;
    document.getElementById('tokTotal').textContent = (s.total_tokens || 0).toLocaleString();
    document.getElementById('tokPrompt').textContent = (s.total_prompt_tokens || 0).toLocaleString();
    document.getElementById('tokCompletion').textContent = (s.total_completion_tokens || 0).toLocaleString();
    document.getElementById('tokTps').textContent = s.avg_tps || 0;
  } catch(e) {}
}

document.addEventListener('DOMContentLoaded',()=>{
  const modal=document.getElementById('smartSendModal');
  if(modal)modal.addEventListener('click',e=>{if(e.target===modal)closeSmartSendModal();});
});
