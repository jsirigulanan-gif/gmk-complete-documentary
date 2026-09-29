from pathlib import Path
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

FIXED='2026-09-27T07:30:00Z'

def project_payload(title='GMK Runtime'):
    return {'title':title,'language':{'narration':'th-TH'},'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}}}

@pytest.fixture
def root():return ROOT
@pytest.fixture
def engine():return StateEngine(ROOT,clock=lambda:FIXED)
@pytest.fixture
def P():return project_payload
