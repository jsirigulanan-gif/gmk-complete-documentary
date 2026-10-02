from copy import deepcopy
import subprocess
import wave

import pytest

from gmk_projects.coverage import inspect_coverage, record_coverage
from gmk_projects.edit import EditError
from gmk_projects.final_production import (decide_final_voice, final_binding_status, inspect_final,
                                          master_file, prepare_final, reopen_final, _heads)
from gmk_projects.production import ProductionProject
from gmk_projects.production_bridge import _active
from tests.build054.test_coverage import covered, assess
from tests.build053.test_media_bridge import footage


def prepare(p):
    preview=inspect_final(p)
    return prepare_final(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])


def decide(p,decision='APPROVED',actor='Fixture reviewer'):
    preview=inspect_final(p);loaded=ProductionProject(p)._load()
    master=_heads(loaded.engine.snapshot(),'MASTER_VOICE')[0]
    return decide_final_voice(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'],
                              expected_master_sha256=master['audio']['sha256'],decision=decision,actor_id=actor)


def test_final_script_real_master_and_explicit_voice_decision(covered):
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Explicit fixture library stop.')
    before=ProductionProject(p)._load().manifest_sha256
    assert inspect_final(p)['ready'] and ProductionProject(p)._load().manifest_sha256==before
    result=prepare(p)
    assert result['production_state']=='TTS_READY' and result['binding']['current'] and not result['binding']['voice_locked']
    loaded=ProductionProject(p)._load();state=loaded.engine.snapshot()
    from gmk_projects.coverage import coverage_binding_status
    from gmk_projects.production_bridge import binding_status
    from gmk_projects.media_bridge import media_binding_status
    assert binding_status(p,state)['current'] and media_binding_status(p,state)['current']
    assert coverage_binding_status(p,state)['ready'] and coverage_binding_status(p,state)['selection_closed']
    script=_heads(state,'VOICEOVER_SCRIPT_FINAL')[0]
    assert script['blocks'][0]['narration_text']==session.load()['scenes'][0]['narration']
    assert _active(state)[script['blocks'][0]['beat_ref']['id']]['workflow_state']=='NARRATION_FINAL'
    master=_heads(state,'MASTER_VOICE')[0];path=master_file(ProductionProject(p),master)
    with wave.open(str(path)) as audio:
        assert audio.getnframes()==38400 and audio.getframerate()==48000 and audio.getnchannels()==1
    assert loaded.dependency_summary['changed_objects']==0
    assert not any(o['object_type']=='APPROVAL' and o.get('approval_class')=='VOICE' for o in _active(state).values())
    from gmk_voice import VoiceRuntime
    review=VoiceRuntime(loaded.engine.root,ProductionProject(p).workspace).review_package()
    assert review.voice_lock_ref==result['binding']['voice_lock_ref']
    assert ProductionProject(p)._load().manifest_sha256==loaded.manifest_sha256
    sha=loaded.manifest_sha256;assert prepare(p)['idempotent_replay']
    assert ProductionProject(p)._load().manifest_sha256==sha
    approved=decide(p)
    assert approved['binding']['voice_locked'] and approved['production_state']=='VOICE_LOCKED'
    sha=approved['manifest_sha256'];assert decide(p)['idempotent_replay']
    assert ProductionProject(p)._load().manifest_sha256==sha


def test_stale_preview_missing_bytes_and_voice_edits_do_not_publish(covered):
    from gmk_projects.media_review import review_voice
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Explicit fixture library stop.')
    preview=inspect_final(p);before=ProductionProject(p)._load().manifest_sha256
    session.attach_voice(scene,voice,expected_revision=session.load()['revision'])
    with pytest.raises(EditError,match='เปลี่ยนหลังเปิดตรวจ'):
        prepare_final(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])
    assert ProductionProject(p)._load().manifest_sha256==before
    review_voice(p,scene,expected_revision=session.load()['revision']);prepare(p)
    loaded=ProductionProject(p)._load();master=_heads(loaded.engine.snapshot(),'MASTER_VOICE')[0]
    path=master_file(ProductionProject(p),master);path.write_bytes(b'Corrupt derived master')
    assert not final_binding_status(p,ProductionProject(p)._load().engine.snapshot())['current']
    with pytest.raises(EditError):decide(p)


def test_late_compilation_failure_keeps_persisted_core_and_edit(covered,monkeypatch):
    from gmk_projects import final_production
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Explicit fixture library stop.')
    before=ProductionProject(p)._load().manifest_sha256;edit=session.load()
    original=final_production._artifact
    def fail(tx,kind,*args):
        if kind=='VOICE_LOCK_MANIFEST':raise EditError('Simulated final voice staging failure')
        return original(tx,kind,*args)
    monkeypatch.setattr(final_production,'_artifact',fail)
    with pytest.raises(EditError,match='Simulated'):prepare(p)
    assert ProductionProject(p)._load().manifest_sha256==before and session.load()==edit
    assert not _heads(ProductionProject(p)._load().engine.snapshot(),'VOICEOVER_SCRIPT_FINAL')


def test_scene_order_and_actual_pcm_follow_edit_with_frame_padding(covered):
    from tests.build051.test_production_bridge import bind_all, connect
    from tests.build053.test_media_bridge import register, rereview
    from gmk_projects.media_review import review_voice
    p,session,scene,shot,voice=covered
    extra=voice.parent/'short.wav'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','sine=frequency=880:duration=0.21:sample_rate=48000',str(extra)],check=True,capture_output=True)
    edit=session.load();video=p.root/edit['scenes'][0]['shots'][0]['path']
    added=session.new_scene();added.update(title='First in edit',narration='The dated report says the event occurred in 1981.',visual='The dated report')
    edit['scenes'].insert(0,added);edit['fps']=24;session.save(edit,expected_revision=edit['revision'])
    bind_all(p);connect(p)
    session.attach_voice(added['id'],extra,expected_revision=session.load()['revision'])
    review_voice(p,added['id'],expected_revision=session.load()['revision'])
    edit=session.add_shot(added['id'],video,.1,1.5,expected_revision=session.load()['revision'])
    for s in edit['scenes']:
        rereview(p,session,s['id'],s['shots'][0]['id'])
    register(p);assess(p,complete_selection=True,stop_reason='Reviewed two synthetic scene selections.')
    # The reusable core compiler must also respect Scene order, not generated IDs.
    import shutil
    from gmk_narrative import ScriptRuntime
    from gmk_runtime.cold_start import ColdStartLoader
    preview=inspect_final(p);clone=voice.parent/'core-order-copy'
    shutil.copytree(ProductionProject(p).workspace,clone)
    # This isolated legacy-compiler check retires the editor assessment before
    # Beat promotion; the product adapter also refreshes pictures/coverage.
    from gmk_projects.coverage import retire_coverage
    from gmk_runtime.persistence import RuntimeStore
    loaded=ColdStartLoader(ProductionProject(p)._load().engine.root,clone).load()
    tx=loaded.engine.begin();retire_coverage(tx);tx.commit()
    RuntimeStore(loaded.engine.root,clone).persist(loaded.engine)
    result=ScriptRuntime(ProductionProject(p)._load().engine.root,clone).run({'language':'th-TH', 'blocks':[
        {'beat_key':s['scene_id'],'language_mode':s['language_mode'],'narration_text':s['narration']} for s in preview['scenes']]})
    core=ColdStartLoader(ProductionProject(p)._load().engine.root,clone).load().engine.snapshot()
    compiled=core.artifacts[(result.script_ref['artifact_id'],result.script_ref['version'])]
    assert [b['narration_text'] for b in compiled['blocks']]==[s['narration'] for s in preview['scenes']]
    prepare(p);state=ProductionProject(p)._load().engine.snapshot()
    script=_heads(state,'VOICEOVER_SCRIPT_FINAL')[0]
    assert [b['narration_text'] for b in script['blocks']]==[s['narration'] for s in session.load()['scenes']]
    timing=_heads(state,'VOICE_TIMING_MAP')[0]['extensions']['project_sample_clock']['blocks']
    assert timing[0]['end_sample']==timing[1]['start_sample']==12000
    assert timing[1]['end_sample']==52000
    with wave.open(str(master_file(ProductionProject(p),_heads(state,'MASTER_VOICE')[0]))) as audio:
        assert audio.getnframes()==52000
        import array
        first=array.array('h',audio.readframes(4800));audio.setpos(12000)
        second=array.array('h',audio.readframes(4800))
    crossings=lambda xs:sum((a<0)!=(b<0) for a,b in zip(xs,xs[1:]))
    assert crossings(first)>140 and crossings(second)<110


def test_rejected_or_approved_voice_can_reopen_without_reusing_old_approval(covered):
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Explicit fixture selection.')
    prepare(p);rejected=decide(p,'REJECTED')
    assert rejected['production_state']=='TTS_READY' and not rejected['binding']['voice_locked']
    assert rejected['binding']['voice_decision']=='REJECTED'
    with pytest.raises(EditError,match='มีผลตรวจแล้ว'):decide(p)
    first=ProductionProject(p)._load().engine.snapshot()
    identities={kind:_heads(first,kind)[0]['artifact_id'] for kind in ('VOICEOVER_SCRIPT_FINAL','TTS_READY_SCRIPT','MASTER_VOICE','VOICE_LOCK_MANIFEST')}
    preview=inspect_final(p);edit=session.load()
    reopen_final(p,expected_edit_sha256=preview['edit_sha256'],expected_manifest_sha256=preview['manifest_sha256'])
    assert ProductionProject(p).status()['production_state']=='ASSET_RECON' and session.load()==edit
    assert not any(o['object_type']=='APPROVAL' for o in _active(ProductionProject(p)._load().engine.snapshot()).values())
    assess(p,complete_selection=True,stop_reason='Explicit repeated fixture selection after reopening.')
    prepare(p);state=ProductionProject(p)._load().engine.snapshot()
    for kind,key in identities.items(): assert _heads(state,kind)[0]['artifact_id']==key
    assert not final_binding_status(p,state)['voice_locked']
    approved=decide(p);assert approved['binding']['voice_locked']
    from gmk_projects.evidence import review_claim
    from gmk_projects.research import research_review
    claim=research_review(p)['claims'][0]
    review_claim(p,claim['id'],claim['version'],claim['text'],disposition='INSUFFICIENT')
    status=ProductionProject(p).status()
    assert status['production_state']=='RESEARCH_INTAKE' and not status['final_binding']['current']
    assert master_file(ProductionProject(p),_heads(first,'MASTER_VOICE')[0]).is_file()


def test_changes_during_assembly_and_foreign_records_cannot_publish(covered,monkeypatch):
    from gmk_projects import final_production
    from gmk_runtime.persistence import RuntimeStore
    p,session,scene,shot,voice=covered
    assess(p,complete_selection=True,stop_reason='Explicit fixture selection.')
    before=ProductionProject(p)._load().manifest_sha256
    original=final_production._assemble
    def change(*args):
        result=original(*args)
        edit=session.load();edit['scenes'][0]['show_title']=not edit['scenes'][0]['show_title']
        session.save(edit,expected_revision=edit['revision']);return result
    monkeypatch.setattr(final_production,'_assemble',change)
    with pytest.raises(EditError,match='เปลี่ยนระหว่างรวมเสียง'):prepare(p)
    assert ProductionProject(p)._load().manifest_sha256==before
    monkeypatch.setattr(final_production,'_assemble',original)
    loaded=ProductionProject(p)._load();tx=loaded.engine.begin()
    ref=tx.create_artifact('PRONUNCIATION_DICTIONARY',{'language':'th-TH','entries':[]});tx.commit()
    RuntimeStore(loaded.engine.root,ProductionProject(p).workspace).persist(loaded.engine)
    before=ProductionProject(p)._load().manifest_sha256
    assert not inspect_final(p)['ready']
    with pytest.raises(EditError,match='ระบบอื่น'):prepare(p)
    assert ProductionProject(p)._load().manifest_sha256==before
