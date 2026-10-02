from copy import deepcopy
import pytest

from gmk_state import StateEngine, ResolverMode, StateEngineError
from gmk_dependency import NodeKey, NodeKind, ImpactDisposition


def make_source_evidence_claim(engine,payloads,*,evidence_constraints=None):
    tx=engine.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=engine.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src,constraints=evidence_constraints)); tx.commit()
    tx=engine.begin(); cl=tx.create_object('CLAIM',payloads['claim'](ev)); tx.commit()
    return src,ev,cl


def test_dependency_projection_is_compiled_from_schema_annotations(engine,payloads):
    tx=engine.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=engine.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src)); tx.commit()
    obj=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    assert obj['dependencies']==[{'target':src,'relation':'EVIDENCE_SOURCE'}]


def test_creating_head_version_does_not_propagate_until_promoted(engine,payloads):
    src,ev,_=make_source_evidence_claim(engine,payloads)
    tx=engine.begin(); v2=tx.create_version(src['id'],base_version=1,patch={'title':'Source v2'}); tx.commit()
    evidence=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    assert evidence['status']=='CURRENT'
    assert evidence['stale']['is_stale'] is False
    assert engine.dependency_invalidation(ev['id'],1) is None
    assert engine.resolver().resolve(src['id'],mode=ResolverMode.ACTIVE)['version']==1
    assert engine.resolver().resolve(src['id'],mode=ResolverMode.HEAD)['version']==2


def test_active_promotion_stales_direct_and_transitive_dependents_without_retarget(engine,payloads):
    src,ev,cl=make_source_evidence_claim(engine,payloads)
    ev_before=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    cl_before=engine.resolver().resolve(cl['id'],mode=ResolverMode.EXACT,version=1)
    ev_decision_before=engine.registry_snapshots()['RESEARCH_REGISTRY']['entries'][ev['id']]['versions']['1']['decision_sha256']

    tx=engine.begin(); v2=tx.create_version(src['id'],base_version=1,patch={'title':'Corrected source title'}); tx.commit()
    tx=engine.begin(); result=tx.promote_active_version(src['id'],v2['version']); tx.commit()

    evidence=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    claim=engine.resolver().resolve(cl['id'],mode=ResolverMode.EXACT,version=1)
    assert evidence['status']=='STALE' and evidence['stale']['is_stale']
    assert claim['status']=='STALE' and claim['stale']['is_stale']
    assert evidence['source_ref']==src                       # no auto-retarget
    assert evidence['dependencies'][0]['target']==src       # exact v1 remains exact v1
    ev_decision_after=engine.registry_snapshots()['RESEARCH_REGISTRY']['entries'][ev['id']]['versions']['1']['decision_sha256']
    assert ev_decision_before==ev_decision_after             # derived stale did not change decision hash

    impact_ref=result['dependency_impact_report']
    assert impact_ref and len(impact_ref['sha256'])==64
    art=engine.snapshot().artifacts[(impact_ref['artifact_id'],1)]
    assert art['artifact_type']=='DEPENDENCY_IMPACT_REPORT'
    impacted={x['node']['ref'].get('id') for x in art['impacts'] if x['disposition']!='UNAFFECTED'}
    assert {ev['id'],cl['id']} <= impacted


def test_derived_from_marks_revalidate_not_stale_and_can_be_explicitly_cleared(engine,payloads):
    tx=engine.begin(); project=tx.create_object('PROJECT',payloads['project']()); tx.commit()
    tx=engine.begin(); act=tx.create_object('ACT',payloads['act'](project)); tx.commit()
    tx=engine.begin(); scene=tx.create_object('SCENE',payloads['scene'](act)); tx.commit()
    before_hash=engine.registry_snapshots()['NARRATIVE_REGISTRY']['entries'][scene['id']]['versions']['1']['decision_sha256']

    tx=engine.begin(); act2=tx.create_version(act['id'],base_version=1,patch={'title':'Act revised'}); tx.commit()
    tx=engine.begin(); tx.promote_active_version(act['id'],2); tx.commit()

    scene_obj=engine.resolver().resolve(scene['id'],mode=ResolverMode.EXACT,version=1)
    inv=engine.dependency_invalidation(scene['id'],1)
    assert scene_obj['status']=='CURRENT' and scene_obj['stale']['is_stale'] is False
    assert inv['disposition']=='REVALIDATE'

    tx=engine.begin(); tx.revalidate_dependency_node(scene['id'],1); tx.commit()
    assert engine.dependency_invalidation(scene['id'],1) is None
    after_hash=engine.registry_snapshots()['NARRATIVE_REGISTRY']['entries'][scene['id']]['versions']['1']['decision_sha256']
    assert before_hash==after_hash


def test_repeated_promotions_persist_same_stale_envelope_as_cold_start(engine,payloads,tmp_path):
    from gmk_runtime import RuntimeStore, ColdStartLoader
    tx=engine.begin(); tx.create_object('PROJECT',payloads['project']()); tx.commit()
    src,ev,cl=make_source_evidence_claim(engine,payloads)
    store=RuntimeStore(engine.root,tmp_path/'workspace')
    for version in (2,3):
        tx=engine.begin()
        tx.create_version(src['id'],base_version=version-1,patch={'title':f'Corrected source {version}'})
        tx.promote_active_version(src['id'],version); tx.commit()
        store.persist(engine)
        loaded=ColdStartLoader(engine.root,store.workspace).load()
        assert loaded.dependency_summary['changed_objects']==0
        assert loaded.engine.registry_snapshots()==engine.registry_snapshots()
        for ref in (ev,cl):
            assert loaded.engine.snapshot().objects[(ref['id'],ref['version'])]['stale']['is_stale']
        assert loaded.engine.snapshot().objects[(ev['id'],1)]['source_ref']==src


def test_archived_dependent_is_retained_history_on_promotion_and_cold_start(engine,payloads,tmp_path):
    from gmk_runtime import RuntimeStore, ColdStartLoader
    tx=engine.begin(); tx.create_object('PROJECT',payloads['project']()); tx.commit()
    src,ev,cl=make_source_evidence_claim(engine,payloads)
    tx=engine.begin(); tx.archive_object(ev['id']); tx.archive_object(cl['id']); tx.commit()
    originals={ref['id']:deepcopy(engine.snapshot().objects[(ref['id'],1)]) for ref in (ev,cl)}
    for version in (2,3):
        tx=engine.begin(); tx.create_version(src['id'],base_version=version-1,patch={'title':f'Revision {version}'})
        tx.promote_active_version(src['id'],version); tx.commit()
        store=RuntimeStore(engine.root,tmp_path/'archive-history'); store.persist(engine)
        loaded=ColdStartLoader(engine.root,store.workspace).load()
        assert loaded.dependency_summary['changed_objects']==0
        assert loaded.engine.registry_snapshots()==engine.registry_snapshots()
        for ref in (ev,cl):
            assert loaded.engine.snapshot().objects[(ref['id'],1)]==originals[ref['id']]


def test_human_locked_creative_impact_requires_explicit_promotion_confirmation(engine,payloads):
    c={'constraint_id':'HC_EVIDENCE_SUMMARY','scope':{'path':'/content_summary'},'rule':{'type':'PRESERVE','statement':'Preserve reviewed evidence summary'},'lock_state':'HUMAN_LOCKED'}
    tx=engine.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=engine.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src,constraints=[c])); tx.commit()
    tx=engine.begin(); tx.create_version(src['id'],base_version=1,patch={'title':'Source renamed'}); tx.commit()

    tx=engine.begin(); report=tx.preview_promotion_impact(src['id'],2)
    assert any(x.node.node_id==ev['id'] for x in report.impacts)
    with pytest.raises(StateEngineError) as err:
        tx.promote_active_version(src['id'],2)
    assert err.value.code=='PROMOTION_LOCKED_IMPACT_CONFIRMATION_REQUIRED'
    tx.discard()

    tx=engine.begin(); tx.promote_active_version(src['id'],2,confirm_locked_impact=True); tx.commit()
    evidence=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    assert evidence['lock_state']=='HUMAN_LOCKED'              # lock preserved
    assert evidence['status']=='STALE'                         # invalidation may still occur


def test_cold_start_projection_mismatch_fails_closed_to_read_only(root,payloads):
    e=StateEngine(root,clock=lambda:'2026-09-27T06:10:00Z')
    tx=e.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=e.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src)); tx.commit()
    snap=e.snapshot()
    objects=[deepcopy(o) for o in snap.objects.values()]
    for obj in objects:
        if obj['id']==ev['id']: obj['dependencies']=[]          # corrupt persisted projection
    cold=StateEngine(root,objects=objects,clock=lambda:'2026-09-27T06:10:00Z')
    assert cold.safety_mode=='READ_ONLY'
    assert cold.dependency_integrity_issues()[0]['code']=='DEPENDENCY_PROJECTION_MISMATCH'
    with pytest.raises(StateEngineError) as err:cold.begin()
    assert err.value.code=='DEPENDENCY_INTEGRITY_READ_ONLY'


def test_promotion_target_with_pending_revalidation_cannot_be_promoted(engine,payloads):
    tx=engine.begin(); project=tx.create_object('PROJECT',payloads['project']()); tx.commit()
    tx=engine.begin(); act=tx.create_object('ACT',payloads['act'](project)); tx.commit()
    tx=engine.begin(); scene=tx.create_object('SCENE',payloads['scene'](act)); tx.commit()
    tx=engine.begin(); scene2=tx.create_version(scene['id'],base_version=1,patch={'title':'Scene candidate'}); tx.commit()
    # Scene v2 itself depends on Act v1. Promote Act and both live Scene versions receive REVALIDATE.
    tx=engine.begin(); act2=tx.create_version(act['id'],base_version=1,patch={'title':'Act v2'}); tx.commit()
    tx=engine.begin(); tx.promote_active_version(act['id'],act2['version']); tx.commit()
    tx=engine.begin()
    with pytest.raises(StateEngineError) as err:tx.promote_active_version(scene['id'],scene2['version'])
    assert err.value.code=='PROMOTION_TARGET_REVALIDATION_REQUIRED'

def test_non_production_version_drift_is_unaffected(engine,payloads):
    tx=engine.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=engine.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src)); tx.commit()
    tx=engine.begin(); src2=tx.create_version(src['id'],base_version=1,patch={'notes':'Internal research note only'}); tx.commit()
    tx=engine.begin(); preview=tx.preview_promotion_impact(src['id'],src2['version'])
    assert preview.change_set.impact_tags==('NON_PRODUCTION',)
    assert any(x.node.node_id==ev['id'] and x.disposition==ImpactDisposition.UNAFFECTED for x in preview.impacts)
    tx.promote_active_version(src['id'],src2['version']); tx.commit()
    evidence=engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)
    assert evidence['status']=='CURRENT'
    assert evidence['stale']['is_stale'] is False
    assert engine.dependency_invalidation(ev['id'],1) is None

def test_cold_start_full_recompute_restores_live_invalidation_from_active_drift(root,payloads):
    e=StateEngine(root,clock=lambda:'2026-09-27T06:10:00Z')
    tx=e.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=e.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src)); tx.commit()
    tx=e.begin(); cl=tx.create_object('CLAIM',payloads['claim'](ev)); tx.commit()
    tx=e.begin(); tx.create_version(src['id'],base_version=1,patch={'title':'Source v2'}); tx.commit()
    tx=e.begin(); tx.promote_active_version(src['id'],2); tx.commit()
    snap=e.snapshot()
    objects=[deepcopy(o) for o in snap.objects.values()]
    # Simulate stale live-derived cache being lost while authoritative exact refs remain.
    for obj in objects:
        if obj['id'] in {ev['id'],cl['id']}:
            obj['status']='CURRENT'; obj['stale']={'is_stale':False,'reasons':[]}
    cold=StateEngine(root,objects=objects,clock=lambda:'2026-09-27T06:10:00Z')
    assert cold.safety_mode=='NORMAL'
    summary=cold.cold_start_dependency_summary()
    assert summary['drift_roots']>=1 and summary['invalidations']>=2
    assert cold.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)['status']=='STALE'
    assert cold.resolver().resolve(cl['id'],mode=ResolverMode.EXACT,version=1)['status']=='STALE'


def test_live_graph_skips_middle_historical_versions(engine,payloads):
    tx=engine.begin(); src=tx.create_object('SOURCE',payloads['source']()); tx.commit()
    tx=engine.begin(); ev=tx.create_object('EVIDENCE',payloads['evidence'](src)); tx.commit()
    # v1 remains ACTIVE, v3 becomes HEAD; v2 is historical middle version.
    tx=engine.begin(); tx.create_version(ev['id'],base_version=1,patch={'content_summary':'Candidate v2'}); tx.commit()
    tx=engine.begin(); tx.create_version(ev['id'],base_version=2,patch={'content_summary':'Candidate v3'}); tx.commit()
    tx=engine.begin(); tx.create_version(src['id'],base_version=1,patch={'title':'Source v2'}); tx.commit()
    tx=engine.begin(); tx.promote_active_version(src['id'],2); tx.commit()
    assert engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=1)['status']=='STALE'
    assert engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=3)['status']=='STALE'
    assert engine.resolver().resolve(ev['id'],mode=ResolverMode.EXACT,version=2)['status']=='CURRENT'
    assert engine.dependency_invalidation(ev['id'],2) is None
