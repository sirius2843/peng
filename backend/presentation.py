"""View-only organization; preserve every original card and calibration identifier."""
import json
from providers import ROOT

def config():return json.loads((ROOT/'knowledge/profile_presentation.json').read_text())
def decorate(cards):
 layout=config();groups={g['id']:g for g in layout['groups']};membership={cid:g['id'] for g in groups.values() for cid in g['cards']}
 for parent,children in layout['merged'].items():
  for child in children:membership[child]=membership[parent]
 result=[]
 for c in cards:
  entry={**c}
  if c['section']=='framework':
   group=membership.get(c['id'],c.get('group'))
   if group not in groups:group=layout['legacy_groups'].get(group,'research')
   entry['display_group']=group
   if group=='asset_research' and c.get('topics'):title=' / '.join(c['topics'])
   else:title=layout['titles'].get(c['id'],c['title']) if not c.get('author_adjusted') else c['title']
   entry['display_title']=title
   entry['display_usage']=c.get('usage') or layout['usage'].get(c['id']) or '、'.join(c.get('conditions',[])) or '研究与写作涉及这项方法时'
   entry['research_path']=[] if c.get('author_adjusted') else layout['paths'].get(c['id'],[])
  else:
   entry['display_usage']=c.get('usage') or '、'.join(c.get('conditions',[])) or ('回看该日期的判断与后续变化' if c['section']=='views' else '使用这个场景的取舍时' if c['section']=='scenarios' else '撰写'+('、'.join(c.get('columns',[])) or c['title'])+'时')
  entry['supplement_summary']=c['summary'] if c.get('author_adjusted') else layout.get('supplement_summaries',{}).get(c['id'],c['summary'])
  result.append(entry)
 return result,layout

def display_cards(cards,layout):
 by_id={c['id']:c for c in cards};hidden=set()
 output=[]
 # Do not hide an independently edited/stopped child: its controls remain inside the combined card.
 for parent,children in layout['merged'].items():
  if parent in by_id:hidden.update(cid for cid in children if cid in by_id)
 for c in cards:
  if c['id'] in hidden:continue
  output.append({**c,'related_cards':[by_id[cid] for cid in layout['merged'].get(c['id'],[]) if cid in by_id]})
 return output
