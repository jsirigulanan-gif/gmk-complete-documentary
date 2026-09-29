from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import sys
import pytest

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_semantics import SemanticValidator, StateView

SHA="0"*64
TS="2026-09-27T04:00:00Z"


def base(typ,id,version=1,**kw):
    d={
      "schema_header":{"schema_id":f"gmk://schema/v1/{typ.lower().replace('_','-')}","schema_version":"1.0.0"},
      "id":id,"object_type":typ,"version":version,"status":"CURRENT","lock_state":"UNLOCKED",
      "created_at":TS,"updated_at":TS,"dependencies":[],"stale":{"is_stale":False,"reasons":[]},
      "approval_summary":{"state":"NOT_REQUIRED"},"human_constraints":[],"extensions":{}
    }
    d.update(kw); return d


def art(typ,id,version=1,**kw):
    d={"schema_header":{"schema_id":f"gmk://schema/v1/artifact/{typ.lower().replace('_','-')}","schema_version":"1.0.0"},
       "artifact_id":id,"artifact_type":typ,"version":version,"uri":f"gmk://artifacts/{id.lower()}","sha256":SHA,
       "created_at":TS,"origin_refs":[],"extensions":{}}
    d.update(kw); return d

@pytest.fixture
def validator(): return SemanticValidator(ROOT)
@pytest.fixture
def B(): return base
@pytest.fixture
def A(): return art
@pytest.fixture
def sha(): return SHA
