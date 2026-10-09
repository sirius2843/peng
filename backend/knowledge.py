"""Private local corpus retrieval and public-facing distilled profile."""
import json,re
from pathlib import Path
from providers import PRIVATE, ROOT

def load(name):
 data=json.loads((PRIVATE/name).read_text())
 if name=='article_metadata_v2.json':
  dates=json.loads((ROOT/'knowledge/original_verification.json').read_text())
  for row in data:
   check=dates.get(str(row['article_id']),{})
   if check.get('date'):row['dates']={**row.get('dates',{}),'candidate_publication_date':check['date'],'verified_publication_timestamp':True,'published_at':check['published_at'],'basis':'original_publisher_timestamp'}
 return data

def profile():
    import learning
    return learning.catalog()

def history(column=None):
    meta={m['article_id']:m for m in load('article_metadata_v2.json')};result=[]
    for row in load('corpus_index.json'):
        m=meta[row['article_id']]
        if not m['core_voice'] or (column and m['column']!=column):continue
        result.append({'id':row['article_id'],'title':row['title'],'column':m['column'],'date_label':row['publish_time'],
                       'source_url':row['url'],'excerpt':row['editorial_text'][:150],'order':row['source_index']})
    return sorted(result,key=lambda x:x['order'])[:36]

def article(aid):
    row=next((a for a in load('corpus_index.json') if str(a['article_id'])==str(aid)),None)
    if not row:return None
    core=next(m['core_voice'] for m in load('article_metadata_v2.json') if m['article_id']==row['article_id'])
    if not core:return None
    return {'id':row['article_id'],'title':row['title'],'body':row['text'],'date_label':row['publish_time'],'source_url':row['url'],'column':row['column']}

ALIASES={'美股科技':['纳斯达克','纳指','美股科技','英伟达'],'红利':['红利','股息','分红'],'A股科技':['科技','半导体','芯片','光模块','通信','设备'],'创新药':['创新药','医药','生物'],'黄金':['黄金','金价','美债','利率'],
         '港股科技':['恒生科技','港科','港股','阿里','腾讯'],'指数与量能':['大盘','指数','成交','量能','收评'],'证券':['证券','券商'],
         'AI应用':['AI应用','Ai应用','软件','云服务','传媒'],
         '新能源':['新能源','电池','光伏','储能','新能源车'],'机器人':['机器人','自动化'],'商业航天':['商业航天','卫星','低空经济'],
         '有色':['有色','铜','铝','稀土'],'消费':['消费','食品','白酒','家电'],'房地产':['房地产','地产'],
         '能源':['石油','煤炭','石化','油价'],'金融':['银行','保险'],'交通':['交通运输','航运','航空'],'配置体系':['配置','定投','红利','低波']}

def infer_topics(column,text):
    topics=[name for name,terms in ALIASES.items() if any(t.lower() in text.lower() for t in terms)]
    if not topics:topics=['指数与量能'] if column in {'盘中实操','风口收评','每日必看'} else []
    terms=[]
    for topic in topics:
        for term in ALIASES[topic]:
            if term.lower() in text.lower():terms.append(term)
    if not terms and text:
        # Extract the supplied subject instead of silently substituting a fixed theme.
        match=re.search(r'(?:关于|点评|分析)([^，。；\n]{2,20}?)(?:的|，|。|；|$)',text)
        if match:terms=[match.group(1).strip()]
    # Empty intent keeps news unfiltered; market leaders are added after collection.
    return topics[:3],list(dict.fromkeys(terms))[:5]

SCENES={'平稳':['盈利验证','放量观察','消息不明'], '缩量分化':['缩量轮动'],
        '破位':['破位谨慎'], '反弹':['下轨候选','判断修正','预期兑现'], '高位拥挤':['估值拥挤','上轨做T'], '其他':[]}

def voice_baseline(column):
    b=load('language_baseline.json')['columns'].get(column)
    if not b:return {'column':column,'note':'无本人同栏目统计，风口收评参考每日必看的表达，不冒称付费样本已蒸馏'}
    n=b['articles']
    return {'column':column,'sample_count':n,'median_body_chars':b['body_chars']['median'],
            'median_sentence_chars':b['sentence_chars']['median'],
            'numbered_articles':b['numbered_body_articles'],'numbered_rate':round(b['numbered_body_articles']/n,3),
            'question_title_rate':round(b['question_title_articles']/n,3),
            'first_person_rate':round(b['first_person_articles']/n,3),
            'note':'描述性参照，不是硬配额；本人当期写法与栏目调整优先，不为命中统计编经历或凑句子'}

def context(column,text,cutoff=None,scene='平稳'):
    topics,terms=infer_topics(column,text);scene_tags=SCENES.get(scene,[]);rows={r['article_id']:r for r in load('corpus_index.json')};meta=load('article_metadata_v2.json')
    verified_dates={m['article_id']:bool(m.get('dates',{}).get('verified_publication_timestamp')) for m in meta}
    # Original publisher dates override inferred labels; exclude same-day/unknown history conservatively.
    eligible={m['article_id'] for m in meta if not cutoff or
              (m.get('dates',{}).get('candidate_publication_date') and
               m['dates']['candidate_publication_date']<cutoff.date().isoformat())}
    selected=[]
    for topic in topics:
        found=[]
        for m in meta:
            if not m['core_voice'] or m['article_id'] not in eligible or (topic not in m['topics'] and not set(scene_tags).intersection(m.get('scenes',[]))):continue
            score=4+(4 if set(scene_tags).intersection(m.get('scenes',[])) else 0)+(3 if m['column']==column else 0)+sum(2 for term in terms if term in m['title'])
            found.append((score,-m['source_index'],m))
        found.sort(key=lambda x:(x[0],x[1]),reverse=True)
        for _,__,m in found[:2]:
            r=rows[m['article_id']]
            selected.append({'article_id':r['article_id'],'title':r['title'],'column':m['column'],'date_raw':r['publish_time'],
                             'source_url':r['url'],'text':r['editorial_text'][:2600],
                             'date_verified':verified_dates.get(r['article_id'],False),'use':'历史推理与声音；数字、事件和工具信号不可当期沿用'})
    if not selected:
        voice_column=column if column in {'每日必看','盘中实操','本周来信','直播精华'} else '每日必看'
        fallback=sorted([m for m in meta if m['core_voice'] and m['article_id'] in eligible and m['column']==voice_column],key=lambda m:m['source_index'])[:3]
        for m in fallback:
            r=rows[m['article_id']]
            selected.append({'article_id':r['article_id'],'title':r['title'],'column':m['column'],'date_raw':r['publish_time'],
                             'source_url':r['url'],'text':r['editorial_text'][:2600],'date_verified':verified_dates.get(r['article_id'],False),
                             'use':'同栏目表达参考，主题不同，不能用作当前主题的事实或观点'})
    selected=list({e['article_id']:e for e in selected}.values())[:6]
    voice_column=column if column in {'每日必看','盘中实操','本周来信','直播精华'} else '每日必看'
    voice_meta=sorted([m for m in meta if m['core_voice'] and m['article_id'] in eligible and m['column']==voice_column],key=lambda m:m['source_index'])[:3]
    voice_examples=[{'article_id':m['article_id'],'column':m['column'],'title':rows[m['article_id']]['title'],
                     'text':rows[m['article_id']]['editorial_text'][:2600],'use':'只用于声音参考，不沿用历史事实'} for m in voice_meta]
    pairs=[c for c in load('contrast_cases.json') if (c['topic'] in topics or c['scene'] in scene_tags) and c['support']['article_id'] in eligible and c['contrast']['article_id'] in eligible]
    rule_ids={'R01','R02','R04','R09','R12','R17','R18'}
    for c in pairs:rule_ids.update(c['rules'])
    if column=='风口收评':rule_ids.update(['R14','R15','R19'])
    if column=='盘中实操':rule_ids.update(['R07','R08'])
    rules=[{**r,'evidence':[e for e in r['evidence'] if e['article_id'] in eligible]} for r in load('framework_rules.json') if r['rule_id'] in rule_ids]
    ledger=[e for e in load('view_ledger.json')['entries'] if e['topic'] in topics and e['source']['article_id'] in eligible]
    import learning
    distillation=learning.for_generation(column,topics,rule_ids,cutoff,[c['case_id'] for c in pairs])
    inactive=set(distillation['inactive_ids'])
    rule_ids.update(rid for c in distillation['cards'] for rid in c.get('rule_ids',[]) if rid not in inactive)
    current={c['id']:c for c in distillation['cards']}
    rules=[]
    for r in load('framework_rules.json'):
        if r['rule_id'] not in rule_ids or r['rule_id'] in inactive:continue
        item={**r,'evidence':[e for e in r['evidence'] if e['article_id'] in eligible]}
        c=current.get(r['rule_id'])
        if c and c.get('author_adjusted'):item.update(reasoning=c['logic'],boundary=c['boundary'],trigger=c['summary'],basis='author_adjustment')
        rules.append(item)
    pairs=sorted([c for c in pairs if c['case_id'] not in inactive and not current.get(c['case_id'],{}).get('author_adjusted')],key=lambda c:(c['scene'] in scene_tags,c['topic'] in topics),reverse=True)[:4]
    ledger=[e for e in ledger if 'V-'+e['entry_id'] not in inactive and not current.get('V-'+e['entry_id'],{}).get('author_adjusted')]
    return {'scene':scene,'scene_tags':scene_tags,'voice_baseline':voice_baseline(column),'voice_examples':voice_examples,'voice_reference_column':voice_column,'topics':topics,'terms':terms,'examples':selected,'contrast_pairs':pairs,'rules':rules,'historical_views':ledger,'distillation':distillation}
