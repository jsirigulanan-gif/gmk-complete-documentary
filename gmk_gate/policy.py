from __future__ import annotations
from pathlib import Path
from typing import Any
import hashlib, yaml, json

class GatePolicy:
    def __init__(self, root:Path):
        self.root=Path(root)
        self.path=self.root/'config'/'gates_policies.yaml'
        self.raw=yaml.safe_load(self.path.read_text(encoding='utf-8')) or {}
        self.config_id=self.raw.get('config_id','GMK_GATES_POLICY')
        self.version=str(self.raw.get('version','1.0.0'))
        self.sha256=hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.gates={x['gate_id']:x for x in self.raw.get('gates',[])}
        self.transitions={(x['from'],x['to']):x for x in self.raw.get('transitions',[])}
        self.blocker_rules=list(self.raw.get('blocker_rules',[]))
        self.project_states=list(self.raw.get('project_states',[]))
        self._validate()
    @property
    def ref(self)->dict[str,Any]:
        return {'config_id':self.config_id,'version':self.version,'sha256':self.sha256}
    def gate(self,gate_id:str)->dict[str,Any]:
        if gate_id not in self.gates: raise KeyError(gate_id)
        return self.gates[gate_id]
    def transition(self,fr:str,to:str)->dict[str,Any]|None:
        return self.transitions.get((fr,to))

    def _validate(self):
        enums=json.loads((self.root/'schema/core/enums.schema.json').read_text(encoding='utf-8'))['$defs']
        legal_gates=set(enums['GateId']['enum']); legal_states=list(enums['ProjectState']['enum'])
        if set(self.gates)-legal_gates:
            raise ValueError(f'Unknown GateId(s) in policy: {sorted(set(self.gates)-legal_gates)}')
        if self.project_states != legal_states:
            raise ValueError('Gate policy project_states must exactly match frozen ProjectState enum order.')
        legal_permissions={'AUTO_ALLOWED','AI_WITH_RULES','HUMAN_APPROVAL_REQUIRED','HUMAN_ONLY','FORBIDDEN'}
        legal_warn={'ALLOW','REQUIRE_EXCEPTION'}
        for (fr,to),td in self.transitions.items():
            if fr not in legal_states or to not in legal_states:raise ValueError(f'Unknown transition state {fr}->{to}')
            if legal_states.index(to)!=legal_states.index(fr)+1:raise ValueError(f'Normal transition must be adjacent: {fr}->{to}')
            if any(g not in self.gates for g in td.get('gates',[])):raise ValueError(f'Transition {fr}->{to} references undefined gate.')
            if td.get('permission') not in legal_permissions:raise ValueError(f'Invalid permission class on {fr}->{to}.')
            if td.get('warn_policy','REQUIRE_EXCEPTION') not in legal_warn:raise ValueError(f'Invalid warn policy on {fr}->{to}.')
        expected={(legal_states[i],legal_states[i+1]) for i in range(len(legal_states)-1)}
        if set(self.transitions)!=expected:
            missing=sorted(expected-set(self.transitions)); extra=sorted(set(self.transitions)-expected)
            raise ValueError(f'Gate policy must define every adjacent transition exactly once; missing={missing}, extra={extra}')
