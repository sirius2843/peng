import copy,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
import learning,presentation
class PresentationTests(unittest.TestCase):
 def test_each_framework_record_has_one_semantic_group(self):
  catalog=learning.catalog();rows=catalog['display_cards'];groups={g['id']:g for g in catalog['presentation']['groups']}
  expected={'principles':3,'research':4,'asset_research':7,'position':2,'toolkit':5,'market_reading':5,'production':5}
  for group,count in expected.items():
   self.assertEqual(len([c for c in rows if c['section']=='framework' and c['display_group']==group]),count)
  self.assertEqual({c['id'] for c in rows if c.get('display_group')=='production'},{'R17','R19','R20','I01','I02'})
 def test_duplicate_cards_are_nested_with_original_controls_and_evidence(self):
  catalog=learning.catalog();original={c['id']:c for c in catalog['cards']};display={c['id']:c for c in catalog['display_cards']}
  self.assertNotIn('T01',display);self.assertNotIn('T02',display)
  self.assertEqual(display['R07']['related_cards'][0]['id'],'T01')
  self.assertEqual(display['R11']['related_cards'][0]['evidence'],original['T02']['evidence'])
  self.assertIn('T01',original);self.assertIn('T02',original)
 def test_views_and_asset_methods_stay_separate(self):
  catalog=learning.catalog();display=catalog['display_cards']
  methods=[c for c in display if c.get('display_group')=='asset_research']
  self.assertEqual({c['id'] for c in methods},{'A01','A02','A03','A04','A05','A06','A07'})
  self.assertTrue(all(c['research_path'] and c['display_title']==' / '.join(c['topics']) for c in methods))
  self.assertEqual(len([c for c in display if c['section']=='views']),len([c for c in catalog['cards'] if c['section']=='views']))
 def test_presentation_does_not_rewrite_judgments_or_calibration(self):
  originals=learning.cards();before=copy.deepcopy(originals);decorated,layout=presentation.decorate(originals)
  presentation.display_cards(decorated,layout)
  self.assertEqual(originals,before)
  for original,new in zip(before,decorated):
   for key in ['id','summary','logic','evidence','revision','status','group']:
    self.assertEqual(original.get(key),new.get(key))
 def test_author_usage_and_title_override_editorial_display(self):
  card=next(c for c in learning.cards() if c['id']=='R03')
  card.update(author_adjusted=True,title='我自己的研究步骤',usage='盈利预期变化时',conditions=[])
  decorated,_=presentation.decorate([card])
  self.assertEqual(decorated[0]['display_title'],'我自己的研究步骤')
  self.assertEqual(decorated[0]['display_usage'],'盈利预期变化时')
  self.assertEqual(decorated[0]['research_path'],[])
if __name__=='__main__':unittest.main()
