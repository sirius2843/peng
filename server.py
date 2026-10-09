#!/usr/bin/env python3
"""Loopback preview and deployable same-origin backend. No static secret serving."""
import argparse,datetime as dt,hashlib,hmac,json,os,secrets,sqlite3,sys,threading,time,urllib.parse
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent/'backend'))
import knowledge,providers,writer,preferences,learning,author_inputs,viewpoints

ROOT=Path(__file__).resolve().parent;PRIVATE=providers.PRIVATE;PRIVATE.mkdir(parents=True,exist_ok=True)
DB=PRIVATE/'studio.sqlite';CSRF=secrets.token_urlsafe(32);JOBS={};LOCK=threading.Lock();CACHE={};SESSIONS={}
PASSWORD=os.getenv('APP_ACCESS_PASSWORD','')
COLS=['每日必看','盘中实操','风口收评','本周来信','行业/事件点评']

def db():
    con=sqlite3.connect(DB,timeout=15);con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE IF NOT EXISTS drafts(id TEXT PRIMARY KEY,column_name TEXT,title TEXT,body TEXT,created TEXT,payload TEXT)');learning.schema(con);learning.initialize_versions(con);con.commit();return con

def records():
    with db() as con:rows=con.execute('SELECT * FROM drafts ORDER BY created DESC').fetchall()
    return [dict(r) for r in rows]

def public_record(r):
    data=json.loads(r['payload']);vs=learning.versions(r['id']);new=data.get('draft',{}).get('new_judgments',[])
    new=[j for j in new if isinstance(j,dict) and j.get('claim_id') and j.get('judgment')] if isinstance(new,list) else []
    return {'id':r['id'],'column':r['column_name'],'title':r['title'],'body':r['body'],'created':r['created'],
          'new_judgments':new,'confirmed_judgments':[j for j in data.get('confirmed_judgments',[]) if j.get('text') and j['text'] in r['body']],'voice_review':data.get('voice_review'),'author_inputs':data.get('sources',{}).get('author_inputs',[]),'scene':data.get('context',{}).get('scene','平稳'),'review':data.get('review'),'sources':data.get('sources'),'review_notes':data.get('draft',{}).get('review_notes',[]),
          'version_id':vs[-1]['id'] if vs else None,'version_count':len(vs),'sample':bool(data.get('sample')),'knowledge_version':data.get('context',{}).get('distillation',{}).get('version'),'feedback_submitted':any(f['record_id']==r['id'] for f in learning.feedback_list()),'viewpoint_snapshot':data.get('viewpoint_snapshot'),'selected_operations':data.get('selected_operations',[]),'edited':data.get('edited',False)}

def save_record(column,result,sources,context,previous_id=None):
    rid=secrets.token_hex(12);draft=result['draft'];created=providers.now().isoformat()
    payload={**result,'generation_review':result.get('review'),'sources':sources,'context':context,'previous_id':previous_id}
    with db() as con:
        con.execute('INSERT INTO drafts VALUES(?,?,?,?,?,?)',(rid,column,draft['title'],draft['body'],created,json.dumps(payload,ensure_ascii=False)))
        learning.initial(con,rid,draft['title'],draft['body'],created,actor='simulation' if result.get('sample') else 'model',reason='人工模拟素材，未调用模型' if result.get('sample') else '模型初稿；保留当次资料与知识快照')
    return public_record({'id':rid,'column_name':column,'title':draft['title'],'body':draft['body'],'created':created,'payload':json.dumps(payload,ensure_ascii=False)})

def cutoff_for(column):
    t=providers.now()
    if column=='每日必看':t=min(t,t.replace(hour=8,minute=45,second=0,microsecond=0))
    return t

def job_run(jid,payload):
    try:
        column=payload['column'];intent=payload.get('intent','');revision=None
        cutoff=cutoff_for(column)
        snapshot=payload.get('_viewpoint_snapshot') or viewpoints.latest()
        previous_record=next((r for r in records() if r['id']==payload.get('revision_id')),None) if payload.get('revision_id') else None
        relevance_text=intent+('\n'+previous_record['title']+'\n'+previous_record['body'] if previous_record else '')
        confirmed_inputs,view_notes=viewpoints.facts(snapshot,cutoff,column,relevance_text)
        confirmed_inputs+=author_inputs.normalize(payload,cutoff)
        scene=snapshot.get('scene','平稳') if snapshot.get('revision') and dt.datetime.fromisoformat(snapshot['effective_at'])<=cutoff else payload.get('scene','平稳')
        if scene not in knowledge.SCENES:raise ValueError('请选择有效盘面场景')
        retrieval_text='\n'.join([relevance_text]+[f['text'] for f in confirmed_inputs])
        ctx=knowledge.context(column,retrieval_text,cutoff,scene)
        ctx['column_guidance']=preferences.read()['columns'][column]
        ctx['viewpoint_snapshot']=snapshot;ctx['viewpoint_notes']=view_notes
        operations=preferences.selected(payload.get('operation_ids',[]))
        source_terms=knowledge.infer_topics(column,intent)[1]
        if column=='行业/事件点评' and previous_record and not source_terms:source_terms=knowledge.infer_topics(column,previous_record['title'])[1]
        key=(column,tuple(source_terms),cutoff.strftime('%Y-%m-%dT%H:%M'))
        JOBS[jid].update(stage='读取行情、新闻与研报')
        cached=CACHE.get(key)
        sources=cached if cached else providers.collect(column,source_terms,cutoff)
        if not cached:
            if len(CACHE)>30:CACHE.clear()
            CACHE[key]=sources
        # Cached public sources never contain another request's private author inputs.
        sources={**sources,'author_inputs':confirmed_inputs,'viewpoint_notes':view_notes}
        ctx['news_unfiltered']=not source_terms
        if not retrieval_text.strip() and sources.get('suggested_terms'):
            ctx=knowledge.context(column,' '.join(sources['suggested_terms']),cutoff,scene)
            ctx['terms']=sources['suggested_terms'];ctx['column_guidance']=preferences.read()['columns'][column]
            ctx['news_unfiltered']=True
        ctx['viewpoint_snapshot']=snapshot;ctx['viewpoint_notes']=view_notes;ctx['news_unfiltered']=not source_terms
        if column=='行业/事件点评' and not sources['news'] and not sources['research']:
            raise ValueError('本次未取得与主题匹配的新闻或研报，暂不能写有依据的事件点评。可补充具体行业或事件名称后重试。')
        if not writer.facts_from_sources(sources):raise ValueError('本次没有取到可用材料，暂不生成无依据的文章。')
        recent=[public_record(r) for r in records() if r['column_name']==column and not json.loads(r['payload']).get('sample')][:3]
        if payload.get('revision_id'):
            match=next((r for r in records() if r['id']==payload['revision_id']),None)
            if not match:raise ValueError('找不到要修改的文章')
            previous=json.loads(match['payload'])
            body=match['body'];tail='\n\n'.join(o['text']+('\n入口：'+o['entry_url'] if o.get('entry_url') else '') for o in previous.get('selected_operations',[]))
            if tail and body.endswith('\n\n'+tail):body=body[:-len(tail)-2]
            revision={'previous_title':match['title'],'previous_body':body,'requested_change':intent}
            ctx['revision_request']=intent
        JOBS[jid].update(stage='按历史判断与栏目声音写作')
        result=writer.generate(column,intent,ctx,sources,recent,revision)
        result['viewpoint_snapshot']=snapshot
        result['draft'].setdefault('review_notes',[]).extend(view_notes)
        result['editorial_body']=result['draft']['body'];result['selected_operations']=operations
        if operations:
            result['draft']['body']+='\n\n'+'\n\n'.join(o['text']+('\n入口：'+o['entry_url'] if o.get('entry_url') else '') for o in operations)
            result['review'].setdefault('warnings',[]).append({'message':'运营素材由本次勾选原样添加，机械证据检查针对创作正文。'})
        record=save_record(column,result,sources,ctx,payload.get('revision_id'))
        JOBS[jid].update(status='done',stage='完成',record=record)
    except ValueError as exc:JOBS[jid].update(status='error',error=str(exc)[:250])
    except RuntimeError as exc:JOBS[jid].update(status='error',error=str(exc)[:250])
    except Exception:JOBS[jid].update(status='error',error='本次处理未完成，请稍后重试。')

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args):pass  # Never log headers, keys or article contents.
    def origin_ok(self):
        host=self.headers.get('Host','');allowed={'127.0.0.1:'+str(self.server.server_port),'localhost:'+str(self.server.server_port)}
        public=os.getenv('PUBLIC_ORIGIN','').rstrip('/')
        if public:allowed.add(urllib.parse.urlsplit(public).netloc)
        if host not in allowed:return False
        origin=self.headers.get('Origin')
        return not origin or urllib.parse.urlsplit(origin).netloc==host
    def authenticated(self):
        if not PASSWORD:return True
        cookie=self.headers.get('Cookie','');m=__import__('re').search(r'(?:^|;\s*)studio_session=([\w-]+)',cookie)
        return bool(m and SESSIONS.get(m[1],0)>time.time())
    def send(self,status,obj,extra=None):
        raw=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Content-Length',str(len(raw)));self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        for k,v in (extra or {}).items():self.send_header(k,v)
        self.end_headers();self.wfile.write(raw)
    def body(self):
        length=int(self.headers.get('Content-Length',0))
        if length>100_000:raise ValueError('内容过长')
        return json.loads(self.rfile.read(length) or '{}')
    def do_GET(self):
        if not self.origin_ok():return self.send(403,{'error':'来源不允许'})
        url=urllib.parse.urlsplit(self.path);path=url.path;query=urllib.parse.parse_qs(url.query)
        if path.startswith('/api/'):
            if not self.authenticated():return self.send(401,{'error':'请输入工作台访问密码'})
            if path=='/api/bootstrap':
                config=writer.settings()
                return self.send(200,{'csrf':CSRF,'profile':knowledge.profile(),'preferences':preferences.read(),
                     'records':[public_record(r) for r in records()],'columns':COLS,'now':providers.now().isoformat(),
                     'settings':{'configured':bool(config['api_key']),'model':config['model'],'max_tokens':config.get('max_tokens',12000),'thinking':config.get('thinking','disabled'),'wmcloud':bool(providers.token()),'market_scope':'日终数据已核验；盘中接口需额外权限'},
                     'viewpoints':viewpoints.latest(),'scenes':list(knowledge.SCENES),'sample':None})
            if path=='/api/viewpoints':return self.send(200,viewpoints.latest())
            if path=='/api/viewpoints/history':return self.send(200,viewpoints.history())
            if path=='/api/knowledge':return self.send(200,knowledge.profile())
            if path.startswith('/api/knowledge/evidence/'):
                try:return self.send(200,learning.evidence(path.rsplit('/',1)[-1]))
                except ValueError as exc:return self.send(404,{'error':str(exc)})
            if path.startswith('/api/knowledge/history/'):return self.send(200,learning.card_history(path.rsplit('/',1)[-1]))
            if path.startswith('/api/records/versions/'):
                return self.send(200,learning.versions(path.rsplit('/',1)[-1]))
            if path=='/api/feedback':return self.send(200,learning.feedback_list())
            if path=='/api/feedback/export':return self.send(200,learning.export_feedback())
            if path.startswith('/api/jobs/'):
                job=JOBS.get(path.rsplit('/',1)[-1]);return self.send(200 if job else 404,job or {'error':'任务不存在'})
            if path=='/api/records':return self.send(200,[public_record(r) for r in records()])
            return self.send(404,{'error':'接口不存在'})
        files={'/':'index.html','/index.html':'index.html','/style.css':'style.css','/app.js':'app.js','/favicon.svg':'favicon.svg'}
        if path not in files:return self.send(404,{'error':'文件不可访问'})
        file=ROOT/'web'/files[path]
        if not file.exists():return self.send(404,{'error':'文件不存在'})
        raw=file.read_bytes();mime={'.html':'text/html','.css':'text/css','.js':'text/javascript','.svg':'image/svg+xml'}[file.suffix]
        self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.send_header('Content-Length',str(len(raw)))
        self.send_header('Cache-Control','no-cache');self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'self'")
        self.end_headers();self.wfile.write(raw)
    def do_POST(self):
        if not self.origin_ok():return self.send(403,{'error':'来源不允许'})
        path=urllib.parse.urlsplit(self.path).path
        try:
            data=self.body()
            if path=='/api/login':
                if not PASSWORD or not hmac.compare_digest(str(data.get('password','')),PASSWORD):return self.send(401,{'error':'访问密码不正确'})
                sid=secrets.token_urlsafe(32);SESSIONS[sid]=time.time()+12*3600
                secure='; Secure' if os.getenv('PUBLIC_ORIGIN','').startswith('https:') else ''
                return self.send(200,{'ok':True},{'Set-Cookie':f'studio_session={sid}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200'+secure})
            if not self.authenticated():return self.send(401,{'error':'请先登录'})
            if not hmac.compare_digest(self.headers.get('X-Studio-Token',''),CSRF):return self.send(403,{'error':'请刷新页面后重试'})
            if path=='/api/viewpoints/save':return self.send(200,viewpoints.save(data))
            if path=='/api/knowledge/save':return self.send(200,learning.save_card(data))
            if path=='/api/feedback/prepare':return self.send(200,learning.prepare_feedback(data.get('record_id')))
            if path=='/api/feedback/submit':return self.send(200,learning.submit_feedback(data))
            if path=='/api/feedback/change':return self.send(200,learning.change_feedback(data))
            if path=='/api/preferences/column':
                result=preferences.save_column(str(data.get('column','')),str(data.get('summary','')),str(data.get('logic','')))
                return self.send(200,result)
            if path=='/api/preferences/operations':
                return self.send(200,preferences.save_operations(data.get('items')))
            if path=='/api/settings':
                current=writer.settings();key=str(data.get('api_key','')).strip() or current['api_key']
                if len(key)<12 or len(key)>256:return self.send(400,{'error':'请填写有效的API Key'})
                model=str(data.get('model',current['model'])).strip()
                if not __import__('re').fullmatch(r'[a-zA-Z0-9_.-]{1,80}',model):raise ValueError('模型名称格式不正确')
                budget=int(data.get('max_tokens',current.get('max_tokens',12000)))
                thinking=data.get('thinking',current.get('thinking','disabled'))
                if not 2000<=budget<=64000 or thinking not in {'enabled','disabled'}:raise ValueError('输出预算需在2000至64000之间，思考模式需有效')
                config={'api_key':key,'model':model,'max_tokens':budget,'thinking':thinking};target=PRIVATE/'deepseek.json'
                target.write_text(json.dumps(config));target.chmod(0o600)
                return self.send(200,{k:v for k,v in config.items() if k!='api_key'}|{'configured':True})
            if path=='/api/settings/test':
                key=writer.settings()['api_key']
                if not key:return self.send(400,{'error':'请先保存密钥'})
                try:
                    result=json.loads(providers.request('https://api.deepseek.com/models',{'Authorization':'Bearer '+key},timeout=15))
                    available=[r.get('id') for r in result.get('data',[])];current=writer.settings()['model']
                    if current not in available:return self.send(400,{'error':'当前模型不在可用列表，可用模型：'+', '.join(str(x) for x in available if x)})
                    return self.send(200,{'ok':True,'model':current,'available_models':available})
                except Exception:return self.send(400,{'error':'连接未成功，请检查密钥或网络'})
            if path=='/api/records/confirm-judgments':
                rid=data.get('id');chosen=data.get('claim_ids',[])
                if not isinstance(chosen,list) or not chosen:raise ValueError('请选择要确认的新增判断')
                with db() as con:
                    con.execute('BEGIN IMMEDIATE')
                    row=con.execute('SELECT * FROM drafts WHERE id=?',(rid,)).fetchone()
                    if not row:raise ValueError('文章不存在')
                    payload=json.loads(row['payload'])
                    if payload.get('sample'):raise ValueError('模拟稿不能确认成当期观点')
                    versions=learning.versions(rid,con)
                    if data.get('expected_version')!=(versions[-1]['id'] if versions else None):raise ValueError('稿件已更新，请刷新后重新确认')
                    new={x['claim_id']:x for x in payload.get('draft',{}).get('new_judgments',[])}
                    claims={x['id']:x for x in payload.get('draft',{}).get('claims',[])}
                    if any(cid not in new or cid not in claims or claims[cid]['sentence'] not in row['body'] for cid in chosen):
                        raise ValueError('所选判断已修改或不存在，请先核对最新正文')
                    accepted={x['claim_id']:x for x in payload.get('confirmed_judgments',[])}
                    for cid in chosen:accepted[cid]={'claim_id':cid,'text':claims[cid]['sentence'],'horizon':claims[cid].get('horizon','short'),'confirmed_at':providers.now().isoformat(),'version_id':data.get('expected_version')}
                    payload['confirmed_judgments']=list(accepted.values())
                    con.execute('UPDATE drafts SET payload=? WHERE id=?',(json.dumps(payload,ensure_ascii=False),rid))
                    updated=dict(row);updated['payload']=json.dumps(payload,ensure_ascii=False)
                return self.send(200,public_record(updated))
            if path=='/api/generate':
                if not writer.settings()['api_key']:return self.send(400,{'error':'请先配置DeepSeek API Key','code':'missing_key'})
                mode=data.get('mode','column');column=data.get('column','盘中实操')
                if mode=='article':column='行业/事件点评'
                if column not in COLS:return self.send(400,{'error':'请选择有效栏目'})
                intent=str(data.get('intent','')).strip()
                if mode=='article' and not intent:return self.send(400,{'error':'请写下想讨论的事件或行业'})
                if len(intent)>8000:return self.send(400,{'error':'补充内容过长，请精简'})
                if sum(j.get('status')=='running' for j in JOBS.values())>=2:return self.send(429,{'error':'已有文章在生成，请等待完成'})
                snapshot=viewpoints.latest()
                if data.get('viewpoint_revision',0)!=snapshot['revision']:raise ValueError('共享观点已更新，请载入最新版本再生成')
                jid=secrets.token_hex(12);JOBS[jid]={'status':'running','stage':'整理历史案例'}
                threading.Thread(target=job_run,args=(jid,{**data,'column':column,'intent':intent,'_viewpoint_snapshot':snapshot}),daemon=True).start()
                return self.send(202,{'job_id':jid})
            if path=='/api/records/edit':
                rid=data.get('id');title=str(data.get('title','')).strip();body=str(data.get('body','')).strip()
                if not title or not body or len(body)>25000:return self.send(400,{'error':'标题和正文不能为空，正文需适当精简'})
                with db() as con:
                    con.execute('BEGIN IMMEDIATE')
                    row=con.execute('SELECT * FROM drafts WHERE id=?',(rid,)).fetchone()
                    if not row:return self.send(404,{'error':'文章不存在'})
                    payload=json.loads(row['payload']);payload.setdefault('generation_review',payload.get('review'));payload['edited']=True
                    v=learning.append_version(con,rid,title,body,'author_edit',data.get('reason',''),expected=data.get('expected_version'))
                    payload['review']={'mechanical_pass':False,'edited':True,'warnings':[{'message':'正文已手动编辑，原生成证据对应需重新审阅'}]}
                    con.execute('UPDATE drafts SET title=?,body=?,payload=? WHERE id=?',(title,body,json.dumps(payload,ensure_ascii=False),rid))
                learning.export_feedback()
                with db() as con:updated=con.execute('SELECT * FROM drafts WHERE id=?',(rid,)).fetchone()
                return self.send(200,public_record(dict(updated)))
            return self.send(404,{'error':'接口不存在'})
        except learning.Conflict as exc:return self.send(409,{'error':str(exc)})
        except ValueError as exc:return self.send(400,{'error':str(exc)[:300]})
        except KeyError:return self.send(400,{'error':'输入格式不正确'})
        except Exception:return self.send(500,{'error':'操作未完成，请稍后重试'})

def main():
    p=argparse.ArgumentParser();p.add_argument('--host',default='127.0.0.1');p.add_argument('--port',type=int,default=16688);args=p.parse_args()
    if args.host not in {'127.0.0.1','localhost'} and (not PASSWORD or not os.getenv('PUBLIC_ORIGIN')):
        raise SystemExit('对外部署须设置APP_ACCESS_PASSWORD与PUBLIC_ORIGIN')
    with db():pass
    server=ThreadingHTTPServer((args.host,args.port),Handler)
    print(f'小鹏哥内容工作台 http://{args.host}:{args.port}',flush=True);server.serve_forever()

if __name__=='__main__':main()
