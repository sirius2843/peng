"""Free supplementary quotes with explicit timestamps and validation boundaries."""
import concurrent.futures as futures
import datetime as dt
import json,re,urllib.parse
from zoneinfo import ZoneInfo
from providers import request,number,TZ

EM='https://push2.eastmoney.com/api/qt/'
def em(path,params):
    url=EM+path+'?'+urllib.parse.urlencode(params)
    data=None
    for host in ['push2.eastmoney.com','82.push2.eastmoney.com']:
        try:
            data=json.loads(request(url.replace('push2.eastmoney.com',host),{'User-Agent':'Mozilla/5.0','Referer':'https://quote.eastmoney.com/'},timeout=10));break
        except Exception:continue
    if data is None:raise RuntimeError('东方财富备用行情接口不可用')
    return data.get('data') or {}

def completed_stamp(value,cutoff):
    stamp=dt.datetime.fromtimestamp(int(value),TZ)
    # Quote endpoints expose live data, never use an incomplete session or a future snapshot.
    if stamp>cutoff or stamp.hour<15 or stamp.replace(hour=16,minute=0,second=0,microsecond=0)>cutoff:raise ValueError('非完整收盘或超过截点')
    return stamp

def historical_index(sec,code,name,cutoff):
    last_day=cutoff.date() if cutoff.hour>=16 else cutoff.date()-dt.timedelta(days=1)
    raw=request('https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urllib.parse.urlencode({
        'secid':sec,'klt':101,'fqt':0,'lmt':30,'end':last_day.strftime('%Y%m%d'),
        'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}),timeout=15)
    quotes=(json.loads(raw).get('data') or {}).get('klines',[])
    rows=[r.split(',') for r in quotes if r.split(',')[0]<=last_day.isoformat()]
    if len(rows)<2:raise RuntimeError('历史报价不足')
    latest=rows[-1];close=number(latest[2]);previous=number(rows[-2][2])
    other=json.loads(request('https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?'+urllib.parse.urlencode({'param':code+',day,,,30,qfq'}),timeout=15))['data'][code]
    peers=other.get('day') or other.get('qfqday') or []
    peer=next((r for r in peers if r[0]==latest[0]),None)
    prior=next((r for r in peers if r[0]==rows[-2][0]),None)
    if not close or not previous or not peer or not prior or abs(float(peer[2])-close)>.05 or abs(float(prior[2])-previous)>.05:
        raise RuntimeError('历史指数交叉验证不一致')
    if cutoff.date()-dt.date.fromisoformat(latest[0])>dt.timedelta(days=14):raise RuntimeError('历史指数过旧')
    return {'name':name,'date':latest[0],'close':close,'pct':round((close/previous-1)*100,2)}

def fallback_indices(cutoff):
    rows=[];gaps=[]
    items=[('1.000001','sh000001','上证指数'),('0.399001','sz399001','深成指'),('0.399006','sz399006','创业板指')]
    with futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(historical_index,*item,cutoff):item for item in items}
        for f,item in jobs.items():
            try:rows.append(f.result())
            except Exception:gaps.append(item[2]+'备用历史报价未通过东方财富/腾讯交叉验证，已排除')
    if len({r['date'] for r in rows})>1:return [],gaps+['备用指数日期不同，已排除']
    return rows,gaps

def sectors(cutoff):
    # Backup industry prices only; money flow is provided by WMCloud.
    data=em('clist/get',{'pn':1,'pz':200,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f3','fs':'m:90+t:2',
        'fields':'f12,f14,f3,f124'})
    rows=data.get('diff',[])
    if isinstance(rows,dict):rows=list(rows.values())
    total=data.get('total',0)
    if rows and len(rows)<total:
        page_size=len(rows)
        with futures.ThreadPoolExecutor(max_workers=4) as pool:
            jobs=[pool.submit(em,'clist/get',{'pn':page,'pz':page_size,'po':1,'np':1,'fltt':2,'invt':2,'fid':'f3','fs':'m:90+t:2','fields':'f12,f14,f3,f124'}) for page in range(2,(total+page_size-1)//page_size+1)]
            for f in jobs:
                diff=f.result().get('diff',[])
                rows+=list(diff.values()) if isinstance(diff,dict) else diff
        if len({r['f12'] for r in rows})<total:raise RuntimeError('行业排行分页不完整，不能冒称完整领涨领跌')
    result=[]
    for r in rows:
        try:
            stamp=completed_stamp(r['f124'],cutoff)
            pct=number(r['f3'])
            if pct is None:continue
            result.append({'name':str(r['f14']),'code':str(r['f12']),'pct':pct,
                'date':stamp.date().isoformat(),'observed_at':stamp.isoformat(),
                'available_at':stamp.date().isoformat()+'T16:00:00+08:00',
                'source':'https://quote.eastmoney.com/center/boardlist.html',
                'validation':'东方财富时间与完整行业排名检查；未取得独立机构同分类验证'})
        except (KeyError,ValueError,TypeError):continue
    if not result:raise RuntimeError('备用行业行情快照未取得')
    latest=max(r['date'] for r in result)
    return [r for r in result if r['date']==latest]

def supplement_market(primary,cutoff):
    gaps=[];m=dict(primary or {});m.setdefault('indices',[]);m.setdefault('gainers',[]);m.setdefault('losers',[])
    if len(m['indices'])==3 and m['gainers'] and m['losers']:
        return m,[]
    with futures.ThreadPoolExecutor(max_workers=2) as pool:
        idx=pool.submit(fallback_indices,cutoff) if len(m['indices'])<3 else None
        sec=pool.submit(sectors,cutoff)
        if idx:
            rows,notes=idx.result();gaps+=notes
            existing={r['name'] for r in m['indices']}
            m['indices'] += [r for r in rows if r['name'] not in existing and (not m.get('trade_date') or r['date']==m['trade_date'])]
            if rows and not m.get('trade_date'):m.update(source='东方财富 / 腾讯交叉验证',trade_date=rows[0]['date'],observed_at=rows[0]['date']+'T15:00:00+08:00')
        try:rows=sec.result()
        except Exception:rows=[];gaps.append('东方财富备用行业涨跌未取得')
    if rows:
        date=rows[0]['date']
        if m.get('trade_date') and date!=m['trade_date']:
            gaps.append('备用行业涨跌与日终行情日期不同，已排除');rows=[]
        elif not m.get('trade_date'):
            m.update(trade_date=date,observed_at=date+'T15:00:00+08:00',source='东方财富公开行业报价')
    if rows:
        ranked=sorted(rows,key=lambda r:r['pct'],reverse=True)
        # Keep providers' taxonomies distinct; do not merge names into one ranking.
        if not m['gainers'] or not m['losers']:
            m['gainers']=[{'name':r['name'],'pct':r['pct']} for r in ranked[:5]]
            m['losers']=[{'name':r['name'],'pct':r['pct']} for r in sorted(rows,key=lambda r:r['pct'])[:5]]
            gaps.append('行业排行采用东方财富行业板块，已核验来源与时点，未取得独立供应商的相同分类验证')
        # This adapter supplies backup prices only; industry money flow comes exclusively from WMCloud.
    if not m.get('trade_date'):return primary,gaps
    m.setdefault('scope','各来源明确列出的范围；未取得完整沪深成交额和涨跌家数')
    m['gaps']=list(m.get('gaps',[]))+gaps
    return m,gaps

GLOBAL=[('SPX','^GSPC','标普500','America/New_York',16,0),('DJI','^DJI','道琼斯','America/New_York',16,0),
        ('IXIC','^IXIC','纳斯达克','America/New_York',16,0),('FTSE','^FTSE','英国富时100','Europe/London',16,30),
        ('DAX','^GDAXI','德国DAX','Europe/Berlin',17,30),('TNX','^TNX','美国十年国债收益率','America/New_York',16,0),
        ('OIL','CL=F','WTI原油期货',None,0,0),('GOLD','GC=F','COMEX黄金期货',None,0,0)]

def global_quote(item,cutoff):
    key,symbol,name,zone,hour,minute=item
    params={'range':'1mo','interval':'1d' if zone else '1h'}
    url='https://query1.finance.yahoo.com/v8/finance/chart/'+urllib.parse.quote(symbol,safe='')+'?'+urllib.parse.urlencode(params)
    r=json.loads(request(url,{'User-Agent':'Mozilla/5.0'},timeout=15))['chart']['result'][0]
    closes=r['indicators']['quote'][0]['close'];observations=[]
    for epoch,value in zip(r.get('timestamp',[]),closes):
        if number(value) is None:continue
        stamp=dt.datetime.fromtimestamp(epoch,ZoneInfo(zone) if zone else TZ)
        observed=stamp.replace(hour=hour,minute=minute,second=0,microsecond=0) if zone else stamp+dt.timedelta(hours=1)
        if observed<=cutoff:observations.append((observed,round(float(value),3 if key=='TNX' else 2)))
    if len(observations)<2:raise RuntimeError('海外报价不足')
    observed,close=observations[-1];previous=observations[-2][1]
    if cutoff-observed>dt.timedelta(days=5):raise RuntimeError('海外报价过旧')
    change=round((close/previous-1)*100,2)
    if key=='TNX':text=f"{name}{close}%，对比上一完整交易日变化{round((close-previous)*100,2)}基点（{'上升' if close>=previous else '下降'}{abs(round((close-previous)*100,2))}基点）。"
    elif not zone:text=f'{name}最近完整小时参考价{close}美元，观测时间{observed.astimezone(TZ).isoformat()}；为期货价格，非现货或正式日结算价。'
    else:text=f"{name}收盘{close}点，涨跌幅{change}%（{'上涨' if change>=0 else '下跌'}{abs(change)}%），交易日{observed.date().isoformat()}。"
    return {'id':'GLOBAL-'+key,'text':text,'source':'https://finance.yahoo.com/quote/'+urllib.parse.quote(symbol,safe='')+'/',
            'observed_at':observed.astimezone(TZ).isoformat(),'available_at':observed.astimezone(TZ).isoformat()}

def global_market(cutoff):
    result=[];gaps=[]
    with futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(global_quote,item,cutoff):item for item in GLOBAL}
        for f,item in jobs.items():
            try:result.append(f.result())
            except Exception:gaps.append({'source':'global','message':item[2]+'免费报价未取得，不生成对应隔夜结论'})
    return result,gaps
