import datetime as dt
import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import knowledge,providers,writer
from review import review

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.fact={'id':'N1','kind':'news','text':'政策仍处于征求意见阶段。','source':'https://example.org/notice','observed_at':'2026-10-07T10:00:00+08:00','available_at':'2026-10-07T10:00:00+08:00','status':'verified'}
        self.draft={'title':'先看落地','body':'政策仍处于征求意见阶段。','claims':[{'id':'C1','sentence':'政策仍处于征求意见阶段。','kind':'fact','fact_ids':['N1'],'support_quotes':{'N1':'政策仍处于征求意见阶段。'},'rule_ids':[]}],'coverage':{},'new_judgments':[],'review_notes':[],'decision_trace':[{'question':'政策到了哪一步','fact_ids':['N1'],'knowledge_ids':[],'choice':'只描述征求意见状态','limit':'尚未实施，不推断已兑现利润'}]}
        self.pack={'cutoff':'2026-10-08T08:45:00+08:00','column':'每日必看','facts':[self.fact],'rule_ids':[]}
    def test_future_publication_rejected(self):
        self.fact['available_at']='2026-10-08T12:00:00+08:00'
        result=review(self.pack,self.draft)
        self.assertFalse(result['mechanical_pass'])
        self.assertIn('future_fact',[e['code'] for e in result['errors']])
    def test_unsupported_fact_quote_rejected(self):
        self.draft['claims'][0]['support_quotes']['N1']='政策已经正式实施。'
        self.assertFalse(review(self.pack,self.draft)['mechanical_pass'])
    def test_unbacked_personal_memory_rejected(self):
        self.draft['body']='昨天我已提示可以买。'
        self.draft['claims'][0].update(sentence=self.draft['body'],kind='author_memory',history_ids=['fake'])
        self.assertIn('invented_memory',[e['code'] for e in review(self.pack,self.draft)['errors']])
    def test_archive_cutoff_applies_to_all_retrieval_layers(self):
        cutoff=dt.datetime(2026,10,8,8,45,tzinfo=providers.TZ)
        ctx=knowledge.context('每日必看','科技',cutoff)
        dates={m['article_id']:m['dates']['candidate_publication_date'] for m in knowledge.load('article_metadata_v2.json')}
        ids=[e['article_id'] for e in ctx['examples']]+[e['source']['article_id'] for e in ctx['historical_views']]
        ids += [p[k]['article_id'] for p in ctx['contrast_pairs'] for k in ['support','contrast']]
        ids += [e['article_id'] for r in ctx['rules'] for e in r['evidence']]
        self.assertTrue(ids)
        self.assertTrue(all(dates[i] and dates[i]<'2026-10-08' for i in ids))
    def test_deepseek_contract_and_context_assembly(self):
        cutoff=dt.datetime(2026,10,8,8,45,tzinfo=providers.TZ)
        ctx=knowledge.context('每日必看','科技',cutoff)
        n={'id':'N1','title':'政策仍处于征求意见阶段。','excerpt':'','url':'https://example.org/notice','published_at':'2026-10-07T10:00:00+08:00'}
        sources={'cutoff':cutoff.isoformat(),'market':None,'news':[n],'research':[],'gaps':[]}
        requests=[]
        def fake_request(url,headers,payload,timeout):
            requests.append(payload)
            self.assertEqual(url,'https://api.deepseek.com/chat/completions')
            self.assertEqual(headers['Authorization'],'Bearer test-local-credential')
            user=json.loads(payload['messages'][1]['content'])
            self.assertTrue(user['historical_context']['rules'])
            self.assertTrue(user['historical_context']['examples'])
            self.assertEqual(user['facts'][0]['id'],'N1')
            self.assertIn('盘中实操',payload['messages'][0]['content'])
            return json.dumps({'choices':[{'message':{'content':json.dumps(self.draft,ensure_ascii=False)}}],'usage':{'total_tokens':10}})
        with patch.object(writer,'settings',return_value={'api_key':'test-local-credential','model':'deepseek-flash'}),patch.object(writer,'request',side_effect=fake_request):
            out=writer.generate('每日必看','科技',ctx,sources,[])
        self.assertTrue(out['review']['mechanical_pass']);self.assertEqual(len(requests),2);self.assertEqual(out['voice_review']['status'],'applied')
    def test_model_invalid_json_is_safe_error(self):
        with patch.object(writer,'settings',return_value={'api_key':'test-local-credential','model':'deepseek-flash'}),patch.object(writer,'request',return_value='remote-invalid-response'):
            with self.assertRaisesRegex(RuntimeError,'未返回可用稿件'):writer.call([])

if __name__=='__main__':unittest.main()
