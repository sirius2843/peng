"""Versioned author calibration. Archive evidence stays immutable; feedback opt-in."""
import difflib,hashlib,json,secrets,sqlite3,threading
from pathlib import Path
from providers import PRIVATE,ROOT,now
DB=PRIVATE/'studio.sqlite'
EXPORT_LOCK=threading.Lock()
CATEGORIES=['判断','期限与仓位','信息选择','声音','结构','运营']
class Conflict(ValueError):pass

def encoded(x):return json.dumps(x,ensure_ascii=False)
def schema(con):
 con.executescript('''
 CREATE TABLE IF NOT EXISTS knowledge_events(id INTEGER PRIMARY KEY AUTOINCREMENT,card_id TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL,action TEXT NOT NULL,note TEXT NOT NULL,created TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS knowledge_card ON knowledge_events(card_id,id);
 CREATE TABLE IF NOT EXISTS draft_versions(id INTEGER PRIMARY KEY AUTOINCREMENT,record_id TEXT NOT NULL,seq INTEGER NOT NULL,title TEXT NOT NULL,body TEXT NOT NULL,actor TEXT NOT NULL,reason TEXT NOT NULL,created TEXT NOT NULL,UNIQUE(record_id,seq));
 CREATE TABLE IF NOT EXISTS feedback(id TEXT PRIMARY KEY,record_id TEXT NOT NULL,column_name TEXT NOT NULL,before_version INTEGER NOT NULL,after_version INTEGER NOT NULL,category TEXT NOT NULL,lesson TEXT NOT NULL,reason TEXT NOT NULL,scope TEXT NOT NULL,status TEXT NOT NULL,topics TEXT NOT NULL,payload TEXT NOT NULL,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS feedback_events(id INTEGER PRIMARY KEY AUTOINCREMENT,feedback_id TEXT NOT NULL,before_json TEXT,after_json TEXT NOT NULL,action TEXT NOT NULL,created TEXT NOT NULL);
 ''')
def connect():
 con=sqlite3.connect(DB,timeout=15);con.row_factory=sqlite3.Row;schema(con);return con

def initialize_versions(con):
 # Recover only what the old database actually retained, never invent lost edits.
 rows=con.execute('SELECT d.* FROM drafts d WHERE NOT EXISTS(SELECT 1 FROM draft_versions v WHERE v.record_id=d.id)').fetchall()
 for r in rows:
  p=json.loads(r['payload']);d=p.get('draft',{});title=d.get('title') or r['title'];body=d.get('body') or r['body']
  initial(con,r['id'],title,body,r['created'],reason='从已有生成记录恢复；旧版中间编辑未保存，无法恢复')
  if title!=r['title'] or body!=r['body']:append_version(con,r['id'],r['title'],r['body'],'legacy_edit','仅恢复旧版当前稿；修改原因未知',created=r['created'])
def initial(con,rid,title,body,created,reason='模型初稿；保留当次资料与知识快照',actor='model'):
 con.execute('INSERT INTO draft_versions(record_id,seq,title,body,actor,reason,created) VALUES(?,?,?,?,?,?,?)',(rid,1,title,body,actor,reason,created))
def versions(rid,con=None):
 if con is not None:return [dict(r) for r in con.execute('SELECT * FROM draft_versions WHERE record_id=? ORDER BY seq',(rid,))]
 with connect() as c:return versions(rid,c)
def append_version(con,rid,title,body,actor,reason='',expected=None,created=None):
 current=versions(rid,con);latest=current[-1] if current else None
 if expected is not None and (not latest or latest['id']!=expected):raise Conflict('文章已在其他页面更新，请刷新后再保存')
 if latest and latest['title']==title and latest['body']==body:return latest
 seq=(latest['seq'] if latest else 0)+1;stamp=created or now().isoformat()
 cur=con.execute('INSERT INTO draft_versions(record_id,seq,title,body,actor,reason,created) VALUES(?,?,?,?,?,?,?)',(rid,seq,title,body,actor,str(reason)[:3000],stamp))
 return {'id':cur.lastrowid,'record_id':rid,'seq':seq,'title':title,'body':body,'actor':actor,'reason':reason,'created':stamp}

def base():return json.loads((PRIVATE/'distillation_v3.json').read_text())
def verified_card(c):
 path=ROOT/'knowledge/original_verification.json'
 dates=json.loads(path.read_text()) if path.exists() else {}
 evidence=[]
 for e in c.get('evidence',[]):
  check=dates.get(str(e.get('article_id')),{});e={**e}
  if check.get('date'):
   e.update(candidate_date=check['date'],published_at=check['published_at'],publication_verified=True,date_verification=check['verification'])
  evidence.append(e)
 boundary=c.get('boundary','')
 if evidence and all(e.get('publication_verified') for e in evidence):boundary=boundary.replace('显示日期未核验；','')
 return {**c,'evidence':evidence,'boundary':boundary}
def cards(con=None):
 if con is None:
  with connect() as c:return cards(c)
 items={c['id']:{**c,'revision':0,'author_adjusted':False} for c in base()['cards']}
 for row in con.execute('SELECT * FROM knowledge_events ORDER BY id'):
  data=json.loads(row['after_json']);data['revision']=row['id'];items[row['card_id']]=data
 return [verified_card(c) for c in items.values()]
def current_card(cid,con=None):return next((c for c in cards(con) if c['id']==cid),None)
def version(con=None):
 if con is None:
  with connect() as c:return version(c)
 k=con.execute('SELECT COALESCE(MAX(id),0) FROM knowledge_events').fetchone()[0];f=con.execute('SELECT COALESCE(MAX(id),0) FROM feedback_events').fetchone()[0]
 return f'v3.k{k}.f{f}'
def public_card(c):
 x={**c};x['evidence']=[{k:v for k,v in e.items() if k not in {'context','body_hash'}} for e in c.get('evidence',[])]
 for e in x['evidence']:e['quote']=e.get('quote','')[:450]
 return x

def catalog():
 b=base()
 with connect() as con:
  import presentation
  entries,layout=presentation.decorate([public_card(c) for c in cards(con)])
  result={'version':version(con),'cards':entries,'display_cards':presentation.display_cards(entries,layout),'presentation':layout,'counts':b['counts'],'limitations':b['limitations'],'feedback':feedback_list(con),
    'framework':json.loads((ROOT/'knowledge/common_framework.json').read_text())}
 return result

def save_card(data):
 action=data.get('action','adjust');cid=data.get('id');note=str(data.get('note','')).strip()[:3000]
 if action not in {'adjust','confirm','pause','resume','restore','create'}:raise ValueError('调整方式不正确')
 with connect() as con:
  con.execute('BEGIN IMMEDIATE');old=current_card(cid,con) if cid else None
  if action=='create':
   section=data.get('section');group=str(data.get('group','其他')).strip()
   if section not in {'framework','views','scenarios','voice'}:raise ValueError('请选择对应板块')
   cid='U-'+secrets.token_hex(8);new={'id':cid,'section':section,'group':group,'title':'','summary':'','logic':'','boundary':'','evidence':[],'topics':[],
    'rule_ids':[],'conditions':[],'evidence_needs':[],'branches':[],'dimensions':[],'basis':'author_statement','status':'confirmed','author_adjusted':True,'revision':0}
  else:
   if not old:raise ValueError('找不到这条内容')
   if data.get('expected_revision') is not None and data['expected_revision']!=old['revision']:raise Conflict('这条内容已更新，请刷新后再调整')
   new={**old}
  if action in {'adjust','create'}:
   for field,limit in [('title',200),('summary',2000),('logic',6000),('boundary',3000),('usage',1000)]:
    value=str(data.get(field,new.get(field,''))).strip()
    if len(value)>limit or (field in {'title','summary','logic'} and not value):raise ValueError('请填写标题、内容和分析方式，并适当精简')
    new[field]=value
   if action=='create':
    topic=str(data.get('topic','')).strip()[:80]
    if topic:new['topics']=[topic];new['group']=topic if new['section'] in {'views','scenarios'} else new['group']
    if new['section']=='voice':new['columns']=[str(data.get('column','')).strip() or new['title']]
   # After an explicit rewrite, old branches are historical evidence, not executable guidance.
   new['historical_branches']=old.get('branches',[]) if old else []
   new['branches']=[];new['conditions']=[];new['author_adjusted']=True;new['status']='confirmed'
  elif action=='confirm':new['status']='confirmed'
  elif action=='pause':new['previous_status']=new['status'];new['status']='paused'
  elif action=='resume':new['status']=new.get('previous_status','confirmed')
  elif action=='restore':
   e=con.execute('SELECT * FROM knowledge_events WHERE id=? AND card_id=?',(data.get('event_id'),cid)).fetchone()
   if not e or not e['before_json']:raise ValueError('没有可以恢复的旧版本')
   new=json.loads(e['before_json'])
  new['updated_at']=now().isoformat()
  if new['section']=='views' and action in {'adjust','create'}:new['opinion_update_at']=new['updated_at']
  cur=con.execute('INSERT INTO knowledge_events(card_id,before_json,after_json,action,note,created) VALUES(?,?,?,?,?,?)',(cid,encoded(old) if old else None,encoded(new),action,note,new['updated_at']))
  new['revision']=cur.lastrowid
 export_feedback()
 return public_card(new)

def card_history(cid):
 with connect() as con:
  return [{**dict(r),'before':json.loads(r['before_json']) if r['before_json'] else None,'after':json.loads(r['after_json'])} for r in con.execute('SELECT * FROM knowledge_events WHERE card_id=? ORDER BY id DESC',(cid,))]

def evidence(cid):
 c=current_card(cid)
 if not c:raise ValueError('内容不存在')
 rows={r['article_id']:r for r in json.loads((PRIVATE/'corpus_index.json').read_text())};out=[]
 for e in c.get('evidence',[]):
  if e.get('kind')!='archive':out.append(e);continue
  r=rows.get(e['article_id']);i=e['block_index']
  if not r or i>=len(r['blocks']) or e['quote'] not in r['blocks'][i]['text']:raise ValueError('证据定位需要核对')
  out.append({**e,'context':r['blocks'][max(0,i-1):i+2]})
 return {'id':cid,'title':c['title'],'evidence':out,'basis':c['basis']}

def prepare_feedback(rid):
 with connect() as con:
  row=con.execute('SELECT * FROM drafts WHERE id=?',(rid,)).fetchone()
  if not row:raise ValueError('文章不存在')
  items=versions(rid,con)
  if len(items)<2:raise ValueError('请先保存修改稿，再提交学习反馈')
  before,after=items[0],items[-1]
  if before['title']==after['title'] and before['body']==after['body']:raise ValueError('当前稿与初稿相同，无需提交修改反馈')
  payload=json.loads(row['payload']);delta=list(difflib.ndiff(before['body'].splitlines(),after['body'].splitlines()))
  added=[x[2:] for x in delta if x.startswith('+ ')];removed=[x[2:] for x in delta if x.startswith('- ')]
  changed=' '.join(added+removed)
  category='期限与仓位' if any(x in changed for x in ['底仓','轻仓','重仓','长线','短线','做T']) else '信息选择' if any(x in changed for x in ['消息','来源','公告','研报']) else '声音'
  previous=con.execute('SELECT id FROM feedback WHERE record_id=? AND after_version=?',(rid,after['id'])).fetchone()
  return {'record_id':rid,'column':row['column_name'],'before':before,'after':after,'added':added,'removed':removed,
   'suggested_category':category,'suggestion_basis':'只按改动词语粗分，不能据此推断修改原因；请本人确认。','categories':CATEGORIES,
   'topics':payload.get('context',{}).get('topics',[]),'sample':bool(payload.get('sample')),'existing_feedback_id':previous['id'] if previous else None}

def submit_feedback(data):
 rid=data.get('record_id');lesson=str(data.get('lesson','')).strip();reason=str(data.get('reason','')).strip()
 if len(lesson)>2500 or len(reason)>3000:raise ValueError('反馈说明过长')
 if not data.get('author_confirmed'):raise ValueError('请由本人确认后提交')
 category=data.get('category');scope=data.get('scope','article')
 if category not in CATEGORIES or scope not in {'article','column','topic'}:raise ValueError('请选择反馈类别与适用范围')
 if scope!='article' and not lesson:raise ValueError('请用一句话说明希望以后怎样写')
 prepared=prepare_feedback(rid)
 if data.get('after_version')!=prepared['after']['id']:raise Conflict('文章已有新的修改，请重新打开反馈')
 if prepared['existing_feedback_id']:raise ValueError('这份修改稿已提交，继续修改后可提交新反馈')
 with connect() as con:
  con.execute('BEGIN IMMEDIATE')
  latest=versions(rid,con)[-1]
  if latest['id']!=prepared['after']['id']:raise Conflict('文章已有新的修改，请重新打开反馈')
  if con.execute('SELECT 1 FROM feedback WHERE record_id=? AND after_version=?',(rid,latest['id'])).fetchone():raise ValueError('这份修改稿已经提交')
  row=con.execute('SELECT * FROM drafts WHERE id=?',(rid,)).fetchone();original=json.loads(row['payload'])
  fid=secrets.token_hex(12);stamp=now().isoformat();status='confirmed' if lesson and scope!='article' and not prepared['sample'] else 'archived'
  payload={'before':prepared['before'],'after':prepared['after'],'diff':{'added':prepared['added'],'removed':prepared['removed']},'author_words':reason,
   'confirmed_lesson':lesson,'category_source':'author_confirmed_after_keyword_suggestion','source_snapshot':original.get('sources'),
   'knowledge_snapshot':original.get('context',{}).get('distillation'),'knowledge_version_at_generation':original.get('context',{}).get('distillation',{}).get('version'),
   'rules_at_generation':original.get('context',{}).get('rules'), 'review_at_generation':original.get('generation_review',original.get('review')),'sample':prepared['sample'],
   'limitation':'模拟素材只演示流程，不进入真实学习；修改原因缺失时不自动推断；不自动升级通用规则。'}
  con.execute('INSERT INTO feedback VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',(fid,rid,row['column_name'],prepared['before']['id'],latest['id'],category,lesson,reason,scope,status,encoded(prepared['topics']),encoded(payload),stamp))
  con.execute('INSERT INTO feedback_events(feedback_id,before_json,after_json,action,created) VALUES(?,?,?,?,?)',(fid,None,encoded({'status':status,'lesson':lesson,'scope':scope,'category':category}),'submit',stamp))
 export_feedback()
 return {'id':fid,'status':status,'sample':prepared['sample'],'message':'已保存演示反馈，不进入真实学习' if prepared['sample'] else '已记住，下次相似内容会参考' if status=='confirmed' else '修改记录已保存，暂不作为以后写作规则'}

def feedback_list(con=None):
 if con is None:
  with connect() as c:return feedback_list(c)
 return [{k:r[k] for k in ['id','record_id','column_name','category','lesson','reason','scope','status','created']} for r in con.execute('SELECT * FROM feedback ORDER BY created DESC LIMIT 100')]
def change_feedback(data):
 fid=data.get('id');action=data.get('action')
 if action not in {'pause','resume'}:raise ValueError('请选择暂停或恢复')
 with connect() as con:
  con.execute('BEGIN IMMEDIATE');row=con.execute('SELECT * FROM feedback WHERE id=?',(fid,)).fetchone()
  if not row:raise ValueError('反馈不存在')
  payload=json.loads(row['payload'])
  if row['scope']=='article' or not row['lesson'] or payload.get('sample'):raise ValueError('这条记录仅留档，没有可启用的写作偏好')
  status='paused' if action=='pause' else 'confirmed'
  con.execute('UPDATE feedback SET status=? WHERE id=?',(status,fid))
  con.execute('INSERT INTO feedback_events(feedback_id,before_json,after_json,action,created) VALUES(?,?,?,?,?)',(fid,encoded({'status':row['status']}),encoded({'status':status}),action,now().isoformat()))
 export_feedback();return {'status':status}
def export_feedback():
 with EXPORT_LOCK:return _export_feedback()
def _export_feedback():
 with connect() as con:
  out={'schema_version':'3.0','exported_at':now().isoformat(),'feedback':[{**dict(r),'payload':json.loads(r['payload']),'topics':json.loads(r['topics'])} for r in con.execute('SELECT * FROM feedback ORDER BY created')],
       'feedback_events':[dict(r) for r in con.execute('SELECT * FROM feedback_events ORDER BY id')],
       'knowledge_events':[dict(r) for r in con.execute('SELECT * FROM knowledge_events ORDER BY id')],
       'draft_versions':[dict(r) for r in con.execute('SELECT * FROM draft_versions ORDER BY record_id,seq')]}
 path=DB.parent/'author_feedback.json';temp=path.with_suffix('.tmp');temp.write_text(encoded(out));temp.chmod(0o600);temp.replace(path)
 return out

def for_generation(column,topics,rule_ids,cutoff,case_ids=None):
 with connect() as con:
  allcards=cards(con);active=[];inactive=[c['id'] for c in allcards if c['status']=='paused']
  for c in allcards:
   if c['status']=='paused':continue
   relevant=(c['section']=='framework' and (c['id'] in rule_ids or (c.get('topics') and set(c['topics'])&set(topics)) or c['group'] in {'inputs','revision'} or c['basis']=='author_statement')) or \
     (c['section'] in {'views','scenarios'} and (bool(set(c.get('topics',[]))&set(topics)) or c['id'] in (case_ids or []))) or (c['section']=='voice' and column in c.get('columns',[]))
   if not relevant:continue
   source_refs=[e for e in c.get('evidence',[]) if not cutoff or (e.get('candidate_date') and e['candidate_date']<cutoff.date().isoformat())]
   # A dated archive viewpoint cannot leak into a historical replay. Author statements are preferences, never market facts.
   if c['section']=='views' and c['basis']!='author_statement' and not source_refs:continue
   entry={k:v for k,v in c.items() if k not in {'historical_branches','revision','statistics','evidence'}}
   entry['evidence']=[{k:e[k] for k in ['article_id','block_index','title','url','candidate_date','publication_verified'] if k in e}|{'quote':e.get('quote','')[:500]} for e in source_refs[:2]]
   entry['rule_ids']=[rid for rid in entry.get('rule_ids',[]) if rid not in inactive]
   if c.get('author_adjusted'):entry['branches']=[];entry['conditions']=[]
   active.append(entry)
  memories=[]
  for r in con.execute("SELECT * FROM feedback WHERE status='confirmed' ORDER BY created DESC"):
   ft=json.loads(r['topics']);relevant=(r['scope']=='column' and r['column_name']==column and (r['category'] in {'声音','结构','运营'} or not ft or bool(set(ft)&set(topics)))) or (r['scope']=='topic' and bool(set(ft)&set(topics)))
   if not relevant:continue
   memories.append({'id':r['id'],'column':r['column_name'],'category':r['category'],'lesson':r['lesson'],'scope':r['scope'],'topics':ft,'status':'author_confirmed',
                   'provenance':{'record_id':r['record_id'],'before_version':r['before_version'],'after_version':r['after_version']},'use':'写作偏好和场景取舍；不是当前事实，不复制旧数字'})
   if len(memories)>=6:break
  return {'version':version(con),'cards':active,'inactive_ids':inactive,'feedback_memories':memories,
          'policy':'本人确认的调整优先于历史归纳；旧原文只解释来源。缺数据不执行工具规则。反馈只按确认范围使用，不自动升为通用规则。'}
