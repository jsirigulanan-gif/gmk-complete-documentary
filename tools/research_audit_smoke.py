from pathlib import Path
import json, tempfile, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_workspace import WorkspaceBootstrapper
from gmk_research import ResearchIntakeRuntime, ResearchAuditRuntime
from gmk_runtime.cold_start import ColdStartLoader

PACK=ROOT/'pilot'/'PT_WORKSPACE'/'inputs'/'research'/'[Research Pack] The Ghost of P.T. & The Erasure of Hideo Kojima (LEMiNO Pipeline).docx'
BATCH=ROOT/'pilot'/'PT_RESEARCH_AUDIT_INPUT.json'

with tempfile.TemporaryDirectory(prefix='gmk-research-audit-smoke-') as td:
    ws=Path(td)/'PT_WORKSPACE'
    WorkspaceBootstrapper(ROOT).init(
        ws,
        title='The Ghost of P.T. & The Erasure of Hideo Kojima',
        working_title='The Ghost of P.T.',
        narration_language='th-TH',
        target_format='LONGFORM_DOCUMENTARY',
        runtime_min=20.0,
        runtime_max=25.0,
        research_pack=PACK,
    )
    intake=ResearchIntakeRuntime(ROOT,ws).run()
    assert intake.project_state=='RESEARCH_INTAKE'
    batch=json.loads(BATCH.read_text(encoding='utf-8'))
    audited=ResearchAuditRuntime(ROOT,ws).run(batch)
    assert audited.project_state=='RESEARCH_AUDITED'
    assert audited.gate_result=='PASS'
    assert audited.disposition_counts=={'CORROBORATED':5,'SOURCE_VERIFIED':6,'INSUFFICIENT_EVIDENCE':3}
    loaded=ColdStartLoader(ROOT,ws).load()
    assert loaded.dependency_summary=={'drift_roots':0,'invalidations':0,'changed_objects':0}
    assert loaded.next_legal_action['target_state']=='ROUGH_NARRATIVE_READY'
    replay=ResearchAuditRuntime(ROOT,ws).run(batch)
    assert replay.idempotent_replay is True
print('PASS: P.T. Research Audit derived evidence-backed dispositions, cleared the intake guard, transitioned to RESEARCH_AUDITED, cold-started without registry drift, and replayed idempotently.')
