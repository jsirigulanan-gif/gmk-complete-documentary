from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine, ResolverMode

FIXED='2026-09-27T06:20:00Z'
e=StateEngine(ROOT,clock=lambda:FIXED)
source={
  'source_type':'WEB_PAGE','title':'Official notice','authority_class':'OFFICIAL',
  'independence':{'group_id':'SRCGRP_SMOKE','relationship':'ORIGINAL'},
  'availability':{'state':'AVAILABLE'},'language':'en','accessed_at':FIXED,
}
t=e.begin(); src=t.create_object('SOURCE',source); t.commit()
t=e.begin(); ev=t.create_object('EVIDENCE',{
  'source_ref':src,'locator':{'type':'FULL_SOURCE'},'evidence_kind':'DOCUMENT_EXCERPT','content_summary':'Observed fact.'
}); t.commit()
t=e.begin(); cl=t.create_object('CLAIM',{
  'claim_text':'Observed fact occurred.','claim_type':'FACTUAL_ASSERTION','verification_state':'SOURCE_VERIFIED',
  'evidence_links':[{'evidence_ref':ev,'relation':'SUPPORTS','scope':['EVENT'],'strength':'DIRECT'}],
  'certainty':{'level':'HIGH','basis':['PRIMARY_EVIDENCE']},
  'production_use':{'narration_allowed':True,'language_mode':'DIRECT'}
}); t.commit()
t=e.begin(); src2=t.create_version(src['id'],base_version=1,patch={'title':'Official notice corrected'}); t.commit()
assert e.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)['status']=='CURRENT'
t=e.begin(); result=t.promote_active_version(src['id'],src2['version']); t.commit()
assert e.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)['status']=='STALE'
assert e.resolver().resolve(cl['id'],mode=ResolverMode.EXACT,version=1)['status']=='STALE'
assert result['dependency_impact_report']
print('PASS: dependency projection, ACTIVE-root impact, transitive stale propagation, exact no-retarget, and impact artifact smoke passed.')
