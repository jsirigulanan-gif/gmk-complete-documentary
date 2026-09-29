from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json, hashlib, yaml

from gmk_runtime.cold_start import ColdStartLoader, ColdStartError


@dataclass(frozen=True)
class DoctorReport:
    ok: bool
    checks: tuple[dict[str,Any],...]

    def to_dict(self):
        return {'ok':self.ok,'checks':[dict(x) for x in self.checks]}


class RuntimeDoctor:
    def __init__(self, runtime_root: Path):
        self.root=Path(runtime_root)

    def run(self, workspace: Path|None=None) -> DoctorReport:
        checks=[]
        def add(name,ok,detail=None):
            rec={'check':name,'ok':bool(ok)}
            if detail is not None:rec['detail']=detail
            checks.append(rec)

        registry_path=self.root/'schema'/'schema-registry.json'
        try:
            reg=json.loads(registry_path.read_text(encoding='utf-8'))
            missing=[]
            for sid,rel in reg.get('schemas',{}).items():
                if not (self.root/rel).is_file():missing.append({'schema_id':sid,'path':rel})
            add('schema_registry',not missing,{'registered':len(reg.get('schemas',{})),'missing':missing})
        except Exception as exc:
            add('schema_registry',False,str(exc))

        pb=self.root/'config'/'gmk_policy_bundle.yaml'
        try:
            data=yaml.safe_load(pb.read_text(encoding='utf-8')) or {}
            sha=hashlib.sha256(pb.read_bytes()).hexdigest()
            add('policy_bundle',data.get('config_id')=='GMK_POLICY_BUNDLE' and bool(data.get('version')),{'config_id':data.get('config_id'),'version':str(data.get('version')),'sha256':sha})
        except Exception as exc:
            add('policy_bundle',False,str(exc))

        if workspace is not None:
            ws=Path(workspace)
            add('workspace_pointer',(ws/'CURRENT_MANIFEST.json').is_file(),str(ws/'CURRENT_MANIFEST.json'))
            if (ws/'CURRENT_MANIFEST.json').is_file():
                try:
                    result=ColdStartLoader(self.root,ws).load()
                    add('cold_start',True,{'project_state':result.engine.project_state,'manifest_version':result.engine.manifest_version,'loaded_objects':result.loaded_objects,'loaded_artifacts':result.loaded_artifacts,'safety_mode':result.engine.safety_mode})
                except ColdStartError as exc:
                    add('cold_start',False,{'code':exc.code,'message':str(exc),'details':exc.details})
                except Exception as exc:
                    add('cold_start',False,str(exc))
        return DoctorReport(all(c['ok'] for c in checks),tuple(checks))
