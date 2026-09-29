from pathlib import Path
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state.models import RuntimeState
from gmk_state.registry import build_registries
from gmk_semantics import SemanticValidator

FIXED='2026-09-27T06:55:00Z'

def envelope(typ,oid,**domain):
    return {
      'schema_header':{'schema_id':f'gmk://schema/v1/{typ.lower().replace("_","-")}','schema_version':'1.0.0'},
      'id':oid,'object_type':typ,'version':1,'status':'CURRENT','lock_state':'UNLOCKED',
      'created_at':FIXED,'updated_at':FIXED,'dependencies':[],'stale':{'is_stale':False,'reasons':[]},
      'approval_summary':{'state':'NOT_REQUIRED','approval_refs':[]},'human_constraints':[],'extensions':{},**domain,
    }

def state(root,objects=(),artifacts=(),project_state='BOOTSTRAPPED',safety_mode='NORMAL'):
    sem=SemanticValidator(root); om={(o['id'],int(o['version'])):o for o in objects}; am={(a['artifact_id'],int(a['version'])):a for a in artifacts}
    return RuntimeState(objects=om,artifacts=am,registries=build_registries(om,sem.decision_hash),project_state=project_state,safety_mode=safety_mode)

@pytest.fixture
def root():return ROOT
@pytest.fixture
def E():return envelope
@pytest.fixture
def S(root):return lambda **kw:state(root,**kw)
