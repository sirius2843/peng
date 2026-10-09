"""Shared, versioned current views. Drafts consume immutable saved snapshots."""
import datetime as dt,json,secrets,sqlite3
from providers import PRIVATE,TZ,now
from author_inputs import normalize
SCENES=['平稳','缩量分化','破位','反弹','高位拥挤','其他']
def connect():
 PRIVATE.mkdir(parents=True,exist_ok=True)
 con=sqlite3.connect(PRIVATE/'viewpoints.sqlite',timeout=15);con.row_factory=sqlite3.Row
 con.execute('CREATE TABLE IF NOT EXISTS views(revision INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
 return con
def empty():return {'revision':0,'effective_at':now().isoformat(timespec='minutes'),'scene':'平稳','scene_other':'','market':{'name':'大盘','view':'','horizon':'short','boll':'','dragon':'','bottom':'','signal_time':''},'industries':[],'confirmed':False}
def latest(con=None):
 if con is None:
  with connect() as c:return latest(c)
 row=con.execute('SELECT payload FROM views ORDER BY revision DESC LIMIT 1').fetchone()
 return json.loads(row['payload']) if row else empty()
def history():
 with connect() as con:return [json.loads(r['payload']) for r in con.execute('SELECT payload FROM views ORDER BY revision DESC LIMIT 50')]
def timestamp(value,label):
 try:
  t=dt.datetime.fromisoformat(str(value));t=t if t.tzinfo else t.replace(tzinfo=TZ)
  if t>now():raise ValueError()
  return t.astimezone(TZ)
 except (TypeError,ValueError):raise ValueError(label+'需填写有效的北京时间，不能晚于现在') from None
def clean(data):
 effective=timestamp(data.get('effective_at'),'更新日期')
 scene=data.get('scene','平稳');other=str(data.get('scene_other','')).strip()
 if scene not in SCENES or len(other)>300 or (scene=='其他' and not other):raise ValueError('请选择盘面场景；其他场景请填写说明')
 if data.get('confirmed') is not True:raise ValueError('请确认这些当期观点和信号已经本人核对')
 industries=data.get('industries',[])
 if not isinstance(industries,list) or len(industries)>30:raise ValueError('行业观点最多30条')
 result={'effective_at':effective.isoformat(),'scene':scene,'scene_other':other,'confirmed':True,'industries':[]}
 seen=set()
 for i,row in enumerate([data.get('market',{}),*industries]):
  if not isinstance(row,dict):raise ValueError('观点格式不正确')
  name='大盘' if i==0 else str(row.get('name','')).strip()
  if not name or len(name)>80 or name in seen:raise ValueError('请填写不重复的行业名称')
  seen.add(name);entry={'name':name,'id':str(row.get('id') or secrets.token_hex(8))}
  for key in ['view','boll','dragon','bottom']:
   entry[key]=str(row.get(key,'')).strip()
   if len(entry[key])>2000:raise ValueError('观点或信号过长，请精简')
  entry['horizon']=row.get('horizon','short')
  if entry['horizon'] not in {'short','medium_long'}:raise ValueError('请选择有效观点期限')
  entry['signal_time']=''
  if any(entry[k] for k in ['boll','dragon','bottom']):
   signal=timestamp(row.get('signal_time'),'信号观测时间')
   if signal>effective:raise ValueError('信号观测时间不能晚于观点更新日期')
   entry['signal_time']=signal.isoformat()
  if i==0:result['market']=entry
  else:result['industries'].append(entry)
 return result
def save(data):
 result=clean(data)
 with connect() as con:
  con.execute('BEGIN IMMEDIATE');current=latest(con)
  if data.get('expected_revision')!=current['revision']:raise ValueError('共享观点已被另一页面更新，请载入最新版本后再合并保存；你的输入仍保留在页面')
  result.update(revision=current['revision']+1,saved_at=now().isoformat())
  con.execute('INSERT INTO views VALUES(?,?)',(result['revision'],json.dumps(result,ensure_ascii=False)))
 return result
def facts(snapshot,cutoff,column,intent=''):
 if not snapshot.get('revision'):return [],[]
 when=dt.datetime.fromisoformat(snapshot['effective_at'])
 if when>cutoff:return [],['共享观点更新晚于本稿资料截点，未用作当期判断；可选择较早版本或其他栏目']
 result=[];notes=[]
 for index,row in enumerate([snapshot['market'],*snapshot['industries']]):
  if column=='行业/事件点评' and index and row['name'] not in intent:continue
  signals='\n'.join(f"{row['name']} · {label}：{row[key]}" for key,label in [('boll','BOLL'),('dragon','龙线'),('bottom','底信号')] if row[key])
  data={'author_view':f"{row['name']}：{row['view']}" if row['view'] else '', 'author_horizon':row['horizon'],'tool_signals':signals,'signal_time':row['signal_time'],'author_confirmed':True}
  part=normalize(data,cutoff)
  for f in part:
   f['id']=f"SHARED-{snapshot['revision']}-{index}-"+f['id'];f['observed_at']=when.isoformat() if f['kind']=='author_judgment' else f['observed_at'];f['available_at']=f['observed_at'];f['view_revision']=snapshot['revision'];f['asset']=row['name'];f['source']='本人确认的共享当期观点'
  result+=part
 if when.date()<cutoff.date():notes.append('共享观点更新日期早于稿件日期，使用时须注明沿用日期，不冒称今天新确认')
 return result,notes
