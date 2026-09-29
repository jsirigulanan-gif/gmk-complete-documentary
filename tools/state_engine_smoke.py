#!/usr/bin/env python3
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine, ResolverMode

engine=StateEngine(ROOT,clock=lambda:'2026-09-27T05:05:00Z')
tx=engine.begin()
ref=tx.create_object('PROJECT',{
  'title':'GMK State Smoke',
  'language':{'narration':'th-TH'},
  'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}},
})
tx.commit()

tx=engine.begin()
v2=tx.create_version(ref['id'],base_version=1,patch={'working_title':'State Engine v2'})
tx.commit()
assert engine.resolver().resolve(ref['id'],mode=ResolverMode.ACTIVE)['version']==1
assert engine.resolver().resolve(ref['id'],mode=ResolverMode.HEAD)['version']==2

tx=engine.begin()
tx.promote_active_version(ref['id'],v2['version'])
tx.commit()
assert engine.resolver().resolve(ref['id'],mode=ResolverMode.ACTIVE)['version']==2
assert len(engine.audit_log())==3
print('PASS: State Engine create/version/HEAD-ACTIVE/promotion/atomic audit smoke passed.')
