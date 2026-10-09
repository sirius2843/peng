import copy,datetime as dt,json,sys,tempfile,unittest,concurrent.futures
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import viewpoints,providers,preferences
from review import review
class SharedViewsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.patch=patch.object(viewpoints,'PRIVATE',Path(self.tmp.name));self.patch.start()
  self.time=dt.datetime(2026,10,9,16,tzinfo=providers.TZ);self.clock=patch.object(viewpoints,'now',return_value=self.time);self.clock.start()
 def tearDown(self):self.clock.stop();self.patch.stop();self.tmp.cleanup()
 def data(self):
  v=viewpoints.empty();v.update(expected_revision=0,confirmed=True,effective_at='2026-10-09T08:00',scene='其他',scene_other='政策引发分化')
  v['market']['view']='缩量先等确认';v['industries']=[{'name':'通信','view':'短期先看空','horizon':'short','boll':'通信指数日线跌破下轨','dragon':'','bottom':'','signal_time':'2026-10-08T15:00'}]
  return v
 def test_two_clients_same_saved_version_and_stale_write_rejected(self):
  a=self.data();b=copy.deepcopy(a);saved=viewpoints.save(a)
  self.assertEqual(viewpoints.latest(),saved)
  with self.assertRaisesRegex(ValueError,'另一页面'):viewpoints.save(b)
  self.assertEqual(viewpoints.latest()['revision'],1)
 def test_simultaneous_saves_have_one_winner(self):
  def attempt():
   try:return viewpoints.save(self.data())['revision']
   except ValueError:return 'conflict'
  with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(lambda _:attempt(),range(2)))
  self.assertEqual(sorted(map(str,result)),['1','conflict'])
 def test_versions_survive_reads_and_old_snapshots_remain_unchanged(self):
  first=viewpoints.save(self.data());later=copy.deepcopy(first);later.update(expected_revision=1);later['market']['view']='反弹后等待量能';second=viewpoints.save(later)
  self.assertEqual(first['market']['view'],'缩量先等确认');self.assertEqual(second['revision'],2)
  self.assertEqual([x['revision'] for x in viewpoints.history()],[2,1])
 def test_signal_date_and_confirmation_validation(self):
  data=self.data();data['confirmed']=False
  with self.assertRaises(ValueError):viewpoints.save(data)
  data['confirmed']=True;data['industries'][0]['signal_time']='2026-10-09T09:00'
  with self.assertRaisesRegex(ValueError,'晚于观点'):viewpoints.save(data)
 def test_snapshot_facts_preserve_asset_and_horizon(self):
  saved=viewpoints.save(self.data());facts,notes=viewpoints.facts(saved,self.time,'风口收评')
  self.assertEqual(len(facts),3);self.assertTrue(all(f['status']=='author_confirmed' for f in facts))
  signal=next(f for f in facts if f['kind']=='tool');self.assertEqual(signal['asset'],'通信');self.assertIn('BOLL',signal['text']);self.assertIn('2026-10-08',signal['observed_at'])
 def test_early_cutoff_never_uses_later_view_or_signal(self):
  data=self.data();data['effective_at']='2026-10-09T09:00';saved=viewpoints.save(data)
  facts,notes=viewpoints.facts(saved,self.time.replace(hour=8,minute=45),'每日必看')
  self.assertEqual(facts,[]);self.assertTrue(notes)
 def test_event_column_selects_relevant_industry_and_does_not_force_all(self):
  saved=viewpoints.save(self.data());facts,_=viewpoints.facts(saved,self.time,'行业/事件点评','银行业绩')
  self.assertFalse(any(f['asset']=='通信' for f in facts))
  facts,_=viewpoints.facts(saved,self.time,'行业/事件点评','通信业绩')
  self.assertTrue(any(f['asset']=='通信' for f in facts))
 def test_shared_judgment_cannot_be_ignored_entirely(self):
  r=review({'mode':'production','cutoff':self.time.isoformat(),'facts':[],'required_author_groups':[['SHARED-1']]},{'title':'标题','body':'等待更多证据。','claims':[]})
  self.assertIn('shared_view_omitted',[e['code'] for e in r['errors']])
 def test_operations_are_actual_verbatim_corpus_materials(self):
  corpus={str(r['article_id']):r for r in json.loads((providers.PRIVATE/'corpus_index.json').read_text())}
  self.assertGreaterEqual(len(preferences.DEFAULT_OPERATIONS),12)
  for row in preferences.DEFAULT_OPERATIONS:
   source=row['source'];self.assertIn(source['quote'],corpus[str(source['article_id'])]['text']);self.assertEqual(source['quote'],row['text'])
 def test_original_services_are_available_under_author_policy(self):
  items=preferences.DEFAULT_OPERATIONS
  self.assertTrue(all(not x['requires_confirmation'] and x['current_confirmed'] for x in items))
  with patch.object(preferences,'read',return_value={'operations':items}):
   self.assertEqual(len(preferences.selected([x['id'] for x in items])),12)
 def test_ledger_dates_use_verified_publisher_timestamps(self):
  import learning
  cards=learning.catalog()['cards']
  refs=[e for c in cards if c['section']=='views' for e in c['evidence']]
  self.assertTrue(refs);self.assertTrue(all(e.get('publication_verified') for e in refs))
  latest=next(e for e in refs if e['article_id']==1500084092)
  self.assertEqual(latest['published_at'],'2026-10-08T13:44:44+08:00')
  self.assertEqual(latest['candidate_date'],'2026-10-08')
if __name__=='__main__':unittest.main()
