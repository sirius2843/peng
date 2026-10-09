import copy,datetime as dt,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import author_inputs,knowledge,writer,providers,market_extra
from review import review

class OptimizationTests(unittest.TestCase):
 def setUp(self):
  self.cutoff=dt.datetime(2026,10,9,16,30,tzinfo=providers.TZ)
  self.sources={'cutoff':self.cutoff.isoformat(),'market':None,'news':[],'research':[],'gaps':[]}
  self.pack={'column':'盘中实操','cutoff':self.cutoff.isoformat(),'facts':[],'rule_ids':[],'knowledge_ids':[],'require_new_judgments':True}
  self.draft={'title':'通信先等等？','body':'我现在看空通信。','claims':[{'id':'C1','kind':'judgment','sentence':'我现在看空通信。','proposed_by':'author_confirmed','fact_ids':['AUTHOR-J1'],'reasoning':'本人当期判断','horizon':'short','invalidation':'后续盈利验证变化时复核','support_quotes':{'AUTHOR-J1':'我现在看空通信。'}}],'new_judgments':[]}
 def inputs(self,**kw):return author_inputs.normalize({'author_view':'我现在看空通信。','author_confirmed':True,**kw},self.cutoff)
 def test_author_view_is_not_inferred_from_intent(self):
  self.assertEqual(author_inputs.normalize({'intent':'我看空通信'},self.cutoff),[])
  with self.assertRaises(ValueError):author_inputs.normalize({'author_view':'看空通信'},self.cutoff)
 def test_confirmed_view_is_usable_and_false_confirmation_rejected(self):
  self.pack['facts']=self.inputs()
  self.assertTrue(review(self.pack,self.draft)['mechanical_pass'])
  self.pack['facts'][0].update(kind='news',status='verified')
  self.assertIn('false_author_confirmation',[e['code'] for e in review(self.pack,self.draft)['errors']])
 def test_actual_tool_input_and_future_signal_block(self):
  self.pack['facts']=self.inputs(tool_signals='通信指数日线BOLL跌破下轨。',signal_time='2026-10-09T15:00')
  self.draft['body']+='通信指数日线BOLL跌破下轨。'
  self.draft['claims'].append({'id':'C2','kind':'tool','proposed_by':'author_confirmed','sentence':'通信指数日线BOLL跌破下轨。','fact_ids':['AUTHOR-T1'],'support_quotes':{'AUTHOR-T1':'通信指数日线BOLL跌破下轨。'}})
  self.assertTrue(review(self.pack,self.draft)['mechanical_pass'])
  with self.assertRaises(ValueError):self.inputs(tool_signals='底信号出现',signal_time='2026-10-09T17:00')
 def test_scene_independent_of_topic_and_baseline(self):
  topics,terms=knowledge.infer_topics('每日必看','')
  self.assertEqual(terms,[]);self.assertNotIn('创新药',topics)
  ctx=knowledge.context('每日必看','煤炭',self.cutoff,'破位')
  self.assertIn('C01',[c['case_id'] for c in ctx['contrast_pairs']])
  self.assertEqual(ctx['voice_baseline']['numbered_articles'],142)
 def test_news_empty_intent_keeps_unrelated_major_event(self):
  stamp=int((self.cutoff-dt.timedelta(hours=1)).timestamp())
  data={'props':{'pageProps':{'assembleData':{'top_article':[{'id':1,'ctime':stamp,'title':'银行重大事件','brief':'银行信息'}]}}}}
  raw='<script id="__NEXT_DATA__">'+json.dumps(data)+'</script>'
  with patch.object(providers,'request',return_value=raw):
   self.assertEqual(len(providers.news(self.cutoff,[])),1)
   self.assertEqual(providers.news(self.cutoff,['半导体']),[])
 def test_missing_closing_facets_exempt_only_unavailable(self):
  self.pack.update(column='风口收评',facts=self.inputs(),coverage_exemptions={k:'实际缺口' for k in ['indices','turnover','gainers','losers','news','flows']})
  self.draft['coverage']={'next_conditions':[self.draft['body']]}
  self.assertTrue(review(self.pack,self.draft)['mechanical_pass'])
  del self.pack['coverage_exemptions']['news']
  self.assertFalse(review(self.pack,self.draft)['mechanical_pass'])
 def test_model_new_judgment_must_be_reviewable(self):
  self.pack['facts']=self.inputs();self.draft['claims'][0]['proposed_by']='model'
  self.assertIn('new_judgment_mapping',[e['code'] for e in review(self.pack,self.draft)['errors']])
  self.draft['new_judgments']=[{'claim_id':'C1','judgment':self.draft['body'],'reason':'新取舍','confirmation':'pending'}]
  self.assertTrue(review(self.pack,self.draft)['mechanical_pass'])
 def test_length_and_numbering_warnings_now_active(self):
  self.pack.update(column='每日必看',facts=self.inputs(),target_length='按任务适当精简')
  self.draft['body']+='重复的没有新增事实的表达。'*300
  codes={w['code'] for w in review(self.pack,self.draft)['warnings']}
  self.assertIn('length_outlier',codes);self.assertIn('numbering_deviation',codes)
 def test_truncation_diagnosis_is_explicit(self):
  raw=json.dumps({'choices':[{'finish_reason':'length','message':{'content':'{"title":'}}]})
  with patch.object(writer,'settings',return_value={'model':'deepseek-flash','api_key':'test-key'}),patch.object(writer,'request',return_value=raw):
   with self.assertRaisesRegex(RuntimeError,'截断'):writer.call([])
 def test_voice_rewrite_cannot_break_evidence(self):
  self.sources['author_inputs']=self.inputs()
  ctx=knowledge.context('盘中实操','通信',self.cutoff)
  self.draft['decision_trace']=[{'question':'通信如何看','choice':'本人判断','limit':'不是核验事实','fact_ids':['AUTHOR-J1'],'knowledge_ids':[]}]
  broken=copy.deepcopy(self.draft);broken['body']='通信确定会跌。'
  with patch.object(writer,'call',side_effect=[(self.draft,{}),(broken,{})]):
   out=writer.generate('盘中实操','通信',ctx,self.sources,[])
  self.assertEqual(out['draft']['body'],self.draft['body']);self.assertEqual(out['voice_review']['status'],'rejected')
 def test_partial_market_still_supplies_available_facts(self):
  self.sources['market']={'indices':[{'name':'上证指数','close':3000,'pct':1.0,'date':'2026-10-09'}],'trade_date':'2026-10-09','observed_at':'2026-10-09T15:00:00+08:00','gainers':[],'losers':[]}
  self.assertEqual([x['id'] for x in writer.facts_from_sources(self.sources)],['MKT-INDEX'])
 def test_free_global_future_session_and_proxy_labels(self):
  start=int(dt.datetime(2026,10,7,9,30,tzinfo=__import__('zoneinfo').ZoneInfo('America/New_York')).timestamp())
  raw={'chart':{'result':[{'timestamp':[start,start+86400,start+172800],'indicators':{'quote':[{'close':[100,101,105]}]}}]}}
  with patch.object(market_extra,'request',return_value=json.dumps(raw)):
   row=market_extra.global_quote(market_extra.GLOBAL[0],self.cutoff)
  self.assertIn('101.0点',row['text']);self.assertLessEqual(dt.datetime.fromisoformat(row['available_at']),self.cutoff)
 def test_network_indices_disagreement_excluded(self):
  epoch=int(self.cutoff.replace(hour=15).timestamp())
  with patch.object(market_extra,'historical_index',side_effect=RuntimeError('双来源不一致')):
   rows,gaps=market_extra.fallback_indices(self.cutoff)
  self.assertEqual(rows,[]);self.assertTrue(gaps)

 def test_author_view_must_not_be_silently_omitted(self):
  self.pack.update(facts=self.inputs(),required_author_ids=['AUTHOR-J1'])
  self.draft['claims'][0]['proposed_by']='model'
  codes={e['code'] for e in review(self.pack,self.draft)['errors']}
  self.assertIn('author_view_omitted',codes)
 def test_author_judgment_does_not_become_verified_news(self):
  self.pack['facts']=self.inputs();self.draft['claims'][0]['kind']='fact'
  self.assertIn('opinion_as_fact',[e['code'] for e in review(self.pack,self.draft)['errors']])
 def test_bad_model_schema_can_be_repaired_without_crash(self):
  self.draft['claims']=[{'sentence':'观点','fact_ids':'not-a-list'}]
  self.assertEqual(review(self.pack,self.draft)['errors'][0]['code'],'claim_shape')
 def test_global_futures_are_timed_proxy_not_spot(self):
  epoch=int(self.cutoff.replace(hour=14,minute=0).timestamp())
  raw={'chart':{'result':[{'timestamp':[epoch,epoch+3600,epoch+7200],'indicators':{'quote':[{'close':[80,81,82]}]}}]}}
  with patch.object(market_extra,'request',return_value=json.dumps(raw)):
   row=market_extra.global_quote(market_extra.GLOBAL[-2],self.cutoff)
  self.assertIn('81.0美元',row['text']);self.assertIn('非现货',row['text'])
 def test_backup_prices_are_not_a_money_flow_source(self):
  epoch=int(self.cutoff.replace(hour=15,minute=0).timestamp())
  rows=[{'f14':'通信','f12':'BK1','f3':2,'f62':300000000,'f124':epoch}]
  with patch.object(market_extra,'em',return_value={'total':1,'diff':rows}):
   data=market_extra.sectors(self.cutoff)
   self.assertEqual(data[0]['pct'],2);self.assertNotIn('net_yi',data[0])
   with self.assertRaises(RuntimeError):market_extra.sectors(self.cutoff.replace(hour=14))
 def test_wmcloud_flow_units_dates_and_missing_values(self):
  def row(code,net,pct=.025,date='2026-10-09'):
   return {'industryID':code,'industryName':code,'netMainInflow':net,'chgPct':pct,'tradeDate':date}
  rows=[row('01032101',-300000000),row('01032102',0),row('01032103',None),
        row('01032104',500000000,-.01),row('01032105',100,date='2026-10-08'),
        row('0103210101',100),row('01032101',999),row('01032106','nan')]
  industries,flows=providers.normalize_industry_rows(rows,'2026-10-09')
  self.assertEqual(len(industries),5);self.assertEqual(len(flows),3)
  self.assertEqual(flows[0]['pct'],2.5);self.assertEqual(flows[0]['net_yi'],-3)
  self.assertEqual(flows[1]['net_yi'],0);self.assertEqual(flows[2]['net_yi'],5)
  self.assertEqual(flows[0]['divergence'],'领涨流出');self.assertEqual(flows[2]['divergence'],'领跌流入')
  self.assertTrue(all(f['net_pct'] is None for f in flows))
 def test_wmcloud_flow_materials_do_not_invent_percentages(self):
  _,flows=providers.normalize_industry_rows([{'industryID':'01032101','industryName':'通信','chgPct':.02,'netMainInflow':-200000000}],'2026-10-09')
  facts=writer.facts_from_sources({'market':{'flows':flows}})
  self.assertEqual(len(facts),1);self.assertIn('净流出2.0亿元',facts[0]['text'])
  self.assertNotIn('None%',facts[0]['text']);self.assertNotIn('占比None',facts[0]['text'])
  self.assertIn('通联',facts[0]['source']);self.assertIn('未提供资金占比',facts[0]['text'])
 def test_complete_wmcloud_snapshot_does_not_call_backup(self):
  primary={'indices':[{}, {}, {}],'gainers':[{}],'losers':[{}],'flows':[]}
  with patch.object(market_extra,'sectors',side_effect=AssertionError('不应调用备用资金')):
   out,gaps=market_extra.supplement_market(primary,self.cutoff)
  self.assertEqual(out,primary);self.assertEqual(gaps,[])
 def test_flow_selection_keeps_money_leaders_and_divergences(self):
  rows=[{'code':str(i),'pct':20-i,'net_yi':i,'divergence':None} for i in range(31)]
  rows[10].update(net_yi=1000);rows[11].update(net_yi=-1000,divergence='领涨流出')
  rows[21].update(net_yi=5,divergence='领跌流入')
  result=providers.select_industry_flows(rows);codes=[r['code'] for r in result]
  self.assertTrue({'10','11','21'}<=set(codes));self.assertEqual(len(codes),len(set(codes)))
 def test_historical_index_cross_source_mismatch_rejected(self):
  em={'data':{'klines':['2026-10-07,100,100','2026-10-08,100,101']}}
  peer={'data':{'sh000001':{'day':[['2026-10-07','100','100'],['2026-10-08','100','99']]}}}
  with patch.object(market_extra,'request',side_effect=[json.dumps(em),json.dumps(peer)]):
   with self.assertRaisesRegex(RuntimeError,'交叉验证'):market_extra.historical_index('1.000001','sh000001','上证',self.cutoff)
 def test_voice_samples_really_match_the_requested_column(self):
  ctx=knowledge.context('盘中实操','煤炭',self.cutoff,'破位')
  self.assertTrue(ctx['voice_examples']);self.assertTrue(all(s['column']=='盘中实操' for s in ctx['voice_examples']))

if __name__=='__main__':unittest.main()
