function openSmartSendModal(){
  document.getElementById('ssKeyword').value=document.getElementById('searchKeyword').value||'';
  document.getElementById('ssCity').value=document.getElementById('searchCity').value||'';
  document.getElementById('ssStatus').textContent='';
  document.getElementById('ssBody').innerHTML='<div class="empty" style="text-align:center;padding:30px 0;color:var(--text-3);">点击「预览」搜索并分析</div>';
  document.getElementById('ssFooter').style.display='none';
  document.getElementById('smartSendModal').style.display='flex';
  _ssPreview=null;
}
function closeSmartSendModal(){document.getElementById('smartSendModal').style.display='none';_ssPreview=null;}
function ssMode(){const el=document.querySelector('input[name="ssMode"]:checked');return el?el.value:'fast';}

document.addEventListener('change',function(e){
  if(e.target&&e.target.name==='ssMode'){
    const hints={fast:'快速：仅搜索结果，无 HR 信息（最快）',top5:'Top5 深度：打开岗位数最多的 5 家公司页解析 HR（约 20 秒）',all:'全部深度：逐个打开所有公司页（慢 2-3 分钟，可能触发风控）'};
    const h=document.getElementById('ssModeHint');if(h)h.textContent=hints[ssMode()]||'';
  }
});

async function doSmartSendPreview(){
  const btn=document.getElementById('ssPreviewBtn');
  const kw=document.getElementById('ssKeyword').value.trim();
  const city=document.getElementById('ssCity').value.trim();
  if(!kw){toast('请输入关键词','warning');return;}
  const mode=ssMode();
  const modeLabel={fast:'快速',top5:'Top5 深度',all:'全部深度'}[mode];
  btn.disabled=true;btn.textContent='分析中...';
  document.getElementById('ssStatus').innerHTML='<span style="color:var(--text-3);">\u23F3 '+modeLabel+'模式：搜索 + 按公司分组'+(mode!=='fast'?' + 打开公司页分析 HR':'')+'...</span>';
  document.getElementById('ssBody').innerHTML='<div class="empty" style="text-align:center;padding:40px 0;color:var(--text-3);">分析中'+(mode!=='fast'?'（深度模式较慢，请稍候）':'')+'...</div>';
  document.getElementById('ssFooter').style.display='none';
  try{
    const p=new URLSearchParams();p.set('keyword',kw);if(city)p.set('city',city);p.set('mode',mode);
    // 透传搜索区域的过滤条件
    const ds=getMultiSelectValues('searchDistrict');
    if(ds&&ds.length)p.set('districts',ds.join(','));
    const sizeMulti=getMultiSelectValues('searchScaleMulti');
    const scaleSingle=document.getElementById('searchScale').value||'';
    const cs=sizeMulti&&sizeMulti.length?sizeMulti.join(','):(scaleSingle||'');
    if(cs)p.set('company_size',cs);
    const r=await fetch('/api/companies/preview?'+p.toString());
    const d=await r.json();_ssPreview=d;
    if(!d.ok){
      document.getElementById('ssStatus').innerHTML='<span style="color:var(--red);">\u274C '+esc(d.message||'失败')+'</span>';
      document.getElementById('ssBody').innerHTML='<div class="empty" style="padding:40px 0;">无结果</div>';
      return;
    }
    document.getElementById('ssStatus').innerHTML='<span style="color:var(--green);">\u2705 '+d.total_jobs+' 个岗位 \u00B7 '+d.total_companies+' 家公司</span>';
    renderSmartSendPreview(d);
    document.getElementById('ssFooter').style.display='flex';
  }catch(e){document.getElementById('ssStatus').innerHTML='<span style="color:var(--red);">\u274C '+esc(e.message)+'</span>';}
  finally{btn.disabled=false;btn.textContent='预览';}
}

function renderSmartSendPreview(d){
  const body=document.getElementById('ssBody');
  const companies=d.companies||[];
  if(!companies.length){body.innerHTML='<div class="empty">未找到有效公司</div>';return;}
  let html='<div style="margin-bottom:10px;font-size:12px;color:var(--text-3);display:flex;justify-content:space-between;align-items:center;">'
    +'<span>'+d.total_companies+' 家公司（按岗位数排序）</span>'
    +'<label style="display:flex;align-items:center;gap:4px;cursor:pointer;font-size:12px;"><input type="checkbox" id="ssSelectAll" checked onchange="toggleAllSS(this.checked)">全选</label>'
    +'</div>';
  html+='<div id="ssCompanyList">';
  companies.forEach((c,i)=>{
    const top=c.top_hr;
    const tj=c.target_job;
    const checked=!c.already_applied?'checked':'';
    const disabled=c.already_applied?'disabled':'';
    const dim=c.already_applied?'opacity:.5;':'';
    html+='<div style="display:flex;align-items:flex-start;gap:10px;padding:10px 12px;border-radius:8px;margin-bottom:6px;border:1px solid var(--border);'+dim+'">'
      +'<input type="checkbox" class="ss-chk" data-idx="'+i+'" '+checked+' '+disabled+' style="margin-top:4px;" onchange="updateSSBtn()">'
      +'<div style="flex:1;min-width:0;">'
      +'<div style="display:flex;align-items:center;gap:6px;flex-wrap:wrap;">'
      +'<span style="font-size:14px;font-weight:600;">'+esc(c.company)+'</span>'
      +'<span style="font-size:11px;background:var(--bg-2);padding:1px 6px;border-radius:4px;font-family:var(--mono);">'+(c.open_count ? c.open_count+' 在招' : c.position_count+' 岗')+'</span>'
      +(c.already_applied?'<span style="font-size:10px;color:var(--red);background:rgba(239,68,68,.1);padding:1px 6px;border-radius:4px;">已投过</span>':'')
      +'</div>';
    if(top){
      html+='<div style="font-size:12px;margin-top:3px;color:var(--text-2);">\uD83C\uDFC6 '+esc(top.name)+' \u00B7 <span style="color:var(--text-3);">'+esc(top.title)+'</span></div>';
    }else if(c.deep_analyzed){
      html+='<div style="font-size:11px;margin-top:3px;color:var(--text-3);">（已分析，未识别到 HR 头衔）</div>';
    }else{
      html+='<div style="font-size:11px;margin-top:3px;color:var(--text-3);">（快速模式 · 搜索页无 HR 信息）</div>';
    }
    if(tj){
      html+='<div style="font-size:11px;margin-top:2px;color:var(--text-3);">\u2192 '+esc(tj.title)+(tj.salary?' \u00B7 '+esc(tj.salary):'')+'</div>';
    }
    if(c.jobs && c.jobs.length > 1){
      html+='<details style="margin-top:4px;"><summary style="font-size:10px;color:var(--text-3);cursor:pointer;">查看全部 '+c.jobs.length+' 个岗位</summary><div style="padding-left:4px;margin-top:4px;">';
      c.jobs.forEach(j => {
        html+='<div style="font-size:11px;color:var(--text-3);padding:1px 0;">'+esc(j.title)+(j.salary?' '+esc(j.salary):'')+(j.hr_name?' ['+esc(j.hr_name)+']':'')+'</div>';
      });
      html+='</div></details>';
    }
    html+='</div></div>';
  });
  html+='</div>';
  body.innerHTML=html;
  updateSSBtn();
}

function toggleAllSS(checked){document.querySelectorAll('.ss-chk:not(:disabled)').forEach(c=>c.checked=checked);updateSSBtn();}
function updateSSBtn(){
  const n=document.querySelectorAll('.ss-chk:checked:not(:disabled)').length;
  const btn=document.getElementById('ssConfirmBtn');
  if(btn)btn.textContent='\uD83C\uDFAF \u6279\u91CF\u6295\u9012 ('+n+' \u5BB6)';
  const footer=document.getElementById('ssFooter');
  if(footer)footer.style.display=n>0?'flex':'none';
}

async function doSmartSendConfirm(){
  if(!_ssPreview||!_ssPreview.companies){toast('请先预览','warning');return;}
  const companies=_ssPreview.companies||[];
  const checks=document.querySelectorAll('.ss-chk:checked:not(:disabled)');
  const targets=[];
  checks.forEach(chk=>{
    const idx=parseInt(chk.dataset.idx);
    const c=companies[idx];
    if(c&&c.target_job&&c.target_job.url){
      targets.push({company:c.company,job_url:c.target_job.url,hr_name:(c.top_hr||{}).name||'',hr_title:(c.top_hr||{}).title||'',is_boss:!!((c.top_hr||{}).is_boss)});
    }
  });
  if(!targets.length){toast('没有可投递的公司','warning');return;}
  const btn=document.getElementById('ssConfirmBtn');
  btn.disabled=true;btn.textContent='投递中...';
  document.getElementById('ssStatus').innerHTML='<span style="color:var(--text-3);">正在批量投递 '+targets.length+' 家...</span>';
  try{
    const r=await fetch('/api/companies/smart-send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({targets,confirm:true})});
    const d=await r.json();
    if(d.success||d.applied>0){
      document.getElementById('ssStatus').innerHTML='<span style="color:var(--green);">\u2705 '+esc(d.message)+'</span>';
      toast('\uD83C\uDFAF '+d.message,'success');
      renderSmartSendResults(d);
      if(typeof refreshStatus==='function')refreshStatus();
      if(typeof loadJobs==='function')loadJobs();
      if(typeof loadApplications==='function')loadApplications();
    }else{
      document.getElementById('ssStatus').innerHTML='<span style="color:var(--red);">\u274C '+esc(d.message||'失败')+'</span>';
      toast(d.message||'失败','error');
    }
  }catch(e){document.getElementById('ssStatus').innerHTML='<span style="color:var(--red);">\u274C 请求失败</span>';toast('请求失败','error');}
  finally{btn.disabled=false;updateSSBtn();}
}

function renderSmartSendResults(d){
  const body=document.getElementById('ssBody');
  const results=d.results||[];
  let html='<div style="text-align:center;padding:14px 0 18px;">'
    +'<div style="font-size:36px;">\uD83C\uDFAF</div>'
    +'<div style="font-size:16px;font-weight:700;margin-top:6px;">投递完成</div>'
    +'<div style="font-size:13px;color:var(--text-2);margin-top:4px;">'+d.applied+' 成功 \u00B7 '+d.skipped+' 跳过 \u00B7 共 '+d.total+' 家</div>'
    +'<div style="font-size:11px;color:var(--text-3);margin-top:8px;">已发招呼语 \u00B7 会话已建立 \u00B7 可到「聊天」Tab 查看 HR 回复</div>'
    +'</div>';
  html+='<div style="border-top:1px solid var(--border);padding-top:10px;">';
  results.forEach(function(rr){
    const ok=rr.status==='success';
    const skip=rr.status==='skipped';
    const icon=ok?'\u2705':(skip?'\u23ED\uFE0F':'\u274C');
    const color=ok?'var(--green)':(skip?'var(--text-3)':'var(--red)');
    html+='<div class="ss-res-row" style="background:var(--bg-1);">'
      +'<span>'+icon+'</span>'
      +'<span style="flex:1;color:'+color+';">'+esc(rr.company||'')+'</span>'
      +(rr.job_title?'<span style="font-size:11px;color:var(--text-3);">'+esc(rr.job_title)+'</span>':'')
      +(rr.hr_name?'<span style="font-size:11px;color:var(--text-2);">'+esc(rr.hr_name)+'</span>':'')
      +(rr.reason?'<span style="font-size:11px;color:var(--text-3);">'+esc(rr.reason)+'</span>':'')
      +'</div>';
  });
  html+='</div>';
  html+='<div style="text-align:center;margin-top:14px;"><button class="btn btn-ghost btn-sm" onclick="closeSmartSendModal()">关闭</button> '
    +'<button class="btn btn-primary btn-sm" onclick="switchTab(\'chat\')">去聊天 Tab \u2192</button></div>';
  body.innerHTML=html;
  document.getElementById('ssFooter').style.display='none';
}

/* ===== AI 面试助手 ===== */
let asstWs=null,asstRunning=false;
