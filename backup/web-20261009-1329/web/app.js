const $=s=>document.querySelector(s);
const state={page:'create',profileTab:'framework',profileGroup:'anchor',feedbackDraft:null,cardDraft:null,mode:'column',column:'盘中实操',filter:'全部',historyKind:'original',intents:{},authorDrafts:{},viewDraft:null,viewDirty:false,viewExpanded:false,viewDepth:'quick',viewRemoteRevision:0,recordFilter:'全部',recordSearch:'',operationSelections:{},operationDraft:[],result:null,editing:false,busy:false,stage:'',data:null};
const desc={'每日必看':'消息与当天判断','盘中实操':'行业判断与消息','风口收评':'行情梳理与次日观察','本周来信':'一周思考与配置','行业/事件点评':'把事件讲到逻辑'};
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL=u=>{try{return new URL(u).protocol==='https:'?esc(u):'#'}catch{return '#'}};
const icon='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 3 2.4 6.6L21 12l-6.6 2.4L12 21l-2.4-6.6L3 12l6.6-2.4L12 3Z"/></svg>';
function toast(text){$('#toast').textContent=text;$('#toast').classList.add('visible');setTimeout(()=>$('#toast').classList.remove('visible'),3200)}
async function api(path,body){
 const options=body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':state.data?.csrf||''},body:JSON.stringify(body)};
 const r=await fetch(path,options);let data;try{data=await r.json()}catch{throw Error('页面服务暂不可用，请重试')}
 if(!r.ok){const e=Error(data.error||'操作未完成');e.code=data.code;e.status=r.status;throw e}return data;
}
function key(){return state.mode==='article'?'article':state.column}
function inputValue(){return state.intents[key()]||''}
let selectSerial=0;
function closeSelects(except=null){document.querySelectorAll('.select-control.open').forEach(w=>{if(w!==except){w.classList.remove('open');w.querySelector('.select-menu').hidden=true;w.querySelector('.select-trigger').setAttribute('aria-expanded','false')}})}
function enhanceSelects(root){
 root.querySelectorAll('select:not(.select-native)').forEach(s=>{
  const wrapper=document.createElement('div');wrapper.className='select-control';s.before(wrapper);wrapper.append(s);s.classList.add('select-native');s.tabIndex=-1;s.setAttribute('aria-hidden','true');
  const label=s.labels?.[0];const name=label?Array.from(label.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join('').trim():s.getAttribute('aria-label')||'选择';
  const trigger=document.createElement('button');trigger.type='button';trigger.className='select-trigger';trigger.setAttribute('role','combobox');trigger.setAttribute('aria-label',name);trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-haspopup','listbox');trigger.disabled=s.disabled;
  const menu=document.createElement('div');menu.className='select-menu';menu.id='select-menu-'+(++selectSerial);menu.hidden=true;menu.setAttribute('role','listbox');menu.setAttribute('aria-label',name);trigger.setAttribute('aria-controls',menu.id);
  const update=()=>{trigger.innerHTML=`<span>${esc(s.selectedOptions[0]?.textContent||'请选择')}</span><svg viewBox="0 0 20 20" aria-hidden="true"><path d="m5 7.5 5 5 5-5"/></svg>`;menu.querySelectorAll('[role=option]').forEach((o,i)=>o.setAttribute('aria-selected',String(i===s.selectedIndex)))};
  const open=()=>{closeSelects(wrapper);wrapper.classList.add('open');menu.hidden=false;trigger.setAttribute('aria-expanded','true');const rect=wrapper.getBoundingClientRect();wrapper.classList.toggle('upward',window.innerHeight-rect.bottom<menu.offsetHeight+12&&rect.top>menu.offsetHeight+12)};
  Array.from(s.options).forEach((option,i)=>{const item=document.createElement('button');item.type='button';item.className='select-option';item.setAttribute('role','option');item.disabled=option.disabled;item.innerHTML=`<span>${esc(option.textContent)}</span><span class="select-check" aria-hidden="true">✓</span>`;
   item.addEventListener('click',e=>{e.stopPropagation();s.selectedIndex=i;s.dispatchEvent(new Event('input',{bubbles:true}));s.dispatchEvent(new Event('change',{bubbles:true}));update();closeSelects();trigger.focus()});
   item.addEventListener('keydown',e=>{if(e.key==='Escape'){e.preventDefault();closeSelects();trigger.focus()}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const options=Array.from(menu.querySelectorAll('[role=option]:not(:disabled)'));let j=options.indexOf(item);j=e.key==='Home'?0:e.key==='End'?options.length-1:(j+(e.key==='ArrowDown'?1:-1)+options.length)%options.length;options[j]?.focus()}});menu.append(item)});
  trigger.addEventListener('click',e=>{e.preventDefault();e.stopPropagation();if(wrapper.classList.contains('open'))closeSelects();else open()});
  trigger.addEventListener('keydown',e=>{if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();open();menu.querySelectorAll('[role=option]')[s.selectedIndex]?.focus()}if(e.key==='Escape')closeSelects()});
  wrapper.addEventListener('focusout',e=>{if(!wrapper.contains(e.relatedTarget))closeSelects()});s.addEventListener('change',update);wrapper.append(trigger,menu);update();
 });
}
document.addEventListener('click',e=>{if(!e.target.closest('.select-control'))closeSelects()});
function showModal(title,body,cls=''){
 const modal=$('#modal');modal.className=cls;$('#modal-content').innerHTML=`<div class="modal-head"><h2>${esc(title)}</h2><button class="close" data-action="close" aria-label="关闭">×</button></div><div class="modal-body">${body}</div>`;
 if(!modal.open)modal.showModal();enhanceSelects($('#modal-content'));setTimeout(()=>modal.querySelector('input,button')?.focus(),0);
}
function settings(){
 const s=state.data.settings;
 showModal('DeepSeek 配置',`<form id="settings-form"><label class="field-label" for="api-key">API Key</label><input id="api-key" name="api_key" type="password" autocomplete="new-password" placeholder="${s.configured?'已保存，输入新密钥可替换':'粘贴你的 DeepSeek API Key'}" ${s.configured?'':'required'} minlength="12" maxlength="256"><p>密钥保存到服务端，页面不回显。已保存时可留空。</p><label class="field-label spaced" for="model-name">模型名称</label><input id="model-name" value="${esc(s.model)}" required maxlength="80"><label class="field-label spaced" for="token-budget">输出预算</label><input id="token-budget" type="number" min="2000" max="64000" step="1000" value="${s.max_tokens||12000}"><label class="field-label spaced" for="thinking-mode">思考模式</label><select id="thinking-mode"><option value="disabled" ${s.thinking==='enabled'?'':'selected'}>关闭 · 较快</option><option value="enabled" ${s.thinking==='enabled'?'selected':''}>开启 · 适合比较判断质量</option></select><div class="connection-info"><span>●</span><span>通联数据${s.wmcloud?'已内置':'未配置'} · 日终行情</span></div><p class="source-gap">盘中快照接口需额外权限，当前不会用收盘数据冒充实时行情。</p><div class="modal-actions">${s.configured?'<button class="quiet" type="button" data-action="test-api">测试连接</button>':''}<button class="primary" type="submit">保存</button></div><div id="settings-message" class="meta"></div></form>`);
}
function operationKey(){return key()}
function pickedOperations(){return state.operationSelections[operationKey()]||[]}
function guidanceHTML(){
 const c=state.data.preferences.columns[state.column];
 return `<div class="column-guidance"><div class="section-line"><h3>${esc(state.column)} · 栏目说明</h3><button class="text-link" data-action="edit-column">调整</button></div><p><span>内容概要</span>${esc(c.summary)}</p><p><span>生成逻辑</span>${esc(c.logic)}</p></div>`;
}
function editColumn(){
 const c=state.data.preferences.columns[state.column];
 showModal(state.column+' · 栏目说明',`<form id="column-form"><label class="field-label" for="column-summary">内容概要</label><textarea id="column-summary" required maxlength="2000" rows="3">${esc(c.summary)}</textarea><label class="field-label spaced" for="column-logic">生成逻辑</label><textarea id="column-logic" required maxlength="6000" rows="6">${esc(c.logic)}</textarea><p>保存后，后续生成会使用这份栏目说明。</p><div class="modal-actions"><button class="primary" type="submit">保存</button></div></form>`);
}
function operationsHTML(){
 const items=state.data.preferences.operations,ids=pickedOperations();
 return `<div class="operations-picker"><div class="section-line"><label class="field-label">运营素材 <span>选填</span></label><button class="text-link" data-action="manage-operations">管理素材</button></div><div class="operation-chips">${items.map(o=>`<button type="button" class="operation-chip ${ids.includes(o.id)?'selected':''}" aria-pressed="${ids.includes(o.id)}" data-operation="${esc(o.id)}" >${ids.includes(o.id)?'✓ ':''}${esc(o.name)}</button>`).join('')||'<span class="meta">暂无素材，可在管理中添加。</span>'}</div>${items.filter(o=>ids.includes(o.id)).map(o=>`<div class="operation-preview"><strong>${esc(o.name)}</strong><p>${esc(o.text)}</p></div>`).join('')}</div>`;
}
function manageOperations(init=true){
 if(init)state.operationDraft=structuredClone(state.data.preferences.operations);
 showModal('运营素材',`<form id="operations-form"><p class="operations-note">勾选的素材会原样添加在文章末尾，未选的不会加入。已整理财富圈真实原文，每条可查看来源。原文中的资料与服务默认继续使用；不再提供的可直接删除。可修改现有素材或添加自己的内容。</p><div class="operation-editor">${state.operationDraft.map((o,i)=>`<div class="operation-row"><div class="row"><label class="sr-only" for="op-name-${i}">素材名称</label><input id="op-name-${i}" data-op-index="${i}" data-op-field="name" value="${esc(o.name)}" placeholder="素材名称" required maxlength="80"><button type="button" class="text-link" data-delete-operation="${i}">移除</button></div><label class="sr-only" for="op-text-${i}">素材正文</label><textarea id="op-text-${i}" data-op-index="${i}" data-op-field="text" placeholder="运营话术、服务说明或已确认的入口" required maxlength="3000" rows="3">${esc(o.text)}</textarea>${o.source?`<p class="meta">原文依据：<a href="${safeURL(o.source.url)}" target="_blank" rel="noopener noreferrer">${esc(o.source.title)}</a> · ${esc(o.source.article_id)}</p><details><summary>查看历史原句</summary><p>${esc(o.source.quote)}</p></details>`:''}${o.entry_url?`<p class="meta">工作室入口：<a href="${safeURL(o.entry_url)}" target="_blank" rel="noopener noreferrer">查看原文工作室入口</a></p>`:''}</div>`).join('')}</div><div class="modal-actions"><button type="button" class="quiet" data-action="add-operation">添加素材</button><button class="primary" type="submit">保存</button></div></form>`,'dialog-operations');
}
function markdown(text){
 const blocks=String(text).split(/\n\s*\n/);
 return blocks.map(block=>{
  const clean=esc(block).replace(/\*\*([^*]+)\*\*/g,'<strong>$1</strong>');
  if(/^### /.test(block))return '<h3>'+clean.slice(4)+'</h3>';
  if(/^## /.test(block))return '<h2>'+clean.slice(3)+'</h2>';
  if(/^# /.test(block))return '<h2>'+clean.slice(2)+'</h2>';
  return '<p>'+clean.replace(/\n/g,'<br>')+'</p>';
 }).join('');
}
function evidence(r){
 if(r.sample)return '<p class="readonly-note">模拟素材，用于校准判断与声音，未调用 DeepSeek。</p>';
 const s=r.sources||{},news=s.news||[],reports=s.research||[],notes=[...(r.review_notes||[]),...(r.review?.warnings||[]).map(w=>w.message)];
 return `<details class="evidence"><summary>资料与审阅 · ${s.market?`行情 ${esc(s.market.trade_date)}`:'行情未取得'} · 新闻${news.length}条 · 研报${reports.length}篇 · 海外${(s.global||[]).length}项</summary><ul>${news.map(n=>`<li><a href="${safeURL(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a> · 财联社摘要</li>`).join('')}${reports.map(n=>`<li><a href="${safeURL(n.url)}" target="_blank" rel="noopener noreferrer">${esc(n.title)}</a> · ${esc(n.source)} · ${esc(n.date)} · 公开摘要</li>`).join('')}</ul>${s.market?`<p class="meta">行情来源：${esc(s.market.source)} · ${esc(s.market.scope)}。${s.market.validation?esc(s.market.validation):''}</p><p class="meta">领涨：${(s.market.gainers||[]).map(x=>esc(x.name)+' '+esc(x.pct)+'%').join('；')}<br>领跌：${(s.market.losers||[]).map(x=>esc(x.name)+' '+esc(x.pct)+'%').join('；')}</p>${(s.market.flows||[]).map(f=>`<p class="meta">${esc(f.name)} · 涨跌${esc(f.pct)}% · 主力净流入${esc(f.net_yi)}亿元${f.net_pct==null?'':' · 占比'+esc(f.net_pct)+'%'}<br>${esc(f.validation)}</p>`).join('')}`:''}${(s.gaps||[]).map(g=>`<p class="source-gap">${esc(g.message)}</p>`).join('')}${(s.global||[]).map(g=>`<p class="meta"><a href="${safeURL(g.source)}" target="_blank" rel="noopener noreferrer">${esc(g.text)}</a></p>`).join('')}${(r.author_inputs||[]).map(f=>`<p class="meta">本人提供 · ${esc(f.text)} · ${esc(f.observed_at)}</p>`).join('')}${r.voice_review?`<p class="meta">声音复核：${esc({applied:'已完成并复查证据',skipped:'待机械问题解决后复核',failed:'未完成，保留初稿',rejected:'改写未通过证据检查，保留初稿'}[r.voice_review.status]||r.voice_review.status)}</p>${(r.voice_review.changes||[]).map(c=>`<p class="meta">${esc(c.reason)}<br>${esc(c.before)} → ${esc(c.after)}</p>`).join('')}`:''}${notes.map(n=>`<p class="source-gap">${esc(n)}</p>`).join('')}${(r.review?.errors||[]).map(n=>`<p class="source-gap">待复核：${esc(n.message)}</p>`).join('')}<p class="readonly-note">核验来源与数字对应不等于本人已确认，因果、取舍和声音仍需审阅。</p></details>`;
}
function resultHTML(){
 if(state.busy)return `<div class="progress" role="status"><span class="spinner"></span><span id="stage">${esc(state.stage||'整理历史案例')}</span></div>`;
 const r=state.result;if(!r)return '';
 return `<section class="result"><div class="result-heading"><div class="row"><h2>新创作</h2><span class="badge ${r.sample?'':'live'}">${r.sample?'试写示例 · 模拟素材':r.edited?'已编辑 · 待复核':'待审阅'}</span></div><div class="row"><button class="quiet" data-action="copy">复制</button><button class="quiet" data-action="toggle-edit">${state.editing?'完成编辑':'编辑'}</button></div></div><div class="card article">${state.editing?`<label class="sr-only" for="edit-title">标题</label><input class="editor-title" id="edit-title" value="${esc(r.title)}"><label class="sr-only" for="edit-body">正文</label><textarea class="editor-body" id="edit-body">${esc(r.body)}</textarea>`:`<h2 class="article-title">${esc(r.title)}</h2><p class="meta">${esc(r.column||state.column)} · ${r.sample?'编辑试写':`DeepSeek · ${new Date(r.created).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})}`}</p><div class="article-body">${markdown(r.body)}</div>`}${r.viewpoint_snapshot?`<p class="meta">生成时使用当期观点第${r.viewpoint_snapshot.revision}版 · ${esc(localTime(r.viewpoint_snapshot.effective_at).replace('T',' '))}${state.data.viewpoints.revision>r.viewpoint_snapshot.revision?' · 观点已有新版，可按最新观点更新这篇':''}</p>`:''}${evidence(r)}${judgmentsHTML(r)}</div><div class="learning-actions">${r.id?`<button class="quiet" data-action="versions">改稿记录${r.version_count?' · '+r.version_count:''}</button>`:'<span class="meta">保存修改稿后可提交学习</span>'}<button class="quiet" data-action="feedback" ${r.id&&r.edited?'':'disabled'}>提交修改稿，帮助助手学习</button></div>${!r.sample?`<div class="revision"><input id="revision" aria-label="修改要求" placeholder="想怎么改？例如：语气更直接，科技部分再短一点"><button class="quiet" data-action="revise">${r.viewpoint_snapshot&&state.data.viewpoints.revision>r.viewpoint_snapshot.revision?'按最新观点更新这篇':'修改这篇'}</button></div>`:''}</section>`;
}
function localTime(value){return String(value||'').slice(0,16)}
function viewRow(row,i){
 return `<div class="view-row"><div class="section-line"><h3>${i<0?'大盘观点':'行业观点'}</h3>${i>=0?`<button class="text-link" data-remove-view="${i}">移除行业</button>`:''}</div>${i>=0?`<label class="field-label">行业名称<input data-view-row="${i}" data-view-field="name" maxlength="80" value="${esc(row.name)}" placeholder="填写行业名称"></label>`:''}<div class="view-grid"><label class="field-label">观点<textarea data-view-row="${i}" data-view-field="view" rows="2" maxlength="2000" placeholder="当前判断、建议仓位">${esc(row.view)}</textarea></label><label class="field-label">观点期限<select data-view-row="${i}" data-view-field="horizon"><option value="short" ${row.horizon==='short'?'selected':''}>短期 / 交易</option><option value="medium_long" ${row.horizon==='medium_long'?'selected':''}>中长期 / 配置</option></select></label></div><details><summary>真实 BOLL / 龙线 / 底信号 · 选填</summary><div class="view-grid">${[['boll','BOLL'],['dragon','龙线'],['bottom','底信号']].map(([k,label])=>`<label class="field-label">${label}<textarea data-view-row="${i}" data-view-field="${k}" maxlength="2000" rows="2" placeholder="资产、周期、参数与实际信号；未观察到可留空">${esc(row[k])}</textarea></label>`).join('')}<label class="field-label">信号观测时间（北京时间）<input type="datetime-local" data-view-row="${i}" data-view-field="signal_time" value="${esc(localTime(row.signal_time))}"></label></div></details></div>`;
}
function ledgerDate(c){
 if(c.opinion_update_at)return localTime(c.opinion_update_at).replace('T',' ')+'（本人更新）';
 const e=c.evidence?.[0],date=e?.candidate_date;
 if(date)return date;
 return c.date_raw||'';
}
function ledgerRows(rows){return [...rows].sort((a,b)=>String(b.opinion_update_at||b.evidence?.[0]?.candidate_date||'').localeCompare(String(a.opinion_update_at||a.evidence?.[0]?.candidate_date||''))||a.id.localeCompare(b.id))}
function shortViewDate(value){const s=localTime(value);return s?`${s.slice(5,10)} ${s.slice(11,16)}`:'未保存'}
function currentLocalMinute(){const d=new Date(),p=n=>String(n).padStart(2,'0');return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`}
function showSaveAndGenerate(){const button=$('[data-action=generate]');if(button&&!state.busy)button.innerHTML=icon+'保存观点并生成'}
function sharedViewsHTML(){
 const v=state.viewDraft,saved=state.data.viewpoints,market=(state.viewDirty?v.market.view:saved.market?.view)||'暂未填写大盘观点',summary=market.length>54?market.slice(0,54)+'…':market;
 const full=`<div class="view-grid"><label class="field-label">更新日期（北京时间）<input id="view-date" type="datetime-local" data-view-top="effective_at" value="${esc(localTime(v.effective_at))}"></label><label class="field-label">盘面场景<select data-view-top="scene">${state.data.scenes.map(x=>`<option ${v.scene===x?'selected':''}>${esc(x)}</option>`).join('')}</select></label><label id="scene-other-field" class="field-label" ${v.scene==='其他'?'':'hidden'}>补充盘面场景<input data-view-top="scene_other" value="${esc(v.scene_other)}" maxlength="300" placeholder="请补充当前盘面场景"></label></div>${viewRow(v.market,-1)}${v.industries.map((r,i)=>viewRow(r,i)).join('')}<button class="quiet" data-action="add-industry">＋ 添加行业</button>`;
 return `<section class="card shared-views ${state.viewExpanded?'expanded':''}"><div class="view-summary"><button class="view-summary-main" data-action="toggle-views" aria-expanded="${state.viewExpanded}"><span class="view-summary-title">当期观点</span><span class="view-summary-dot">·</span><span class="view-summary-date">${esc(shortViewDate(state.viewDirty?v.effective_at:saved.effective_at))}</span><span class="view-summary-dot">·</span><span class="view-summary-opinion">大盘：${esc(summary)}</span><span class="view-chevron" aria-hidden="true">⌄</span></button><button class="text-link" data-action="open-ledger">查看台账</button></div><p class="view-summary-help">填写当期观点（可选）——不填也能生成，助手会结合历史方法与当天资料写作。</p>${state.viewExpanded?`<div class="view-editor"><div class="view-depth" role="tablist" aria-label="观点填写方式"><button role="tab" aria-selected="${state.viewDepth==='quick'}" data-view-depth="quick" class="${state.viewDepth==='quick'?'active':''}">一句话</button><button role="tab" aria-selected="${state.viewDepth==='full'}" data-view-depth="full" class="${state.viewDepth==='full'?'active':''}">完整结构化</button></div><p id="view-status" class="meta">${state.viewDirty?'有未保存修改':v.revision?'已保存 · 第'+v.revision+'版':'尚未保存观点'}</p>${state.viewDepth==='quick'?`<label class="field-label quick-view-label">今天我怎么看<textarea data-quick-view rows="3" maxlength="2000" placeholder="一句话写下当前判断和建议仓位">${esc(v.market.view)}</textarea></label><p class="meta">保存后作为本人确认的大盘观点；已有行业观点和信号会继续保留。</p>`:full}<p class="meta view-method-note">观点会按栏目选择使用，并与当天行情、新闻和研报一起写作，不会替代其他资料。</p><div class="modal-actions"><button class="primary" data-action="save-views">本人确认并保存</button></div></div>`:''}</section>`;
}
async function saveViews({renderAfter=true,notify=true}={}){
 const saved=await api('/api/viewpoints/save',{...state.viewDraft,confirmed:true,expected_revision:state.viewDraft.revision});state.data.viewpoints=saved;state.viewDraft=structuredClone(saved);state.viewDirty=false;state.viewRemoteRevision=saved.revision;if(renderAfter)render();if(notify)toast('本人观点已确认并保存，后续生成使用这一版');return saved;
}
async function syncViews(){
 if(!state.data)return;
 try{const v=await api('/api/viewpoints');if(v.revision===state.data.viewpoints.revision)return;state.data.viewpoints=v;state.viewRemoteRevision=v.revision;
 if(!state.viewDirty){state.viewDraft=structuredClone(v);if(state.page==='create'&&!state.editing&&!state.busy)render()}
 else {const el=$('#view-status');if(el)el.textContent='另一页面已保存第'+v.revision+'版，你的未保存输入已保留。请载入最新版本或查看更新记录后合并。'}
 }catch(e){}
}
async function viewHistory(){const rows=await api('/api/viewpoints/history');showModal('当期观点更新记录',rows.map(v=>`<div class="draft-version"><strong>第${v.revision}版 · ${esc(localTime(v.effective_at).replace('T',' '))} · ${esc(v.scene)}</strong><p>${esc(v.market.view||'未填大盘观点')}</p>${v.industries.map(r=>`<p>${esc(r.name)}：${esc(r.view||'仅信号')}</p>`).join('')}<button class="quiet" data-use-view="${v.revision}">载入这一版供编辑</button></div>`).join('')||'<p>暂无保存记录。</p>');state.viewHistory=rows}
function judgmentsHTML(r){
 const confirmed=new Set((r.confirmed_judgments||[]).map(x=>x.claim_id));
 if(!(r.new_judgments||[]).length)return '';
 return `<details class="evidence new-judgments"><summary>模型新增判断 · ${r.new_judgments.length}项，请本人审阅</summary>${r.new_judgments.map(j=>`<div class="judgment-row"><p>${esc(j.judgment)}</p><p class="meta">${esc(j.reason)}</p><button class="quiet" data-confirm-judgment="${esc(j.claim_id)}" ${confirmed.has(j.claim_id)?'disabled':''}>${confirmed.has(j.claim_id)?'本人已确认':'确认这条判断'}</button></div>`).join('')}${confirmed.size?'<button class="text-link" data-action="use-confirmed">带入下一篇的本人当期观点</button>':''}<p class="meta">确认记录随稿保存；带入下一篇后可修改，并再次确认时效和期限。</p></details>`;
}
function recordsHTML(){
 const rows=state.data.records.filter(r=>!r.sample&&(state.recordFilter==='全部'||r.column===state.recordFilter)&&(!state.recordSearch||(r.title+' '+r.body).includes(state.recordSearch)));
 return `<div class="page-heading"><h1>历史稿</h1><span class="meta">生成稿与修改版本均保留</span></div><div class="filters">${['全部',...state.data.columns].map(c=>`<button data-record-filter="${esc(c)}" class="${c===state.recordFilter?'selected':''}">${esc(c)}</button>`).join('')}</div><label class="sr-only" for="record-search">搜索历史稿</label><input id="record-search" value="${esc(state.recordSearch)}" placeholder="搜索标题或正文"><div id="record-list" class="record-list">${recordsList(rows)}</div>${resultHTML()}`;
}
function recordsList(rows){return rows.map(r=>`<button class="card record-row" data-record="${esc(r.id)}"><strong>${esc(r.title)}</strong><span class="meta">${esc(r.column)} · ${esc(new Date(r.created).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}))} · ${r.edited?'已编辑 · 待复核':r.review?.mechanical_pass?'待本人审阅':'待复核'} · ${r.version_count||1}版</span></button>`).join('')||'<p class="card empty">还没有符合条件的稿件。</p>'}
function createHTML(){
 const article=state.mode==='article';
 return `<div class="page-heading"><h1>内容创作</h1><span class="meta">小鹏哥写作档案已就绪</span></div>${sharedViewsHTML()}<section class="card compose"><div class="mode-tabs" role="tablist" aria-label="创作方式"><button role="tab" aria-selected="${!article}" data-mode="column" class="${article?'':'active'}">按栏目生成</button><button role="tab" aria-selected="${article}" data-mode="article" class="${article?'active':''}">新撰写文章</button></div>${article?'':`<div class="column-grid" role="group" aria-label="选择栏目">${state.data.columns.map(c=>`<button class="column-tile ${state.column===c?'selected':''}" aria-pressed="${state.column===c}" data-column="${esc(c)}"><strong>${esc(c)}</strong><small>${esc(desc[c])}</small></button>`).join('')}</div>`}${article?'':guidanceHTML()}<label class="field-label" for="intent">${article?'想写什么':'补充想法'}${article?'':'<span>选填</span>'}</label><textarea id="intent" rows="3" ${state.busy?'disabled':''} placeholder="${article?'例如：想写一篇关于半导体设备合作公告的点评，重点讲清楚订单和利润之间还有哪些环节。':'有特别想讲的行业、判断或消息，可以写在这里。留空则按栏目整理。'}">${esc(inputValue())}</textarea>${operationsHTML()}<div class="compose-bottom"><div class="source-meta"><span><i></i>通联数据</span><span><i></i>财经新闻</span><span><i></i>研报摘要</span></div><button class="primary" data-action="generate" ${state.busy?'disabled':''}>${icon}${state.busy?'正在创作':state.viewDirty?'保存观点并生成':'生成文章'}</button></div></section>${resultHTML()}`;
}
const sectionNames={framework:'理念与方法',views:'观点台账',scenarios:'场景打法',voice:'栏目写法'};
const groupNames={principles:'投资理念',research:'研究方法',asset_research:'分资产研究',position:'期限与仓位',toolkit:'工具使用',market_reading:'盘面与消息',production:'写作与资料规范'};
const statusName=c=>c.status==='paused'?'已停用':c.status==='confirmed'||c.author_adjusted?'本人已确认':'';
function cardControls(c,compact=false){
 return `<div class="knowledge-actions ${compact?'compact':''}">${c.status==='paused'?`<button class="quiet" data-card-action="resume" data-card="${esc(c.id)}">重新使用</button>`:`${c.status!=='confirmed'&&!c.author_adjusted?`<button class="quiet" data-card-action="confirm" data-card="${esc(c.id)}">确认${compact?'补充':''}</button>`:''}<button class="quiet" data-card-action="adjust" data-card="${esc(c.id)}">${compact?'调整补充':'调整'}</button>`}<button class="text-link" data-card-evidence="${esc(c.id)}">${c.evidence.length?'原文依据':'来源说明'}</button>${c.revision?`<button class="text-link" data-card-history="${esc(c.id)}">调整记录</button>`:''}</div>`;
}
function knowledgeCard(c){
 const group=c.display_group,asset=c.section==='framework'&&group==='asset_research',belief=c.section==='framework'&&group==='principles';
 const title=c.section==='views'?((c.topics[0]||c.title)+' · '+ledgerDate(c)):c.display_title||c.title;
 const badge=statusName(c);
 return `<article class="card knowledge-card ${c.status==='paused'?'paused':''} ${asset?'asset-method-card':''} ${belief?'belief-card':''}"><div class="knowledge-heading"><h3>${esc(title)}</h3>${badge?`<span class="badge">${badge}</span>`:''}</div>${asset?`<p class="card-kind">${esc(c.title)} · 长期研究路径</p>`:''}<p class="knowledge-summary">${esc(c.summary)}</p><div class="usage-line"><span>${c.section==='views'?'回看用途':'什么时候用'}</span><p>${esc(c.display_usage||c.usage||'相关研究与写作时')}</p></div>${c.research_path?.length?`<ol class="research-path">${c.research_path.map(step=>`<li>${esc(step)}</li>`).join('')}</ol>`:''}${c.boundary?`<p class="visible-boundary"><span>边界</span>${esc(c.boundary)}</p>`:''}<details class="knowledge-detail"><summary>${c.section==='voice'?'具体写法':'分析过程与处理方式'}</summary><p>${esc(c.logic)}</p>${(c.branches||[]).length?`<div class="decision-branches">${c.branches.map(b=>`<p><strong>${esc(b.when)}</strong><br>${esc(b.choice)}</p>`).join('')}</div>`:''}</details>${(c.related_cards||[]).map(child=>`<div class="method-supplement"><div class="section-line"><span class="card-kind">${c.id==='R07'?'龙线与BOLL · 定义和参数':'五道筛子与四不买 · 补充排查'}</span>${statusName(child)?`<span class="meta">${statusName(child)}</span>`:''}</div>${child.status!=='paused'?`<p>${esc(child.supplement_summary||child.summary)}</p>`:''}<details><summary>查看补充边界与原文</summary><p>${esc(child.boundary)}</p>${cardControls(child,true)}</details></div>`).join('')}<p class="card-origin">${c.basis==='user_design'?'工作台生产规范':c.basis==='author_statement'?'本人补充':c.author_adjusted?'本人已调整，原文依据另行保留':'依据原文整理'}${c.author_adjusted&&c.updated_at?' · '+esc(localTime(c.updated_at).replace('T',' ')):''}</p>${cardControls(c)}</article>`;
}
function profileHTML(){
 const p=state.data.profile,section=state.profileTab;
 const all=(p.display_cards||p.cards).filter(c=>c.section===section),layout=p.presentation?.groups||[];
 const groups=section==='framework'?layout.map(g=>g.id):section==='views'?['全部',...new Set(all.map(c=>c.group))]:section==='scenarios'?[...new Set(all.map(c=>c.group))]:[];
 let group=state.profileGroup;if(groups.length&&!groups.includes(group))group=groups[0];state.profileGroup=group;
 let rows=groups.length&&group!=='全部'?all.filter(c=>(section==='framework'?c.display_group:c.group)===group):all;
 const groupInfo=layout.find(g=>g.id===group);
 if(section==='framework'&&groupInfo){const order=groupInfo.cards;rows.sort((a,b)=>(order.includes(a.id)?order.indexOf(a.id):999)-(order.includes(b.id)?order.indexOf(b.id):999))}
 if(section==='views')rows=ledgerRows(rows);
 const hints={framework:groupInfo?.description||'长期的原则与分析方法，按实际用途整理。',views:'这里记录某个日期的判断和后续变化。研究这类资产的长期路径，见分资产研究。',scenarios:'同一资产在不同盘面条件下，期限、仓位和操作如何改变。',voice:'各栏目怎样选择材料、组织内容和表达判断。'};
 return `<div class="page-heading"><h1>我的分析与表达</h1><button class="quiet" data-action="show-feedbacks">学习反馈${p.feedback.filter(f=>f.status==='confirmed').length?' · '+p.feedback.filter(f=>f.status==='confirmed').length:''}</button></div><p class="profile-intro">长期方法、当时观点、场景处理和栏目写法分别查看。原文归纳默认可用，本人确认与停用单独记录。</p><div class="profile-tabs" role="tablist" aria-label="蒸馏板块">${Object.entries(sectionNames).map(([k,v])=>`<button role="tab" aria-selected="${section===k}" data-profile-tab="${k}" class="${section===k?'active':''}">${v}</button>`).join('')}</div>${groups.length?`<div class="filters knowledge-filters">${groups.map(g=>{const count=all.filter(c=>(section==='framework'?c.display_group:c.group)===g).length;return `<button data-profile-group="${esc(g)}" class="${group===g?'selected':''}">${esc(groupNames[g]||g)}${section==='framework'?`<span class="group-count">${count}</span>`:''}</button>`}).join('')}</div>`:''}<div class="profile-context group-context"><div><h2>${esc(section==='framework'?groupInfo?.name||group:sectionNames[section])}</h2><p>${hints[section]}</p></div><div class="row">${section==='framework'&&group==='asset_research'?'<button class="text-link" data-action="open-ledger">看各日期的观点</button>':section==='views'?'<button class="text-link" data-action="asset-methods">看分资产研究方法</button>':''}<button class="text-link" data-action="add-knowledge">补充一条</button></div></div><div class="knowledge-grid ${group==='principles'&&section==='framework'?'belief-grid':''}">${rows.map(knowledgeCard).join('')}</div><details class="framework-explanation"><summary>原文、方法与本人调整怎样保存</summary><p>每条方法保留原文依据和本人修改记录。龙线/BOLL与三位一体、五道筛子与风险排查合并展示，补充定义仍可单独调整与停用。归类变化不改写历史判断。</p><p class="meta">${p.counts.core}篇核心语料 · ${p.version}。历史观点不自动当作今天的观点；行业方法使用当期数据重新研究。</p></details>`;
}
async function refreshKnowledge(){state.data.profile=await api('/api/knowledge')}
function editKnowledge(c=null){
 const create=!c,section=c?.section||state.profileTab;state.cardDraft=c||{section,group:state.profileGroup};
 showModal(create?'补充我的分析方式':'调整：'+c.title,`<form id="knowledge-form"><label class="field-label" for="knowledge-title">名称</label><input id="knowledge-title" required maxlength="200" value="${esc(c?.title||'')}" placeholder="给这条内容起个简短名称">${create&&['views','scenarios'].includes(section)?'<label class="field-label spaced" for="knowledge-topic">方向或资产</label><input id="knowledge-topic" maxlength="80" required placeholder="例如：创新药">':''}<label class="field-label spaced" for="knowledge-summary">${section==='voice'?'我习惯怎样写':'我的说法'}</label><textarea id="knowledge-summary" required maxlength="2000" rows="3">${esc(c?.summary||'')}</textarea><label class="field-label spaced" for="knowledge-logic">${section==='voice'?'具体写法':'怎样分析或处理'}</label><textarea id="knowledge-logic" required maxlength="6000" rows="4">${esc(c?.logic||'')}</textarea><label class="field-label spaced" for="knowledge-usage">什么时候用</label><textarea id="knowledge-usage" maxlength="1000" rows="2" placeholder="例如：判断长期性价比、对照仓位与期限时">${esc(c?.usage||c?.display_usage||'')}</textarea><label class="field-label spaced" for="knowledge-boundary">适用条件或例外 <span>选填</span></label><textarea id="knowledge-boundary" maxlength="3000" rows="2">${esc(c?.boundary||'')}</textarea><details class="edit-reason"><summary>补充调整原因（选填）</summary><textarea id="knowledge-note" rows="2" maxlength="3000" placeholder="例如：这只适用于交易仓，长期配置不这样处理"></textarea></details><p>保存后用于后续相关创作。原文与旧版本都会保留，可在调整记录里撤回。</p><div class="modal-actions">${c?`<button type="button" class="text-link" data-card-action="pause" data-card="${esc(c.id)}">暂不用于写作</button>`:''}<button class="primary" type="submit">保存我的调整</button></div></form>`,'dialog-knowledge');
}
async function cardAction(id,action){
 const c=state.data.profile.cards.find(c=>c.id===id);
 if(action==='adjust'){editKnowledge(c);return}
 try{await api('/api/knowledge/save',{id,action,expected_revision:c.revision});await refreshKnowledge();if($('#modal').open)$('#modal').close();render();toast(action==='pause'?'已暂停使用，记录仍保留':action==='confirm'?'已认可':'已恢复使用')}catch(e){toast(e.message)}
}
async function showEvidence(id){
 try{const x=await api('/api/knowledge/evidence/'+encodeURIComponent(id));showModal('原文依据',`${x.evidence.length?x.evidence.map(e=>`<div class="evidence-quote"><p class="meta">${esc(e.title)} · 原始日期 ${esc(e.date_raw)}</p><blockquote>${esc(e.quote)}</blockquote><details><summary>看上下文</summary>${(e.context||[]).map(b=>`<p>${esc(b.text)}</p>`).join('')}</details><a href="${safeURL(e.url)}" target="_blank" rel="noopener noreferrer">查看原文 ↗</a></div>`).join(''):`<p>${x.basis==='author_statement'?'这条由本人补充，可在调整记录追溯。':'这是用户提出的栏目或生产设计，不冒称作者的历史原话。'}</p>`}<p>原文证明历史分析方式，不代表当期事实已核验。</p>`,'dialog-reader')}catch(e){toast(e.message)}
}
async function showCardHistory(id){
 try{const rows=await api('/api/knowledge/history/'+encodeURIComponent(id));showModal('调整记录',rows.map(r=>`<div class="history-event"><p class="meta">${esc(new Date(r.created).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'}))} · ${esc({adjust:'调整',confirm:'认可',pause:'暂停',resume:'恢复',create:'补充',restore:'撤回'}[r.action])}</p><p>${esc(r.after.summary)}</p>${r.note?`<p>原因：${esc(r.note)}</p>`:''}<details><summary>修改前后</summary><p>之前：${esc(r.before?.summary||'新增条目')}</p><p>现在：${esc(r.after.summary)}</p></details>${r.before?`<button class="quiet" data-restore-card="${esc(id)}" data-event="${r.id}">撤回这次调整</button>`:''}</div>`).join('')||'<p>还没有调整。</p>','dialog-reader')}catch(e){toast(e.message)}
}
async function showVersions(){
 try{const rows=await api('/api/records/versions/'+state.result.id);showModal('改稿记录',rows.map(v=>`<details class="draft-version" ${v.seq===rows.length?'open':''}><summary>第${v.seq}版 · ${esc(v.actor==='model'?'初稿':v.actor==='legacy_edit'?'旧版当前稿':'保存的修改稿')}</summary><p class="meta">${esc(v.created)} · ${esc(v.reason||'未填写修改原因')}</p><h3>${esc(v.title)}</h3><div class="reader-body">${esc(v.body)}</div></details>`).join(''),'dialog-reader')}catch(e){toast(e.message)}
}
async function prepareFeedback(){
 if(state.editing){toast('请先完成编辑并保存');return}
 try{const d=await api('/api/feedback/prepare',{record_id:state.result.id});state.feedbackDraft=d;
 if(d.existing_feedback_id){toast('这份修改稿已提交，继续修改后可再次提交');return}
 showModal('提交修改稿，帮助助手学习',`<form id="feedback-form">${d.sample?'<p class="source-gap">这是模拟示例，反馈只演示流程，不进入真实学习。</p>':''}<label class="field-label">这次主要改了什么？</label><div class="feedback-categories">${d.categories.map(c=>`<button type="button" class="operation-chip ${c===d.suggested_category?'selected':''}" data-feedback-category="${esc(c)}">${esc(c)}</button>`).join('')}</div><label class="field-label spaced" for="feedback-lesson">希望助手怎样写？ <span>选填</span></label><textarea id="feedback-lesson" rows="3" maxlength="2500" placeholder="用一句话说明，例如：长期逻辑没变时，短线风险只影响交易仓，别直接改成长线看空。"></textarea><label class="remember-choice"><input id="feedback-remember" type="checkbox">以后同栏目、相似情形也这样处理</label><details class="edit-reason"><summary>修改对照与原因（选填）</summary><div class="feedback-diff"><div><h3>删去或改写</h3>${d.removed.map(t=>`<p>${esc(t)}</p>`).join('')||'<p>没有删除的段落</p>'}</div><div><h3>新增或修改</h3>${d.added.map(t=>`<p>${esc(t)}</p>`).join('')||'<p>只改了标题或格式</p>'}</div></div><label class="field-label spaced" for="feedback-reason">补充原因或原话</label><textarea id="feedback-reason" rows="2" maxlength="3000"></textarea></details><p>提交表示这是本人确认的修改。未勾选“以后也这样”，只保存本次记录；系统不会自动改通用规则。</p><div class="modal-actions"><button class="primary" type="submit">确认提交</button></div></form>`,'dialog-feedback');d.category=d.suggested_category;
 }catch(e){toast(e.message)}
}
function showFeedbacks(){
 const rows=state.data.profile.feedback;
 showModal('学习反馈',`<p>只在你确认的范围内使用。一次改稿不会自动升级通用规则。</p>${rows.map(f=>`<div class="history-event"><div class="row"><span class="badge">${esc(f.status==='confirmed'?'以后参考':f.status==='paused'?'已暂停':'仅留档')}</span><span class="meta">${esc(f.column_name)} · ${esc(f.category)}</span></div><p>${esc(f.lesson||'只保存改稿对照，未填写学习要求')}</p>${f.reason?`<details><summary>修改原因</summary><p>${esc(f.reason)}</p></details>`:''}${['confirmed','paused'].includes(f.status)?`<button class="quiet" data-feedback-id="${f.id}" data-feedback-action="${f.status==='confirmed'?'pause':'resume'}">${f.status==='confirmed'?'暂不参考':'重新参考'}</button>`:''}</div>`).join('')||'<p>还没有提交的修改反馈。</p>'}`,'dialog-feedback');
}

function render(){
 if(!state.data)return;
 document.querySelectorAll('.top [data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===state.page));
 $('#configure').classList.toggle('configured',state.data.settings.configured);
 $('#app').innerHTML=state.page==='create'?createHTML():state.page==='records'?recordsHTML():profileHTML();
 enhanceSelects($('#app'));
}
async function generate(revision=false){
 if(!state.data.settings.configured){settings();return}
 if(state.busy)return;
 if(state.viewDirty){try{await saveViews({renderAfter:false,notify:false})}catch(e){toast(e.message);return}}
 const intent=revision?($('#revision')?.value.trim()||'按最新共享观点更新相关内容，保留有依据的当天消息与栏目逻辑'):inputValue().trim();
 if((state.mode==='article'||revision)&&!intent){toast(revision?'写一下希望怎么修改':'写一下想讨论的事件或行业');return}
 try{
  state.busy=true;state.editing=false;state.stage='整理历史案例';render();
  const q={mode:revision?(state.result.column==='行业/事件点评'?'article':'column'):state.mode,column:revision?state.result.column:state.column,intent,viewpoint_revision:state.viewDraft.revision,operation_ids:pickedOperations()};if(revision)q.revision_id=state.result.id;
  const {job_id}=await api('/api/generate',q);
  for(let n=0;n<600;n++){
   await new Promise(r=>setTimeout(r,1500));const job=await api('/api/jobs/'+job_id);state.stage=job.stage;
   const stage=$('#stage');if(stage)stage.textContent=job.stage;
   if(job.status==='error')throw Error(job.error);
   if(job.status==='done'){state.result=job.record;state.data.records.unshift(job.record);state.busy=false;render();$('.result')?.scrollIntoView({behavior:'smooth',block:'start'});return}
  }
  throw Error('生成时间较长，稍后刷新页面可查看已保存结果。');
 }catch(e){state.busy=false;render();if(e.code==='missing_key')settings();else toast(e.message)}
}
async function toggleEdit(){
 if(!state.editing){state.editing=true;render();return}
 const title=$('#edit-title').value.trim(),body=$('#edit-body').value.trim();
 if(!title||!body){toast('标题和正文不能为空');return}
 try{
  state.result=await api('/api/records/edit',{id:state.result.id,title,body,expected_version:state.result.version_id});
  const n=state.data.records.findIndex(r=>r.id===state.result.id);if(n>=0)state.data.records[n]=state.result;else state.data.records.unshift(state.result);state.editing=false;render();toast(state.result.sample?'示例改稿已保存，可演示反馈流程':'修改已保存，原稿与各版修改均保留');
 }catch(e){toast(e.message)}
}
document.addEventListener('input',e=>{if(e.target.hasAttribute('data-quick-view')){if(!state.viewDirty)state.viewDraft.effective_at=currentLocalMinute();state.viewDraft.market.view=e.target.value;state.viewDraft.confirmed=false;state.viewDirty=true;const status=$('#view-status');if(status)status.textContent='有未保存修改';showSaveAndGenerate();return}if(e.target.dataset.viewTop||e.target.dataset.viewField){const t=e.target;const obj=t.dataset.viewTop?state.viewDraft:(Number(t.dataset.viewRow)<0?state.viewDraft.market:state.viewDraft.industries[Number(t.dataset.viewRow)]);obj[t.dataset.viewTop||t.dataset.viewField]=t.value;state.viewDirty=true;state.viewDraft.confirmed=false;const status=$('#view-status');if(status)status.textContent='有未保存修改';showSaveAndGenerate();if(t.dataset.viewTop==='scene')$('#scene-other-field').hidden=t.value!=='其他'}if(e.target.id==='record-search'){state.recordSearch=e.target.value;const rows=state.data.records.filter(r=>!r.sample&&(state.recordFilter==='全部'||r.column===state.recordFilter)&&(!state.recordSearch||(r.title+' '+r.body).includes(state.recordSearch)));$('#record-list').innerHTML=recordsList(rows)}if(e.target.id==='intent')state.intents[key()]=e.target.value;if(e.target.dataset.opIndex!==undefined)state.operationDraft[Number(e.target.dataset.opIndex)][e.target.dataset.opField]=(e.target.type==='checkbox'?e.target.checked:e.target.value)});
document.addEventListener('click',async e=>{
 const el=e.target.closest('button');if(!el)return;
 if(state.editing&&(el.dataset.page||el.dataset.mode||el.dataset.column||el.dataset.operation)){toast('请先点击完成编辑，保存这份修改稿');return}
 if(el.dataset.recordFilter){state.recordFilter=el.dataset.recordFilter;render();return}
 if(el.dataset.record){state.result=state.data.records.find(r=>r.id===el.dataset.record);state.column=state.result.column;state.editing=false;render();$('.result')?.scrollIntoView({behavior:'smooth'});return}
 if(el.dataset.confirmJudgment){try{state.result=await api('/api/records/confirm-judgments',{id:state.result.id,claim_ids:[el.dataset.confirmJudgment],expected_version:state.result.version_id});const i=state.data.records.findIndex(r=>r.id===state.result.id);if(i>=0)state.data.records[i]=state.result;render();toast('本人确认已保存')}catch(e){toast(e.message)}return}
 if(el.dataset.profileTab){state.profileTab=el.dataset.profileTab;state.profileGroup=el.dataset.profileTab==='framework'?'anchor':'';render();return}
	 if(el.dataset.profileGroup){state.profileGroup=el.dataset.profileGroup;render();return}
	 if(el.dataset.viewDepth){state.viewDepth=el.dataset.viewDepth;render();return}
 if(el.dataset.cardAction){cardAction(el.dataset.card,el.dataset.cardAction);return}
 if(el.dataset.cardEvidence){showEvidence(el.dataset.cardEvidence);return}
 if(el.dataset.cardHistory){showCardHistory(el.dataset.cardHistory);return}
 if(el.dataset.restoreCard){try{const c=state.data.profile.cards.find(c=>c.id===el.dataset.restoreCard);await api('/api/knowledge/save',{id:c.id,action:'restore',event_id:Number(el.dataset.event),expected_revision:c.revision});await refreshKnowledge();$('#modal').close();render();toast('已恢复旧版本，撤回记录也已保留')}catch(e){toast(e.message)}return}
 if(el.dataset.feedbackCategory){state.feedbackDraft.category=el.dataset.feedbackCategory;document.querySelectorAll('[data-feedback-category]').forEach(b=>b.classList.toggle('selected',b===el));return}
 if(el.dataset.feedbackId){try{await api('/api/feedback/change',{id:el.dataset.feedbackId,action:el.dataset.feedbackAction});await refreshKnowledge();render();showFeedbacks()}catch(e){toast(e.message)}return}
 if(el.dataset.page){state.page=el.dataset.page;state.editing=false;render();window.scrollTo({top:0});return}
 if(el.dataset.mode){state.mode=el.dataset.mode;render();return}
 if(el.dataset.column){state.column=el.dataset.column;render();return}
 if(el.dataset.operation){const ids=pickedOperations(),id=el.dataset.operation;state.operationSelections[operationKey()]=ids.includes(id)?ids.filter(x=>x!==id):[...ids,id];render();return}
 if(el.dataset.deleteOperation!==undefined){state.operationDraft.splice(Number(el.dataset.deleteOperation),1);manageOperations(false);return}
 if(el.id==='configure'){settings();return}
 if(el.dataset.removeView!==undefined){state.viewDraft.industries.splice(Number(el.dataset.removeView),1);state.viewDraft.confirmed=false;state.viewDirty=true;render();return}
 if(el.dataset.useView){const v=state.viewHistory.find(x=>x.revision===Number(el.dataset.useView));state.viewDraft={...structuredClone(v),revision:state.data.viewpoints.revision,confirmed:false};state.viewDirty=true;$('#modal').close();render();return}
	 const action=el.dataset.action;
	 if(action==='toggle-views'){state.viewExpanded=!state.viewExpanded;render();return}
 if(action==='save-views'){try{await saveViews()}catch(e){toast(e.message)}return}
 if(action==='load-views'){try{const v=await api('/api/viewpoints');state.data.viewpoints=v;state.viewDraft=structuredClone(v);state.viewDirty=false;state.viewRemoteRevision=v.revision;render();toast('已载入最新保存观点')}catch(e){toast(e.message)}return}
 if(action==='view-history'){try{await viewHistory()}catch(e){toast(e.message)}return}
 if(action==='asset-methods'){state.page='profile';state.profileTab='framework';state.profileGroup='asset_research';render();window.scrollTo({top:0});return}
 if(action==='open-ledger'){state.page='profile';state.profileTab='views';state.profileGroup='全部';render();window.scrollTo({top:0});return}
 if(action==='add-industry'){if(state.viewDraft.industries.length>=30){toast('最多30个行业');return}state.viewDraft.industries.push({id:crypto.randomUUID(),name:'',view:'',horizon:'short',boll:'',dragon:'',bottom:'',signal_time:''});state.viewDraft.confirmed=false;state.viewDirty=true;render();return}
 if(action==='use-confirmed'){state.viewDraft.market.view=(state.result.confirmed_judgments||[]).map(j=>j.text).join('\n');state.viewDraft.confirmed=false;state.viewDirty=true;state.page='create';render();toast('已带入待编辑的大盘观点，请核对资产、日期并保存');return}
 if(action==='add-knowledge'){editKnowledge();return}
 if(action==='show-feedbacks'){showFeedbacks();return}
 if(action==='versions'){showVersions();return}
 if(action==='feedback'){prepareFeedback();return}
 if(action==='edit-column'){editColumn();return}
 if(action==='manage-operations'){manageOperations();return}
 if(action==='add-operation'){if(state.operationDraft.length>=40){toast('最多保存40条素材');return}state.operationDraft.push({id:crypto.randomUUID(),name:'',text:''});manageOperations(false);return}
 if(action==='close'){$('#modal').close();return}
 if(action==='generate'){generate();return}
 if(action==='revise'){generate(true);return}
 if(action==='toggle-edit'){toggleEdit();return}
 if(action==='copy'){try{await navigator.clipboard.writeText(state.result.title+'\n\n'+state.result.body);toast('已复制')}catch{toast('浏览器未允许复制，可进入编辑后选中文字')}return}
 if(action==='test-api'){el.disabled=true;try{await api('/api/settings/test',{});toast('DeepSeek连接成功')}catch(e){toast(e.message)}finally{el.disabled=false}return}
});
document.addEventListener('submit',async e=>{
 if(!['settings-form','login-form','column-form','operations-form','knowledge-form','feedback-form'].includes(e.target.id))return;e.preventDefault();const b=e.target.querySelector('[type=submit]');b.disabled=true;
 try{
  if(e.target.id==='knowledge-form'){const c=state.cardDraft;await api('/api/knowledge/save',{id:c.id,action:c.id?'adjust':'create',section:c.section,group:c.group,topic:$('#knowledge-topic')?.value||'',column:c.section==='voice'?$('#knowledge-title').value:'',title:$('#knowledge-title').value,summary:$('#knowledge-summary').value,logic:$('#knowledge-logic').value,boundary:$('#knowledge-boundary').value,usage:$('#knowledge-usage').value,note:$('#knowledge-note').value,expected_revision:c.revision});await refreshKnowledge();$('#modal').close();render();toast('调整已保存，后续相关创作会使用');return}
  if(e.target.id==='feedback-form'){const d=state.feedbackDraft;const f=await api('/api/feedback/submit',{record_id:d.record_id,after_version:d.after.id,category:d.category,lesson:$('#feedback-lesson').value,reason:$('#feedback-reason').value,scope:$('#feedback-remember').checked?'column':'article',author_confirmed:true});state.result.feedback_submitted=true;await refreshKnowledge();$('#modal').close();render();toast(f.message);return}
  if(e.target.id==='column-form'){state.data.preferences.columns[state.column]=await api('/api/preferences/column',{column:state.column,summary:$('#column-summary').value,logic:$('#column-logic').value});$('#modal').close();render();toast('栏目说明已保存，后续生成会使用');return}
  if(e.target.id==='operations-form'){const items=await api('/api/preferences/operations',{items:state.operationDraft});state.data.preferences.operations=items;for(const k of Object.keys(state.operationSelections))state.operationSelections[k]=state.operationSelections[k].filter(id=>items.some(o=>o.id===id));$('#modal').close();render();toast('运营素材已保存');return}
  if(e.target.id==='login-form'){await api('/api/login',{password:$('#access-password').value});$('#modal').close();await boot();return}
  const config=await api('/api/settings',{api_key:$('#api-key').value,model:$('#model-name').value,max_tokens:Number($('#token-budget').value),thinking:$('#thinking-mode').value});state.data.settings={...state.data.settings,...config};$('#api-key').value='';$('#modal').close();render();toast('密钥已保存到服务端');
 }catch(e){toast(e.message)}finally{b.disabled=false}
});
$('#modal').addEventListener('click',e=>{if(e.target===$('#modal'))$('#modal').close()});
async function boot(){
 try{
  state.data=await api('/api/bootstrap');state.viewDraft=structuredClone(state.data.viewpoints);state.viewRemoteRevision=state.viewDraft.revision;state.result=null;render();
 }catch(e){
  if(e.status===401){showModal('进入内容工作台','<form id="login-form"><label class="field-label" for="access-password">访问密码</label><input id="access-password" type="password" required autocomplete="current-password"><div class="modal-actions"><button class="primary" type="submit">进入</button></div></form>');return}
  $('#app').innerHTML=`<div class="card empty">${esc(e.message)}</div>`;
 }
}
boot();
