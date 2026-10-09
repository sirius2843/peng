"""Editable column guidance and explicitly selected operation text."""
import json,secrets,threading,urllib.parse
from providers import PRIVATE,ROOT
LOCK=threading.Lock()
DEFAULT_COLUMNS={
 '每日必看':{'summary':'筛选隔夜及盘前重要消息，结合上一交易日市场，讲清当天值得关注的方向与变化。','logic':'先选真正影响预期的事件，接着解释对盈利、估值或情绪的影响，再落到参与条件。海外信息只在相关时加入；不使用盘后或午间数据冒充盘前事实。'},
 '盘中实操':{'summary':'精简回应重点行业的变化，补充最新消息，区分配置与交易、不同仓位的应对。','logic':'对照前期判断，筛选会改变行业预期的消息，说明延续或修正的依据。没有实时行情和工具信号时，只讲消息与条件，明确日终参考日期，不编盘中点位。'},
 '风口收评':{'summary':'梳理收盘后的指数、成交额、领涨领跌与异动行业、主力资金流入流出、消息催化，以及后续观察条件。','logic':'从当天最值得解释的盘面矛盾切入，比较行业涨跌和主力资金流向；领涨流出、领跌流入时讨论分歧与后续验证，不能把资金口径当成机构身份或已证实的涨跌原因。用行情与消息解释变化，证据不足就保留缺口。覆盖必要信息，但不固定为大盘、板块、明日三个段落；次日预期要有可检验条件。'},
 '本周来信':{'summary':'围绕本周真正改变判断的问题，讲投资机制、配置取舍和下一周观察重点。','logic':'选择一到三个有意义的问题，串联事实、历史判断与变化，讲清短期与长期的区别。允许反思和修正，不按工作日罗列新闻，不编读者来信或本人经历。'},
 '行业/事件点评':{'summary':'围绕指定行业或事件，解释变化如何传导到盈利、估值与投资判断。','logic':'先确认事件进展与来源，再沿产业链和利润传导找受益环节、限制因素及验证条件。用历史框架辅助取舍，不直接套旧结论；预测与已实现事实分开写。'}
}
DEFAULT_OPERATIONS=json.loads((ROOT/'knowledge/operations_library.json').read_text())
def read():
 path=PRIVATE/'preferences.json'
 data=json.loads(path.read_text()) if path.exists() else {}
 columns={**DEFAULT_COLUMNS,**data.get('columns',{})}
 old={'summary':'梳理收盘后的指数、成交额、行业领涨领跌、消息催化，以及次日需要验证的条件。','logic':'从当天最值得解释的盘面矛盾切入，用行情与消息判断涨跌原因，证据不足就保留缺口。覆盖必要信息，但不固定为大盘、板块、明日三个段落；次日预期要有可检验条件。'}
 if columns['风口收评']==old:columns['风口收评']=DEFAULT_COLUMNS['风口收评']
 items=data.get('operations')
 if items is None or items==[{'id':'interaction','name':'点赞互动','text':'如果今天的内容对你有帮助，记得点点赞，我们继续一起跟踪市场变化。'},{'id':'allocation','name':'配置提醒','text':'七分配置，三分交易。大仓位先把配置做好，小仓位再做交易，别把两笔钱混在一起。'},{'id':'risk','name':'风险提示','text':'以上内容仅供参考，投资需结合自身风险承受能力、投资目标和资金安排。市场有风险，投资需谨慎。'}]:items=DEFAULT_OPERATIONS
 elif not data.get('operation_library_version'):
  ids={r['id'] for r in items};items=items+[r for r in DEFAULT_OPERATIONS if r['id'] not in ids]
 defaults={r['id']:r for r in DEFAULT_OPERATIONS}
 items=[{**r,'requires_confirmation':False,'current_confirmed':True,'source':defaults[r['id']]['source'],'entry_url':r.get('entry_url') or defaults[r['id']].get('entry_url',''),'availability_basis':defaults[r['id']].get('availability_basis')} if r['id'] in defaults else r for r in items]
 return {'columns':columns,'operations':items,'operation_library_version':data.get('operation_library_version',0)}
def write(data):
 target=PRIVATE/'preferences.json';temp=target.with_suffix('.tmp')
 temp.write_text(json.dumps(data,ensure_ascii=False,indent=2));temp.chmod(0o600);temp.replace(target)
def save_column(column,summary,logic):
 if column not in DEFAULT_COLUMNS:raise ValueError('栏目不存在')
 if not summary.strip() or not logic.strip() or len(summary)>2000 or len(logic)>6000:raise ValueError('请填写概要和生成逻辑，并适当精简')
 with LOCK:
  data=read();data['columns'][column]={'summary':summary.strip(),'logic':logic.strip()};write(data)
 return data['columns'][column]
def save_operations(items):
 if not isinstance(items,list) or len(items)>40:raise ValueError('运营素材最多保存40条')
 clean=[];seen=set()
 for row in items:
  name=str(row.get('name','')).strip();text=str(row.get('text','')).strip();rid=str(row.get('id') or secrets.token_hex(8))
  if not name or not text or len(name)>80 or len(text)>3000 or rid in seen:raise ValueError('每条素材需要名称与正文，且不能重复')
  seen.add(rid)
  origin=next((r for r in read()['operations'] if r['id']==rid),{})
  url=str(row.get('entry_url','')).strip()
  if url and (urllib.parse.urlsplit(url).scheme!='https' or not urllib.parse.urlsplit(url).netloc or len(url)>2000):raise ValueError('当前入口请填写有效的HTTPS链接')
  clean.append({'entry_url':url,'id':rid,'name':name,'text':text,'source':origin.get('source'),'requires_confirmation':False,'current_confirmed':True,'availability_basis':origin.get('availability_basis','本人添加的运营素材')})
 with LOCK:
  data=read();data['operations']=clean;data['operation_library_version']=1;write(data)
 return clean
def selected(ids):
 if not isinstance(ids,list):raise ValueError('运营素材选择格式不正确')
 library={x['id']:x for x in read()['operations']}
 if any(i not in library for i in ids):raise ValueError('运营素材已变化，请刷新后重新选择')
 return [library[i] for i in dict.fromkeys(ids)]
