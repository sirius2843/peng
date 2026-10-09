"""Read-only source adapters. Credentials stay on the server; dates remain explicit."""
import concurrent.futures as futures
import datetime as dt
import gzip, html, json, math, os, re, ssl, urllib.parse, urllib.request
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
PRIVATE=Path(os.getenv('STUDIO_DATA_DIR',str(ROOT/'.local')))
TZ=ZoneInfo('Asia/Shanghai')

def now(): return dt.datetime.now(TZ)

def request(url,headers=None,payload=None,timeout=20):
    h={'User-Agent':'XiaopengStudio/1.0','Accept-Encoding':'gzip'};h.update(headers or {})
    data=json.dumps(payload,ensure_ascii=False).encode() if payload is not None else None
    if data:h['Content-Type']='application/json'
    with urllib.request.urlopen(urllib.request.Request(url,data=data,headers=h),timeout=timeout) as response:
        raw=response.read(8_000_000)
        if response.headers.get('Content-Encoding')=='gzip':raw=gzip.decompress(raw)
        return raw.decode('utf-8',errors='replace')

def token():
    env=os.getenv('WMCLOUD_TOKEN')
    if env:return env.strip()
    path=PRIVATE/'wmcloud_token.txt'
    return path.read_text().strip() if path.exists() else ''

def wmcloud(api,query):
    key=token()
    if not key:raise RuntimeError('通联凭据未配置')
    q=urllib.parse.urlencode({k:v for k,v in query.items() if v is not None})
    payload=json.loads(request('https://api.wmcloud.com/data/v1/api/'+api+'.json?'+q,{'Authorization':'Bearer '+key},timeout=18))
    if payload.get('retCode')==1:return payload.get('data') or []
    if payload.get('retCode')==-1:return []
    # Do not echo remote error bodies, request headers or credentials.
    raise RuntimeError('通联接口不可用（权限或参数），'+api)

def number(v):
    try:
        result=float(v)
        return result if math.isfinite(result) else None
    except (ValueError,TypeError):return None

def normalize_industry_rows(rows,trade_date):
    industries=[];flows=[];seen=set()
    for row in rows:
        code=str(row.get('industryID',''))
        if len(code)!=8 or code in seen:continue
        # Reject an explicitly mismatched date; an omitted date remains tied to the exact-date query.
        if row.get('tradeDate') and str(row['tradeDate']).replace('-','')[:8]!=trade_date.replace('-',''):continue
        name=row.get('industryName');pct=number(row.get('chgPct'))
        if not name or pct is None:continue
        seen.add(code);pct=round(pct*100,2)
        industries.append({'name':name,'pct':pct,'industry_id':code})
        net=number(row.get('netMainInflow'))
        if net is None:continue  # Missing is not zero; a genuine zero is retained.
        flows.append({'name':name,'code':code,'pct':pct,'net_yi':round(net/1e8,2),'net_pct':None,
                      'observed_at':trade_date+'T15:00:00+08:00','available_at':trade_date+'T16:00:00+08:00',
                      'source':'通联数据 market/getMktInstEqudV1','source_label':'通联数据',
                      'scope':'通联中信一级行业主力净流入（netMainInflow），不代表全部资金；未提供资金占比',
                      'validation':'指定交易日、一级行业ID、数值与单位检查；涨跌和主力净额来自同一行业快照，非独立供应商交叉验证',
                      'divergence':'领涨流出' if pct>0 and net<0 else '领跌流入' if pct<0 and net>0 else None})
    return industries,flows

def select_industry_flows(rows):
    ranked=sorted(rows,key=lambda r:r['pct'],reverse=True)
    selected=ranked[:5]+ranked[-5:]+sorted(rows,key=lambda r:r['net_yi'],reverse=True)[:5]+sorted(rows,key=lambda r:r['net_yi'])[:5]
    selected+=[r for r in ranked if r['divergence']=='领涨流出'][:3]
    selected+=[r for r in reversed(ranked) if r['divergence']=='领跌流入'][:3]
    return list({r['code']:r for r in selected}.values())

def market(cutoff):
    # Before 16:00, do not claim that today's daily API is a complete close.
    day=cutoff.date() if cutoff.hour>=16 else cutoff.date()-dt.timedelta(days=1)
    begin=(day-dt.timedelta(days=25)).strftime('%Y%m%d');end=day.strftime('%Y%m%d')
    snapshots=[];gaps=[]
    for code,name in [('000001','上证指数'),('399001','深成指'),('399006','创业板指')]:
        try:rows=wmcloud('market/getMktIdxd',{'ticker':code,'beginDate':begin,'endDate':end,'field':'ticker,tradeDate,closeIndex,turnoverValue'})
        except Exception:gaps.append(name+'通联接口不可用');continue
        rows=sorted([r for r in rows if r.get('tradeDate') and r['tradeDate'][:10]<=day.isoformat()],key=lambda r:r['tradeDate'])
        if len(rows)<2:gaps.append(name+'缺完整对比记录');continue
        latest,prior=rows[-1],rows[-2];close,previous=number(latest.get('closeIndex')),number(prior.get('closeIndex'))
        if close is None or not previous:continue
        snapshots.append({'name':name,'ticker':code,'date':latest['tradeDate'][:10],'prior_date':prior['tradeDate'][:10],
                          'close':close,'pct':round((close/previous-1)*100,2)})
    if not snapshots:raise RuntimeError('通联指数行情未取得')
    if len(snapshots)<3:gaps.append('指数不完整，仅保留实际取得的指数')
    dates={x['date'] for x in snapshots}
    if len(dates)!=1:raise RuntimeError('指数交易日不一致')
    trade_date=snapshots[0]['date'];prior_date=snapshots[0]['prior_date']
    def equities(date):
        data=wmcloud('market/getMktEqud',{'tradeDate':date.replace('-',''),'field':'ticker,exchangeCD,closePrice,preClosePrice,turnoverValue,isOpen'})
        return [x for x in data if x.get('exchangeCD') in {'XSHG','XSHE'} and not str(x.get('ticker','')).startswith(('200','900')) and str(x.get('isOpen',1)) in {'1','1.0','True','true'}]
    try:stocks=equities(trade_date);previous=equities(prior_date)
    except Exception:stocks=[];previous=[]
    if not stocks or not previous:gaps.append('沪深成交额或比较交易日缺失，省略量能比较')
    amount=sum(number(r.get('turnoverValue')) or 0 for r in stocks)/1e8 if stocks else None
    previous_amount=sum(number(r.get('turnoverValue')) or 0 for r in previous)/1e8 if previous else None
    breadth={'up':0,'down':0,'flat':0}
    for r in stocks:
        close,pre=number(r.get('closePrice')),number(r.get('preClosePrice'))
        if close is None or not pre:continue
        breadth['up' if close>pre else 'down' if close<pre else 'flat']+=1
    industries=[];industry_flows=[]
    try:
        raw=wmcloud('market/getMktInstEqudV1',{'tradeDate':trade_date.replace('-',''),'industryLevel':1,
             'field':'tradeDate,industryID,industryName,chgPct,netMainInflow'})
        industries,industry_flows=normalize_industry_rows(raw,trade_date)
        if not industries:gaps.append('一级行业涨跌未取得')
        if not industry_flows:gaps.append('通联一级行业主力净流入未取得')
    except Exception:gaps.append('通联一级行业涨跌与主力资金接口不可用')

    industries.sort(key=lambda r:r['pct'],reverse=True)
    observed=trade_date+'T15:00:00+08:00'
    return {'source':'通联数据','kind':'完整日终行情','trade_date':trade_date,'previous_date':prior_date,
            'observed_at':observed,'collected_at':now().isoformat(),'indices':snapshots,'turnover_yi':round(amount,2) if amount is not None else None,
            'previous_turnover_yi':round(previous_amount,2) if previous_amount is not None else None,'delta_yi':round(amount-previous_amount,2) if amount is not None and previous_amount is not None else None,
            'breadth':breadth if stocks else None,'gainers':industries[:5],'losers':sorted(industries,key=lambda r:r['pct'])[:5],
            'flows':select_industry_flows(industry_flows),'industry_count':len(industries),'flow_count':len(industry_flows),
            'flow_scope':'通联中信一级行业主力净流入，供应商统计口径，不代表全部资金；未提供主力资金占比',
            'scope':'沪深A股，不含北交所和B股；行业为通联一级行业，不与ETF分类混排','gaps':gaps,
            'limitations':['未取得盘中快照权限；日终数据不得称为当前盘中行情。','行业涨跌是行情事实，不直接证明新闻因果。']}

def clean(text):return html.unescape(re.sub(r'<[^>]+>','',str(text or ''))).strip()

def news(cutoff,terms):
    raw=request('https://www.cls.cn/',timeout=15)
    m=re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',raw,re.S)
    if not m:raise RuntimeError('财联社页面结构变化，未提取到新闻')
    props=json.loads(m[1])['props']['pageProps'];assemble=props.get('assembleData',{})
    rows=assemble.get('top_article',[])+assemble.get('depth_list',[])
    bar=assemble.get('roll_bar')
    if isinstance(bar,dict):rows.append(bar)
    candidates=[];seen=set()
    for r in rows:
        try:published=dt.datetime.fromtimestamp(int(r['ctime']),TZ)
        except (KeyError,ValueError,TypeError):continue
        if not cutoff-dt.timedelta(days=7)<=published<=cutoff:continue
        aid=r.get('id')
        if not aid or aid in seen:continue
        seen.add(aid);title=clean(r.get('title'));brief=clean(r.get('brief'))
        if not brief and not title:continue
        score=sum(t in title+brief for t in terms)*5
        candidates.append((score,published,{'id':'NEWS-'+str(aid),'source':'财联社','title':title or brief[:45],
          'excerpt':brief[:360],'published_at':published.isoformat(),'url':'https://www.cls.cn/detail/'+str(aid),
          'scope':'公开页面摘要；未读取付费栏目，未声称已读完整报道','verification':'media_summary_not_primary_announcement'}))
    candidates.sort(key=lambda x:(-x[0],-x[1].timestamp()))
    return [x[2] for x in candidates[:8] if x[0]>0 or not terms][:6]

def research(cutoff,terms):
    end=cutoff.date();begin=end-dt.timedelta(days=30);found=[]
    for page in range(1,3):
        params={'pageSize':50,'pageNo':page,'beginTime':begin.isoformat(),'endTime':end.isoformat(),'qType':1,'industry':'*','rating':'*'}
        data=json.loads(request('https://reportapi.eastmoney.com/report/list?'+urllib.parse.urlencode(params),timeout=15))
        for r in data.get('data') or []:
            when=str(r.get('publishDate') or '')[:10]
            # Report day-only timestamps do not establish premarket availability.
            if not when or when>=cutoff.date().isoformat():continue
            title=str(r.get('title') or '');industry=str(r.get('industryName') or '')
            if terms and not any(t in title+industry for t in terms):continue
            if r.get('attachPages') is not None and int(r['attachPages'])<=2:continue
            url='https://data.eastmoney.com/report/zw_industry.jshtml?encodeUrl='+urllib.parse.quote(str(r.get('encodeUrl') or ''),safe='')
            try:
                body=request(url,timeout=12)
                paragraph=[clean(x) for x in re.findall(r'<p[^>]*>(.*?)</p>',body,re.S)]
                paragraph=[p for p in paragraph if p and not any(s in p for s in ['郑重声明','东方财富网发布此信息'])]
                excerpt=' '.join(paragraph)[:850]
            except Exception:excerpt=''
            if not excerpt:continue
            found.append({'id':'REPORT-'+str(r.get('infoCode')),'title':title,'source':r.get('orgSName'),'date':when,
                          'url':url,'excerpt':excerpt,'scope':'研报公开详情摘要；预测不等于实际业绩，未读取PDF全文'})
            if len(found)>=3:return found
    return found

def collect(column,terms,cutoff):
    output={'cutoff':cutoff.isoformat(),'market':None,'news':[],'research':[],'gaps':[],'collected_at':now().isoformat()}
    tasks={'market':lambda:market(cutoff),'news':lambda:news(cutoff,terms),'research':lambda:research(cutoff,terms)}
    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        work={name:pool.submit(fn) for name,fn in tasks.items()}
        for name,f in work.items():
            try:output[name]=f.result()
            except Exception:output['gaps'].append({'source':name,'message':{'market':'通联行情未完整取得','news':'财经新闻未取得','research':'研报摘要未取得'}[name]})
    from market_extra import supplement_market,global_market
    output['market'],extra_gaps=supplement_market(output['market'],cutoff)
    if not output['market']:
        output['gaps'] += [{'source':'market','message':g} for g in extra_gaps]
    output['global']=[]
    if column=='每日必看':
        output['global'],global_gaps=global_market(cutoff);output['gaps']+=global_gaps
    if not terms and output['market']:
        output['suggested_terms']=list(dict.fromkeys(r['name'] for key in ['gainers','losers'] for r in output['market'].get(key,[])))[:8]
    if not output['news']:output['gaps'].append({'source':'news','message':'截点前没有匹配到可用新闻摘要'})
    if not output['research']:output['gaps'].append({'source':'research','message':'本次主题未取得可读取研报摘要，不能引用研报结论'})
    if column=='盘中实操':output['gaps'].append({'source':'intraday','message':'现有通联权限不含盘中快照；只用已完成日终参考，不编盘中新买卖点'})
    if output['market']:output['gaps']+= [{'source':'market','message':m} for m in output['market']['gaps']]
    return output
