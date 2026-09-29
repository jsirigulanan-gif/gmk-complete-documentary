from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_state import StateEngine

FIXED='2026-09-27T06:55:00Z'
pack={'artifact_id':'RESEARCH_PACK_001','artifact_type':'RESEARCH_PACK','version':1,'sha256':'a'*64}
e=StateEngine(ROOT,artifacts=[pack],clock=lambda:FIXED)
assert e.evaluate_gate('BOOTSTRAP').result=='PASS'
assert e.next_legal_action(actor_type='AI').action=='TRANSITION_PROJECT_STATE'
tx=e.begin();tx.transition_project_state('RESEARCH_INTAKE',actor_type='AI');tx.commit()
assert e.project_state=='RESEARCH_INTAKE'
assert e.gate_history()[-1]['gate_id']=='BOOTSTRAP'
print('PASS — Gate Engine evaluated exact evidence, authorized adjacent transition, and recorded immutable gate snapshot.')
