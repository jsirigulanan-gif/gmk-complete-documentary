from pathlib import Path
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

FIXED='2026-09-27T05:05:00Z'

def project_payload(title='GMK Project', *, constraints=None):
    d={
      'title':title,
      'language':{'narration':'th-TH'},
      'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}},
    }
    if constraints is not None:d['human_constraints']=constraints
    return d

@pytest.fixture
def root(): return ROOT
@pytest.fixture
def engine(ROOT=None):
    return StateEngine(Path(__file__).resolve().parents[2],clock=lambda:FIXED)
@pytest.fixture
def P(): return project_payload
