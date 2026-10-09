"""Mechanical evidence/cutoff/number/voice checks. Not a semantic fact checker."""
import argparse,datetime as dt,json,re
from pathlib import Path
from difflib import SequenceMatcher
from providers import PRIVATE
ROOT=PRIVATE
NUMBER=re.compile(r'(?<![0-9A-Za-z.])[-+]?\d+(?:\.\d+)?\s*(?:万亿元|亿元|万美元|亿美元|美元|万亿|亿|万|%|％|倍|基点|bp|点)?')

def numbers(text):
    # Ignore list ordinals, not economic dates or values.
    text=re.sub(r'^\s*(?:🔺)?\d+[、.]\s*','',text,flags=re.M)
    return {re.sub(r'\s+','',m.group()).replace('％','%').lstrip('+') for m in NUMBER.finditer(text)}

def timestamp(s):
    value=dt.datetime.fromisoformat(s.replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('timezone required')
    return value

def shape(body):
    headings=re.findall(r'^#{1,3}\s+(.+)$',body,re.M)
    return [re.sub(r'\d+','N',x).strip() for x in headings]

def review(pack,draft,recent=None):
    errors=[];warnings=[]
    if not isinstance(draft,dict) or not isinstance(draft.get('body'),str) or not isinstance(draft.get('title'),str) or not isinstance(draft.get('claims'),list):
        return {'mechanical_pass':False,'errors':[{'code':'draft_shape','message':'稿件标题、正文或句子清单格式错误'}],'warnings':[]}
    for c in draft['claims']:
        if not isinstance(c,dict) or not isinstance(c.get('sentence',''),str) or any(not isinstance(c.get(k,[]),list) or any(not isinstance(x,str) for x in c.get(k,[])) for k in ['fact_ids','rule_ids','knowledge_ids']) or not isinstance(c.get('support_quotes',{}),dict):
            return {'mechanical_pass':False,'errors':[{'code':'claim_shape','message':'句子证据清单格式错误'}],'warnings':[]}
    if not isinstance(draft.get('coverage',{}),dict) or any(not isinstance(v,list) or any(not isinstance(x,str) for x in v) for v in draft.get('coverage',{}).values()):
        return {'mechanical_pass':False,'errors':[{'code':'coverage_shape','message':'覆盖项应为正文句子列表'}],'warnings':[]}
    def error(code,msg):errors.append({'code':code,'message':msg})
    def warning(code,msg):warnings.append({'code':code,'message':msg})
    try:cutoff=timestamp(pack['cutoff'])
    except (KeyError,ValueError,TypeError):return {'mechanical_pass':False,'errors':[{'code':'cutoff','message':'缺少带时区的截点'}],'warnings':[]}
    facts=pack.get('facts',[]);fact_ids=[f.get('id') for f in facts]
    if len(fact_ids)!=len(set(fact_ids)):error('duplicate_fact_id','事实ID重复')
    source={f.get('id'):f for f in facts};usable={}
    mode=pack.get('mode','production')
    for f in facts:
        try:
            available=timestamp(f['available_at']); observed=timestamp(f.get('observed_at',f['available_at']))
        except (KeyError,ValueError,TypeError):error('fact_timestamp',str(f.get('id'))+'缺少带时区的时间');continue
        if available>cutoff or observed>cutoff:
            error('future_fact',str(f['id'])+'超过稿件截点');continue
        if f.get('status')=='simulation' and mode!='simulation':error('simulation_as_live',f['id']+'模拟事实不可用于真实发布');continue
        if f.get('status') not in {'verified','simulation','author_confirmed'}:error('unverified_fact',f['id']+'未核验');continue
        if not f.get('text') or not f.get('source'):error('fact_source',f['id']+'缺正文或来源');continue
        usable[f['id']]=f
    body=draft.get('body','');claims=draft.get('claims',[])
    if not body.strip() or not draft.get('title'):error('empty_draft','缺标题或正文')
    if not claims:error('no_claim_mapping','未提供重要句子的事实/判断对应')
    rules={x['rule_id'] for x in json.loads((ROOT/'framework_rules.json').read_text())}
    selected=set(pack.get('rule_ids',[]));knowledge_ids=set(pack.get('knowledge_ids',[]))
    if selected-rules:error('unknown_rule','输入有未知规则ID')
    history=pack.get('history_records',[]);memory_ids={str(x.get('id')) for x in history}
    reviewed_numbers=set()
    valid_kinds={'fact','judgment','author_memory','technical','tool','operation'}
    for c in claims:
        sent=c.get('sentence','');cid=c.get('id','?');kind=c.get('kind')
        if not sent or sent not in body:error('sentence_not_found',str(cid)+'对应句不在正文');continue
        if kind not in valid_kinds:error('unknown_claim_kind',str(cid)+'类型无效')
        ids=c.get('fact_ids',[]);unknown=set(ids)-set(usable)
        if unknown:error('unsupported_source',str(cid)+'引用不可用事实 '+','.join(map(str,unknown)))
        if kind in {'fact','technical','tool','operation'} and not ids:error('missing_source',str(cid)+'缺当前事实来源')
        if kind=='judgment':
            if not c.get('reasoning'):error('missing_reasoning',str(cid)+'判断缺理由')
            if set(c.get('knowledge_ids',[]))-knowledge_ids:error('unselected_knowledge',str(cid)+'使用未提供或停用的知识卡')
            if not c.get('rule_ids') and not c.get('knowledge_ids'):warning('no_rule',str(cid)+'新判断未映射历史规则，需本人审阅')
            if not ids:error('judgment_without_fact',str(cid)+'判断缺当前证据')
            if not c.get('horizon'):error('missing_horizon',str(cid)+'判断缺期限')
            if not c.get('invalidation'):warning('missing_boundary',str(cid)+'未写复核/失效条件')
            if c.get('proposed_by') not in {'model','author_confirmed'}:error('judgment_authorship',str(cid)+'未区分模型新增与本人确认')
        if c.get('proposed_by')=='author_confirmed':
            origins=[usable[fid] for fid in ids if fid in usable and usable[fid].get('status')=='author_confirmed' and usable[fid].get('kind')==('author_judgment' if kind=='judgment' else 'tool')]
            if not origins or not any(f['text'] in sent for f in origins):
                error('false_author_confirmation',str(cid)+'没有对应的本人当期确认原话或真实工具记录，不可标为本人确认')
        if set(c.get('rule_ids',[]))-selected:error('unselected_rule',str(cid)+'使用未检索的规则')
        for fid,quote in c.get('support_quotes',{}).items():
            if fid not in usable or not isinstance(quote,str) or not quote or quote not in usable[fid]['text']:error('quote_mismatch',str(cid)+'证据片段不属于引用事实')
        if kind in {'fact','technical','tool'} and not c.get('support_quotes'):error('missing_quote',str(cid)+'缺可回溯的当前事实片段')
        available_text='\n'.join(usable[fid]['text'] for fid in ids if fid in usable)
        if kind=='author_memory':
            refs={str(x) for x in c.get('history_ids',[])}
            if not refs or not refs<=memory_ids:error('invented_memory',str(cid)+'没有真实历史稿/本人记录')
            available_text+='\n'+'\n'.join(x.get('text','') for x in history if str(x.get('id')) in refs)
        missing=numbers(sent)-numbers(available_text)
        if missing:error('unsupported_number',str(cid)+'数字/单位不在相应材料 '+','.join(sorted(missing)))
        else:reviewed_numbers|=numbers(sent)
        if kind=='tool' and not any(usable[fid].get('kind')=='tool' for fid in ids if fid in usable):error('invented_tool',str(cid)+'没有实际工具输出')
        if kind=='technical' and not any(usable[fid].get('kind') in {'technical','tool'} for fid in ids if fid in usable):error('missing_technical',str(cid)+'技术判断没有行情计算或真实工具材料')
        if kind=='operation' and not any(usable[fid].get('kind')=='operation' for fid in ids if fid in usable):error('unconfirmed_operation',str(cid)+'运营入口未当期确认')
    represented={fid for c in claims if c.get('kind')=='judgment' and c.get('proposed_by')=='author_confirmed' for fid in c.get('fact_ids',[])}
    if set(pack.get('required_author_ids',[]))-represented:error('author_view_omitted','本人当期观点被遗漏或没有标记为本人确认')
    for group in pack.get('required_author_groups',[]):
        if not represented.intersection(group):error('shared_view_omitted','有相关共享观点但正文未体现任何本人确认判断')
    for c in claims:
        if c.get('kind') in {'fact','technical','tool'} and any(usable.get(fid,{}).get('kind')=='author_judgment' for fid in c.get('fact_ids',[])):
            error('opinion_as_fact','本人判断不能作为已核验客观事实或工具输出')
    uncovered=numbers(body)-reviewed_numbers
    if uncovered:error('unmapped_number','正文数字缺句子映射 '+','.join(sorted(uncovered)))
    # A tool name can be discussed without claiming a signal exists.
    if re.search(r'(趋势顶底|暗盘资金).{0,15}(已|出现|流入|流出|发出)',body) and not any(c.get('kind')=='tool' for c in claims):error('tool_claim_unmapped','专有工具结果缺实际输出映射')
    if re.search(r'(昨天|上周|此前).{0,16}(我|小鹏哥).{0,12}(提示|说过|买|卖|加仓)|我.{0,8}(昨天|上周).{0,8}(提示|买|卖|加仓)',body) and not any(c.get('kind')=='author_memory' for c in claims):error('history_unmapped','本人历史行为未对应历史记录')
    for h in history:
        if h.get('verified_timestamp'):
            try:
                if timestamp(h['available_at'])>cutoff:error('future_history','历史记录晚于截点')
            except (KeyError,ValueError):error('history_timestamp','历史记录时间无效')
        elif mode=='production':warning('archive_date_uncertain','显示日期未核验的历史记录仅用于声音；不可据此声称昨天已提示')
    if pack.get('column')=='风口收评':
        required={'indices','turnover','gainers','losers','news','next_conditions','flows'}
        required-=set(pack.get('coverage_exemptions',{}))
        for facet,reason in pack.get('coverage_exemptions',{}).items():warning('coverage_gap',facet+'：'+reason)
        coverage=draft.get('coverage',{})
        for facet in required:
            sentences=coverage.get(facet,[])
            if not sentences or any(s not in body for s in sentences):error('closing_coverage','收评缺有效覆盖映射 '+facet)
    for token in ['综上所述','总而言之','展望未来','机遇与挑战并存','值得注意的是','赋能','格局重塑','把握投资机遇']:
        if token in body:warning('institutional_phrase','复核机构化表达：'+token)
    titles=shape(body)
    if len(titles)==3 and any(re.search('背景|影响|展望|大盘|板块|明日',h) for h in titles):warning('three_part_outline','检查是否固定三段，不能仅换标题')
    for i,prev in enumerate(recent or []):
        previous=prev.get('body','')
        if titles and len(titles)>=2 and titles==shape(previous):warning('repeated_outline','与近期稿'+str(i+1)+'章节相同')
        opening=re.sub(r'\d+(?:\.\d+)?','N',body.split('\n')[0])
        old=re.sub(r'\d+(?:\.\d+)?','N',previous.split('\n')[0])
        if len(opening)>12 and SequenceMatcher(None,opening,old).ratio()>.82:warning('repeated_opening','与近期稿'+str(i+1)+'开头高度相似')
    if pack.get('require_decision_trace'):
        trace=draft.get('decision_trace',[])
        if not isinstance(trace,list) or not trace:error('missing_decision_trace','缺少问题、证据和取舍的简短后台记录')
        else:
            for step in trace:
                if not isinstance(step,dict) or not step.get('question') or not step.get('choice') or not step.get('limit'):
                    error('decision_trace_shape','决策记录缺问题、取舍或边界');continue
                if set(step.get('fact_ids',[]))-set(usable):error('decision_trace_fact','决策记录引用不可用事实')
                if set(step.get('knowledge_ids',[]))-knowledge_ids:error('decision_trace_knowledge','决策记录引用未提供或停用知识')
    if pack.get('require_new_judgments'):
        new=draft.get('new_judgments')
        if not isinstance(new,list):error('missing_new_judgments','缺少模型新增判断清单（无新增时用空数组）')
        else:
            model_ids={c.get('id') for c in claims if c.get('kind')=='judgment' and c.get('proposed_by')=='model'}
            listed={x.get('claim_id') for x in new if isinstance(x,dict)}
            if listed!=model_ids:error('new_judgment_mapping','新增判断清单须对应全部模型判断，不能包含本人原话或未知句子')
            if any(not isinstance(x,dict) or not x.get('judgment') or not x.get('reason') or x.get('confirmation')!='pending' for x in new):
                error('new_judgment_shape','新增判断需写明取舍、理由并保持待本人确认')
    baseline=json.loads((ROOT/'language_baseline.json').read_text())['columns'].get(pack.get('column'))
    if baseline and not isinstance(pack.get('target_length'),(int,float)) and len(body)>baseline['body_chars']['p90']*1.7:warning('length_outlier','明显长于本栏目，复核是否塞入无关材料')
    if baseline:
        n=baseline['articles'];numbered=baseline['numbered_body_articles']
        if numbered/n>=.9 and not re.search(r'(?:^|\n)\s*(?:🔺|[①②③④⑤⑥⑦⑧⑨⑩]|\d+[、.．）)])',body):
            warning('numbering_deviation',f'本栏目历史{numbered}/{n}篇含编号，本稿没有；请结合内容复核结构')
        if baseline['question_title_articles']/n>=.7 and not re.search(r'[?？]',draft.get('title','')):
            warning('title_deviation','本栏目多数历史标题采用问句，可复核标题是否更贴近本人表达')
    return {'mechanical_pass':not errors,'mode':mode,'errors':errors,'warnings':warnings,
            'requires_human_review':['Cause and effect / logical entailment','Author voice and usefulness','Judgment and action appropriateness'],
            'meaning':'Pass confirms mechanical mappings only; it does not certify truth, style match, or publication readiness.'}

def main():
    p=argparse.ArgumentParser();p.add_argument('--pack',type=Path,required=True);p.add_argument('--draft',type=Path,required=True);p.add_argument('--recent',type=Path);p.add_argument('--output',type=Path);a=p.parse_args()
    result=review(json.loads(a.pack.read_text()),json.loads(a.draft.read_text()),json.loads(a.recent.read_text()) if a.recent else None)
    s=json.dumps(result,ensure_ascii=False,indent=2)
    if a.output:a.output.write_text(s)
    else:print(s)
    raise SystemExit(0 if result['mechanical_pass'] else 1)

if __name__=='__main__':main()
