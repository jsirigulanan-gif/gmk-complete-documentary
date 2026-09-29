from __future__ import annotations
from copy import deepcopy
from pathlib import Path

from gmk_state.errors import StateEngineError
from gmk_production import ProductionLockRuntime
from gmk_render import RenderRuntime
from gmk_qa import QARuntime
from gmk_release import ReleaseRuntime
from gmk_recovery import CheckpointRuntime
from gmk_operations import OperationRuntime

class GMKOrchestrator:
    """Thin policy-respecting harness around the GMK runtime engines.

    It does not invent missing evidence or bypass gates. It exposes the current
    legal action, advances only when the Gate Engine permits it, and composes the
    production/release runtimes for integration tests and future Antigravity use.
    """
    def __init__(self,engine,*,workspace:Path|None=None):
        self.engine=engine; self.workspace=Path(workspace) if workspace is not None else None
        self.production=ProductionLockRuntime(engine); self.render=RenderRuntime(engine); self.qa=QARuntime(engine)
        self.release=ReleaseRuntime(engine,workspace=workspace); self.checkpoints=CheckpointRuntime(engine,workspace=workspace); self.operations=OperationRuntime(engine)

    def status(self,*,actor_type='SYSTEM'):
        return {'project_state':self.engine.project_state,'safety_mode':self.engine.safety_mode,'manifest_version':self.engine.manifest_version,'next_legal_action':self.engine.next_legal_action(actor_type=actor_type).to_dict()}

    def advance(self,*,actor_type='SYSTEM',human_confirmed=False):
        nxt=self.engine.next_legal_action(actor_type=actor_type)
        if nxt.action!='TRANSITION_PROJECT_STATE' or not nxt.target_state:
            raise StateEngineError('ORCHESTRATOR_BLOCKED','Project cannot advance without satisfying the reported prerequisite.',details=nxt.to_dict())
        tx=self.engine.begin();tx.transition_project_state(nxt.target_state,actor_type=actor_type,human_confirmed=human_confirmed);tx.commit();return self.status(actor_type=actor_type)

    def advance_to(self,target_state,*,human_states=()):
        seen=0
        while self.engine.project_state!=target_state:
            if seen>64:raise StateEngineError('ORCHESTRATOR_LOOP_GUARD','Too many state transitions while advancing project.')
            nxt=self.engine.next_legal_action(actor_type='HUMAN' if self.engine.project_state in set(human_states) else 'SYSTEM')
            if nxt.action!='TRANSITION_PROJECT_STATE' or not nxt.target_state:raise StateEngineError('ORCHESTRATOR_BLOCKED',f'Blocked before {target_state}.',details=nxt.to_dict())
            human=self.engine.project_state in set(human_states)
            tx=self.engine.begin();tx.transition_project_state(nxt.target_state,actor_type='HUMAN' if human else 'SYSTEM',human_confirmed=human);tx.commit();seen+=1
        return self.status()
