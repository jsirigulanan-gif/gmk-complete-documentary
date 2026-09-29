from pathlib import Path
import sys, pytest
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

class Clock:
    def __init__(self):self.n=0
    def __call__(self):
        self.n+=1
        return f"2026-09-27T08:{self.n:02d}:00Z"

@pytest.fixture
def root():return ROOT
@pytest.fixture
def clock():return Clock()
@pytest.fixture
def engine(root,clock):return StateEngine(root,clock=clock)
@pytest.fixture
def project(engine):
    tx=engine.begin();ref=tx.create_object('PROJECT',{
        'title':'GMK Build 007','language':{'narration':'th-TH'},
        'target':{'format':'LONGFORM_DOCUMENTARY','runtime_minutes':{'min':20,'max':40}}
    });tx.commit();return ref
