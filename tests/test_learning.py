import copy,json,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import server
import learning,knowledge,providers

class LearningTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.directory=Path(self.tmp.name)
  self.patch=patch.object(learning,'DB',self.directory/'studio.sqlite');self.patch.start()
  self.spatch=patch.object(server,'DB',self.directory/'studio.sqlite');self.spatch.start()
  server.CACHE.clear();server.JOBS.clear()
  with server.db():pass
 def tearDown(self):self.spatch.stop();self.patch.stop();self.tmp.cleanup()
 def make_draft(self,sample=False):
  result={'draft':{'title':'测试初稿','body':'产业有长期机会，也要区分交易期限。'},'review':{'mechanical_pass':True},'sample':sample}
  return server.save_record('盘中实操',result,{'snapshot':'冻结的当期资料'},{'topics':['创新药'],'distillation':{'version':learning.version(),'cards':[]}},None)
 def edit(self,record,body):
  with server.db() as con:
   con.execute('BEGIN IMMEDIATE');v=learning.append_version(con,record['id'],'修改稿',body,'author_edit',expected=record['version_id'])
   con.execute('UPDATE drafts SET title=?,body=? WHERE id=?',('修改稿',body,record['id']))
  return {**record,'body':body,'version_id':v['id']}
 def feedback(self,r,scope='column',lesson='短线风险只影响交易仓，长期判断单独核验。'):
  p=learning.prepare_feedback(r['id'])
  return learning.submit_feedback({'record_id':r['id'],'after_version':p['after']['id'],'category':'期限与仓位','lesson':lesson,'reason':'不要把交易破位写成长线证伪。','scope':scope,'author_confirmed':True})
 def test_versions_and_conflicting_edit(self):
  r=self.make_draft();edited=self.edit(r,'交易仓谨慎，长期逻辑单独研究。')
  items=learning.versions(r['id']);self.assertEqual(len(items),2);self.assertEqual(items[0]['body'],r['body'])
  with server.db() as con:
   with self.assertRaises(learning.Conflict):learning.append_version(con,r['id'],'冲突','过期编辑','author_edit',expected=r['version_id'])
  self.assertEqual(learning.versions(r['id'])[-1]['id'],edited['version_id'])
 def test_feedback_preserves_pair_snapshot_and_scoped_retrieval(self):
  r=self.edit(self.make_draft(),'短线先等待，但不据此改变长期逻辑。');f=self.feedback(r)
  self.assertEqual(f['status'],'confirmed')
  export=json.loads((self.directory/'author_feedback.json').read_text());payload=export['feedback'][0]['payload']
  self.assertEqual(payload['before']['body'],'产业有长期机会，也要区分交易期限。');self.assertEqual(payload['after']['body'],r['body'])
  self.assertEqual(payload['source_snapshot']['snapshot'],'冻结的当期资料');self.assertTrue(payload['author_words'])
  self.assertTrue(learning.for_generation('盘中实操',['创新药'],[],None)['feedback_memories'])
  self.assertFalse(learning.for_generation('本周来信',['创新药'],[],None)['feedback_memories'])
  self.assertFalse(learning.for_generation('盘中实操',['黄金'],[],None)['feedback_memories'])
  learning.change_feedback({'id':f['id'],'action':'pause'});self.assertFalse(learning.for_generation('盘中实操',['创新药'],[],None)['feedback_memories'])
 def test_article_only_and_simulation_never_become_learning(self):
  for sample,scope in [(False,'article'),(True,'column')]:
   f=self.feedback(self.edit(self.make_draft(sample),'只修改当前文章的表达。'),scope)
   self.assertEqual(f['status'],'archived')
  self.assertFalse(learning.for_generation('盘中实操',['创新药'],[],None)['feedback_memories'])
 def test_stale_and_duplicate_feedback_rejected(self):
  r=self.edit(self.make_draft(),'先分期限再讲选择。');p=learning.prepare_feedback(r['id']);r=self.edit(r,'再次改稿。')
  with self.assertRaises(learning.Conflict):learning.submit_feedback({'record_id':r['id'],'after_version':p['after']['id'],'category':'声音','lesson':'更直接','scope':'column','author_confirmed':True})
  self.feedback(r)
  with self.assertRaises(ValueError):self.feedback(r)
 def test_author_adjustment_priority_pause_and_rollback(self):
  c=learning.current_card('R01');original=copy.deepcopy(c['evidence'])
  adjusted=learning.save_card({'id':'R01','action':'adjust','expected_revision':0,'title':c['title'],'summary':'先问这笔钱准备拿多久。','logic':'先询问期限，不默认比例。','boundary':'期限不明时不提供比例。'})
  ctx=knowledge.context('盘中实操','配置',providers.now());self.assertEqual(next(r for r in ctx['rules'] if r['rule_id']=='R01')['reasoning'],'先询问期限，不默认比例。')
  learning.save_card({'id':'R01','action':'pause','expected_revision':adjusted['revision']})
  ctx=knowledge.context('盘中实操','配置',providers.now());self.assertNotIn('R01',[r['rule_id'] for r in ctx['rules']])
  self.assertNotIn('R01',[c['id'] for c in ctx['distillation']['cards']])
  paused=learning.current_card('R01');learning.save_card({'id':'R01','action':'restore','event_id':adjusted['revision'],'expected_revision':paused['revision']})
  self.assertEqual(learning.current_card('R01')['evidence'],original);self.assertEqual(len(learning.card_history('R01')),3)
 def test_multiple_feedbacks_do_not_silently_promote_general_rules(self):
  for _ in range(3):self.feedback(self.edit(self.make_draft(),'交易仓和长期底仓分别解释。'))
  self.assertEqual(len(learning.catalog()['feedback']),3)
  self.assertEqual(learning.current_card('R01')['revision'],0)
 def test_regeneration_uses_latest_edited_text_and_knowledge(self):
  r=self.edit(self.make_draft(),'这是本人最新修改，要保留。');self.feedback(r)
  source={'market':None,'news':[{'id':'N1','title':'创新药进展','excerpt':'最新消息','url':'https://example.org/notice','published_at':'2026-10-08T12:00:00+08:00'}],'research':[],'gaps':[],'cutoff':'2026-10-09T12:00:00+08:00'}
  def generate(col,intent,ctx,sources,recent,revision):
   self.assertEqual(revision['previous_body'],r['body']);self.assertTrue(ctx['distillation']['feedback_memories'])
   return {'draft':{'title':'修改结果','body':'保留最新稿后的再次修改。'},'review':{'mechanical_pass':True}}
  server.JOBS['test']={}
  with patch.object(server.providers,'collect',return_value=source),patch.object(server.writer,'generate',side_effect=generate):
   server.job_run('test',{'column':'盘中实操','intent':'创新药','revision_id':r['id'],'operation_ids':[]})
  self.assertEqual(server.JOBS['test']['status'],'done',server.JOBS['test'])
 def test_quote_links_recover_exact_paragraph(self):
  data=learning.evidence('T01');self.assertTrue(data['evidence'])
  for e in data['evidence']:self.assertIn(e['quote'],e['context'][1 if e['block_index'] else 0]['text'])

if __name__=='__main__':unittest.main()
