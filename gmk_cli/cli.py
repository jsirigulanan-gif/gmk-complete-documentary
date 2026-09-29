from __future__ import annotations
from pathlib import Path
import argparse, hashlib, json, sys, zipfile

from gmk_runtime.cold_start import ColdStartLoader, ColdStartError
from gmk_runtime.persistence import RuntimeStore
from gmk_orchestrator import GMKOrchestrator
from gmk_workspace import WorkspaceBootstrapper, RuntimeDoctor
from gmk_research import ResearchIntakeRuntime, ResearchAuditRuntime
from gmk_narrative import RoughNarrativeRuntime, VisualRequirementsRuntime, ScriptRuntime, TTSRuntime
from gmk_assets import AssetReconRuntime, AssetSelectionRuntime, AssetAcquisitionRuntime, MediaHandoffRuntime, VisualCoverageRuntime
from gmk_voice import VoiceRuntime
from gmk_design import DesignRuntime
from gmk_planning import ScenePlanRuntime, ShotPlanRuntime
from gmk_review import HTMLReviewRuntime
from gmk_production import ProductionLockStageRuntime
from gmk_render import RenderQAStageRuntime
from gmk_qa import SceneQAStageRuntime, FullFilmQAStageRuntime
from gmk_release import DeliveryStageRuntime, ReleaseFinalStageRuntime
from gmk_audit import AuditRuntime
from gmk_pilot import PilotExecutionRuntime, PilotMediaIntakeRuntime, PilotMediaProcessRuntime, PilotReadinessRuntime
from gmk_footage.query_planner import FootageQueryPlanner
from gmk_footage.research import FootageResearchRuntime
from gmk_footage.fallback_research import MaterialFallbackResearchRuntime

ROOT=Path(__file__).resolve().parents[1]


def _print(data,as_json=False):
    if as_json:
        print(json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True))
    else:
        for k,v in data.items():
            if isinstance(v,(dict,list,tuple)):
                print(f'{k}: {json.dumps(v,ensure_ascii=False,sort_keys=True)}')
            else:print(f'{k}: {v}')


def cmd_init(args):
    res=WorkspaceBootstrapper(ROOT).init(Path(args.workspace),title=args.title,narration_language=args.language,target_format=args.format,runtime_min=args.runtime_min,runtime_max=args.runtime_max,working_title=args.working_title,research_pack=Path(args.research_pack) if args.research_pack else None)
    out={'workspace':str(res.workspace),'project_ref':res.project_ref,'project_state':res.manifest['project_state']['current'],'manifest_version':res.manifest['manifest_version'],'research_pack_ref':res.research_pack_ref,'input_copy':str(res.input_copy) if res.input_copy else None,'input_sha256':res.input_sha256}
    _print(out,args.json);return 0


def _load(ws):
    return ColdStartLoader(ROOT,Path(ws)).load()


def cmd_status(args):
    result=_load(args.workspace);orch=GMKOrchestrator(result.engine,workspace=Path(args.workspace));out=orch.status(actor_type=args.actor)
    out.update({'loaded_objects':result.loaded_objects,'loaded_artifacts':result.loaded_artifacts,'manifest_sha256':result.manifest_sha256})
    _print(out,args.json);return 0


def cmd_next(args):
    result=_load(args.workspace);out=result.engine.next_legal_action(actor_type=args.actor).to_dict();_print(out,args.json);return 0


def cmd_persist(args):
    result=_load(args.workspace);manifest=RuntimeStore(ROOT,Path(args.workspace)).persist(result.engine);_print({'manifest_id':manifest['manifest_id'],'manifest_version':manifest['manifest_version'],'project_state':manifest['project_state']['current']},args.json);return 0


def cmd_doctor(args):
    report=RuntimeDoctor(ROOT).run(Path(args.workspace) if args.workspace else None);_print(report.to_dict(),True if args.json else False);return 0 if report.ok else 2


def _sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()



def cmd_footage_plan(args):
    plan=FootageQueryPlanner(ROOT,Path(args.workspace)).build().to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(plan,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');plan['report_path']=str(path)
    _print(plan,args.json);return 0

def cmd_footage_research(args):
    report=FootageResearchRuntime(ROOT,Path(args.workspace)).run(per_query=args.per_query,inspect_top=args.inspect_top,timestamp_top=args.timestamp_top).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');report['report_path']=str(path)
    _print(report,args.json);return 0


def cmd_footage_material_research(args):
    youtube=FootageResearchRuntime(ROOT,Path(args.workspace)).run(per_query=args.per_query,inspect_top=args.inspect_top,timestamp_top=args.timestamp_top)
    fallback=MaterialFallbackResearchRuntime(ROOT,Path(args.workspace)).run(youtube,per_query=args.web_per_query)
    out={'youtube':youtube.to_dict(),'material_fallback':fallback.to_dict()}
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_pilot_preflight(args):
    p=Path(args.research_pack)
    checks=[]
    def add(name,ok,detail=None):
        x={'check':name,'ok':bool(ok)}
        if detail is not None:x['detail']=detail
        checks.append(x)
    add('file_exists',p.is_file(),str(p))
    if p.is_file():
        sha=_sha(p);add('sha256',True,sha);add('non_empty',p.stat().st_size>0,p.stat().st_size)
        if p.suffix.lower()=='.docx':
            try:
                with zipfile.ZipFile(p) as z:
                    names=set(z.namelist());ok='word/document.xml' in names and '[Content_Types].xml' in names
                add('docx_container_valid',ok,'word/document.xml present' if ok else 'required DOCX parts missing')
            except Exception as exc:add('docx_container_valid',False,str(exc))
        else:add('docx_container_valid',False,'Pilot Research Pack is expected to be .docx')
        expected='The Ghost of P.T.'
        add('pilot_name_match',expected.lower() in p.name.lower(),p.name)
    doctor=RuntimeDoctor(ROOT).run();checks.extend({'check':'runtime_'+c['check'],'ok':c['ok'],'detail':c.get('detail')} for c in doctor.checks)
    report={'pilot':'The Ghost of P.T. & The Erasure of Hideo Kojima','ready_for_bootstrap':all(c['ok'] for c in checks),'checks':checks,'scope_note':'Preflight verifies runtime/input integrity only. It does not claim Research Audit, factual verification, Asset Recon, or production readiness.'}
    if args.output:
        out=Path(args.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')
        report['report_path']=str(out)
    _print(report,args.json);return 0 if report['ready_for_bootstrap'] else 3



def cmd_research_intake(args):
    res=ResearchIntakeRuntime(ROOT,Path(args.workspace)).run()
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0



def cmd_research_audit(args):
    batch_path=Path(args.input)
    batch=json.loads(batch_path.read_text(encoding='utf-8'))
    res=ResearchAuditRuntime(ROOT,Path(args.workspace)).run(batch)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_rough_narrative(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=RoughNarrativeRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_visual_requirements(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=VisualRequirementsRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_asset_recon(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=AssetReconRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_asset_select(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=AssetSelectionRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_asset_acquire(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=AssetAcquisitionRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_asset_media_handoff(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=MediaHandoffRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_visual_coverage(args):
    res=VisualCoverageRuntime(ROOT,Path(args.workspace)).run()
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_script(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=ScriptRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_tts(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=TTSRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_voice_prepare(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=VoiceRuntime(ROOT,Path(args.workspace)).prepare(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_voice_review_package(args):
    res=VoiceRuntime(ROOT,Path(args.workspace)).review_package()
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_voice_decide(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=VoiceRuntime(ROOT,Path(args.workspace)).decide(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_design_prepare(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=DesignRuntime(ROOT,Path(args.workspace)).prepare(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_design_review_package(args):
    out=DesignRuntime(ROOT,Path(args.workspace)).review_package().to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_design_decide(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=DesignRuntime(ROOT,Path(args.workspace)).decide(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_scene_plan(args):
    out=ScenePlanRuntime(ROOT,Path(args.workspace)).run().to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_shot_plan(args):
    out=ShotPlanRuntime(ROOT,Path(args.workspace)).run().to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_html_review_prepare(args):
    out=HTMLReviewRuntime(ROOT,Path(args.workspace)).prepare().to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_html_review_decide(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=HTMLReviewRuntime(ROOT,Path(args.workspace)).decide(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_pilot_bootstrap(args):
    ws=Path(args.workspace)
    init=WorkspaceBootstrapper(ROOT).init(
        ws,
        title='The Ghost of P.T. & The Erasure of Hideo Kojima',
        working_title='The Ghost of P.T.',
        narration_language=args.language,
        target_format='LONGFORM_DOCUMENTARY',
        runtime_min=20.0,
        runtime_max=25.0,
        research_pack=Path(args.research_pack),
    )
    intake=ResearchIntakeRuntime(ROOT,ws).run()
    out={'bootstrap':{'project_ref':init.project_ref,'research_pack_ref':init.research_pack_ref,'input_sha256':init.input_sha256},'intake':intake.to_dict()}
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_production_lock_prepare(args):
    res=ProductionLockStageRuntime(ROOT,Path(args.workspace)).prepare()
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_production_lock_decide(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=ProductionLockStageRuntime(ROOT,Path(args.workspace)).decide(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_render_shot_qa(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=RenderQAStageRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_scene_qa(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=SceneQAStageRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_full_film_qa(args):
    plan_path=Path(args.input)
    plan=json.loads(plan_path.read_text(encoding='utf-8'))
    res=FullFilmQAStageRuntime(ROOT,Path(args.workspace)).run(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_delivery_prepare(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=DeliveryStageRuntime(ROOT,Path(args.workspace)).prepare(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def cmd_delivery_decide(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=DeliveryStageRuntime(ROOT,Path(args.workspace)).decide(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_audit(args):
    runtime=AuditRuntime(ROOT)
    result=runtime.run(profile=args.profile,timeout_seconds=args.timeout)
    out=result.to_dict()
    if args.output:
        path=Path(args.output)
        md=Path(args.markdown) if args.markdown else path.with_suffix('.md')
        AuditRuntime.write_reports(result,path,md)
        out['report_path']=str(path); out['markdown_path']=str(md)
    _print(out,args.json)
    return 0 if result.fail_count==0 else 2


def cmd_pilot_execution_pack(args):
    res=PilotExecutionRuntime(ROOT,Path(args.workspace)).prepare(Path(args.output_dir))
    _print(res.to_dict(),args.json);return 0


def cmd_pilot_media_preflight(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    res=PilotExecutionRuntime(ROOT,Path(args.workspace)).preflight(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0 if res.ready else 2


def cmd_pilot_media_execute(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    res=PilotExecutionRuntime(ROOT,Path(args.workspace)).execute(plan)
    out=res.to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0


def cmd_pilot_media_intake_init(args):
    res=PilotMediaIntakeRuntime(ROOT,Path(args.workspace)).init(Path(args.intake_dir))
    _print(res.to_dict(),args.json);return 0


def cmd_pilot_media_intake_build(args):
    inspection=json.loads(Path(args.inspection).read_text(encoding='utf-8'))
    res=PilotMediaIntakeRuntime(ROOT,Path(args.workspace)).build(Path(args.intake_dir),inspection,Path(args.output_dir) if args.output_dir else None)
    _print(res.to_dict(),args.json);return 0


def cmd_pilot_media_process(args):
    inspection=json.loads(Path(args.inspection).read_text(encoding='utf-8'))
    res=PilotMediaProcessRuntime(ROOT,Path(args.workspace)).run(
        Path(args.intake_dir),inspection,execute=bool(args.execute),
        output_dir=Path(args.output_dir) if args.output_dir else None,
    )
    _print(res.to_dict(),args.json);return 0


def cmd_pilot_readiness(args):
    res=PilotReadinessRuntime(ROOT,Path(args.workspace)).inspect(
        Path(args.intake_dir),Path(args.output_dir) if args.output_dir else None,
    )
    _print(res.to_dict(),args.json)
    return 0 if res.ready_to_execute or res.readiness=='ALREADY_ADVANCED' else 2


def cmd_release_finalize(args):
    plan=json.loads(Path(args.input).read_text(encoding='utf-8'))
    out=ReleaseFinalStageRuntime(ROOT,Path(args.workspace)).run(plan).to_dict()
    if args.output:
        path=Path(args.output);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8');out['report_path']=str(path)
    _print(out,args.json);return 0

def parser():
    p=argparse.ArgumentParser(prog='gmk',description='Gamer Must Know Production Pipeline v2 runtime CLI')
    sub=p.add_subparsers(dest='command',required=True)
    q=sub.add_parser('init',help='Bootstrap a new GMK workspace through the State Engine.')
    q.add_argument('--workspace',required=True);q.add_argument('--title',required=True);q.add_argument('--working-title');q.add_argument('--language',default='th-TH');q.add_argument('--format',choices=['LONGFORM_DOCUMENTARY','VERTICAL_SLICE_PILOT'],default='LONGFORM_DOCUMENTARY');q.add_argument('--runtime-min',type=float,default=20.0);q.add_argument('--runtime-max',type=float,default=40.0);q.add_argument('--research-pack');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_init)
    q=sub.add_parser('status',help='Cold-start a workspace and show reconstructed runtime status.');q.add_argument('--workspace',required=True);q.add_argument('--actor',choices=['SYSTEM','AI','HUMAN'],default='SYSTEM');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_status)
    q=sub.add_parser('next-action',help='Show the next legal Gate/State action.');q.add_argument('--workspace',required=True);q.add_argument('--actor',choices=['SYSTEM','AI','HUMAN'],default='SYSTEM');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_next)
    q=sub.add_parser('persist',help='Persist reconstructed runtime state without changing authoritative decisions.');q.add_argument('--workspace',required=True);q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_persist)
    q=sub.add_parser('doctor',help='Run runtime/schema installation and optional workspace integrity checks.');q.add_argument('--workspace');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_doctor)
    q=sub.add_parser('pilot-preflight',help='Check the P.T. Research Pack and runtime before pilot bootstrap.');q.add_argument('--research-pack',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_preflight)
    q=sub.add_parser('research-intake',help='Parse the registered Research Pack into safe UNREVIEWED GMK research-intake records.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_research_intake)
    q=sub.add_parser('research-audit',help='Apply an external verification batch and derive exact GMK research dispositions.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_research_audit)
    q=sub.add_parser('rough-narrative',help='Compile current audited Claims into ACT/SCENE/NARRATION_BEAT rough narrative objects and a NARRATIVE_SPINE.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_rough_narrative)
    q=sub.add_parser('visual-requirements',help='Attach complete visual evidence requirements to every current rough Narrative Beat and advance to VISUAL_REQUIREMENTS_READY.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_visual_requirements)
    q=sub.add_parser('asset-recon',help='Create exact Beat-targeted SEARCH/SEARCH_RESULT candidates and candidate comparisons without promoting them to ASSET.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_asset_recon)
    q=sub.add_parser('footage-plan',help='Build deterministic YouTube-first footage search intents from current Narration Beats without network access or workspace mutation.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_footage_plan)
    q=sub.add_parser('footage-research',help='Run YouTube-first metadata/caption research, ranking and timestamp nomination without downloading video bytes.');q.add_argument('--workspace',required=True);q.add_argument('--per-query',type=int,default=5);q.add_argument('--inspect-top',type=int,default=3);q.add_argument('--timestamp-top',type=int,default=3);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_footage_research)
    q=sub.add_parser('footage-material-research',help='Run YouTube-first research and automatically fall back to web/archive video then still/document candidates; AI remains last-resort marker only.');q.add_argument('--workspace',required=True);q.add_argument('--per-query',type=int,default=5);q.add_argument('--inspect-top',type=int,default=3);q.add_argument('--timestamp-top',type=int,default=3);q.add_argument('--web-per-query',type=int,default=5);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_footage_material_research)
    q=sub.add_parser('asset-select',help='Close Search Again, issue Search Completion Certificate, explicitly select candidates, create ASSET identities, and plan acquisition without inventing original files or SEGMENTs.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_asset_select)
    q=sub.add_parser('asset-acquire',help='Verify acquired bytes or bounded web evidence snapshots, advance ASSET lifecycle, create exact SEGMENTs, and run visual coverage QA without substituting deferred media.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_asset_acquire)
    q=sub.add_parser('asset-media-handoff',help='Validate externally supplied original video bytes with ffprobe/SHA-256, require exact time ranges, and safely close pending video acquisition through the existing asset-acquire runtime.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_asset_media_handoff)
    q=sub.add_parser('visual-coverage',help='Verify complete production-ready Segment coverage and advance ASSET_CATALOG_READY through the frozen VISUAL_COVERAGE Gate.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_visual_coverage)
    q=sub.add_parser('script',help='Compile complete final narration for all active Beats, pin Beat decision hashes into VOICEOVER_SCRIPT_FINAL, and advance through the frozen SCRIPT Gate.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_script)
    q=sub.add_parser('tts',help='Compile the exact final voiceover script into pronunciation dictionary, voice profile, TTS-ready blocks, and advance through the frozen TTS Gate.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_tts)
    q=sub.add_parser('voice-prepare',help='Verify imported master voice bytes, build exact timing and VOICE_LOCK_MANIFEST, and stop at the frozen Human Approval boundary.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_voice_prepare)
    q=sub.add_parser('voice-review-package',help='Create the pre-scene VOICE_REVIEW_PACKAGE needed for human voice-lock review without requiring Scene Plan artifacts.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_voice_review_package)
    q=sub.add_parser('voice-decide',help='Record an explicit human APPROVED/REJECTED voice decision against VOICE_REVIEW_PACKAGE and transition to VOICE_LOCKED only when approved.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_voice_decide)
    q=sub.add_parser('design-prepare',help='Create DESIGN_DNA and EFFECTIVE_DESIGN_TOKENS from exact voice/narrative dependencies, stopping at human approval.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_design_prepare)
    q=sub.add_parser('design-review-package',help='Create pre-scene DESIGN_DNA_REVIEW_PACKAGE for human design review without Scene Plan artifacts.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_design_review_package)
    q=sub.add_parser('design-decide',help='Record human APPROVED/REJECTED design decision and transition to DESIGN_DNA_APPROVED only when approved.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_design_decide)
    q=sub.add_parser('scene-plan',help='Create one SCENE_ASSET_POOL and SCENE_PLAN per active Scene from approved design, locked voice timing, and verified visual coverage, then advance to SCENE_PLAN_READY.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_scene_plan)
    q=sub.add_parser('shot-plan',help='Compile exact SHOT/LAYER/CUE objects from Scene Plans, verified Segments, voice timing, and approved design, then advance to SHOT_PLAN_READY.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_shot_plan)
    q=sub.add_parser('html-review-prepare',help='Generate deterministic per-Scene HTML review files, SCENE_PREVIEW and REVIEW_PACKAGE artifacts, then enter HTML_REVIEW.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_html_review_prepare)
    q=sub.add_parser('html-review-decide',help='Record explicit human APPROVED/REJECTED decisions for current Scene Previews and enter HTML_APPROVED only when every Scene is approved.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_html_review_decide)
    q=sub.add_parser('production-lock-prepare',help='Compile the exact HTML-approved Shot/Layer/Cue closure into a PRODUCTION_LOCK_REVIEW_PACKAGE without creating locks yet.');q.add_argument('--workspace',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_production_lock_prepare)
    q=sub.add_parser('production-lock-decide',help='Record explicit human APPROVED/REJECTED production-lock decision; APPROVED creates exact Shot approvals, Scene/Project locks, lock approvals, and enters PRODUCTION_RENDER only if the Gate passes.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_production_lock_decide)
    q=sub.add_parser('render-shot-qa',help='Import an actual final render, execute it against the exact Project Production Lock, require explicit review coverage for every active Shot, and advance only when RENDER + SHOT_QA both PASS.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_render_shot_qa)
    q=sub.add_parser('scene-qa',help='Require explicit checklist review for every active Scene, aggregate current PASS Shot QA evidence against one Final Render, and advance only when SCENE_QA passes.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_scene_qa)
    q=sub.add_parser('full-film-qa',help='Require explicit Viewer Experience, Production Integrity, and Delivery Integrity review passes against the exact Final Render, then advance only when FULL_FILM_QA passes.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_full_film_qa)
    q=sub.add_parser('delivery-prepare',help='Build exact delivery manifests, Delivery QA, package, PRE_RELEASE checkpoint and DELIVERY_REVIEW_PACKAGE without publishing.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_delivery_prepare)
    q=sub.add_parser('delivery-decide',help='Record explicit human RELEASE approval/rejection of the exact delivery candidate and enter DELIVERY_READY only after approval and a PASS Delivery Gate.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_delivery_decide)
    q=sub.add_parser('release-finalize',help='Publish an exact human-approved DELIVERY_READY candidate through the authorized LOCAL_EXPORT adapter, create immutable RELEASE, FINAL_PROJECT checkpoint, and complete the project.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_release_finalize)
    q=sub.add_parser('pilot-execution-pack',help='Generate the exact P.T. external-media execution manifest, handoff template, and operator runbook from the current workspace.');q.add_argument('--workspace',required=True);q.add_argument('--output-dir',required=True);q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_execution_pack)
    q=sub.add_parser('pilot-media-preflight',help='Validate the complete P.T. source-locked media handoff plan with ffprobe/range/source-lock/checksum checks without mutating the workspace.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_media_preflight)
    q=sub.add_parser('pilot-media-execute',help='Execute a passing P.T. source-locked media handoff and advance only through the non-human Visual Coverage stage.');q.add_argument('--workspace',required=True);q.add_argument('--input',required=True);q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_media_execute)
    q=sub.add_parser('pilot-media-intake-init',help='Create source-locked per-candidate intake slots and an inspection worksheet without mutating the P.T. workspace.');q.add_argument('--workspace',required=True);q.add_argument('--intake-dir',required=True);q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_media_intake_init)
    q=sub.add_parser('pilot-media-intake-build',help='Probe/hash exactly one authorized video per intake slot, require explicit human inspection, create checksum receipt and a preflight-valid handoff plan without mutating the P.T. workspace.');q.add_argument('--workspace',required=True);q.add_argument('--intake-dir',required=True);q.add_argument('--inspection',required=True);q.add_argument('--output-dir');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_media_intake_build)
    q=sub.add_parser('pilot-media-process',help='One-command P.T. media intake build + authoritative preflight; non-mutating by default and executes acquisition only with explicit --execute.');q.add_argument('--workspace',required=True);q.add_argument('--intake-dir',required=True);q.add_argument('--inspection',required=True);q.add_argument('--output-dir');q.add_argument('--execute',action='store_true');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_media_process)
    q=sub.add_parser('pilot-readiness',help='Read-only P.T. readiness dashboard: inspect pending source-locked media slots, human inspection completeness, and authoritative preflight readiness without mutating PT_WORKSPACE.');q.add_argument('--workspace',required=True);q.add_argument('--intake-dir',required=True);q.add_argument('--output-dir');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_readiness)
    q=sub.add_parser('audit',help='Run repository hardening audit. STATIC performs deterministic package checks, QUICK adds validators/smokes/fast regressions, FULL adds heavy build partitions with explicit TIMEOUT reporting.');q.add_argument('--profile',choices=['STATIC','QUICK','FULL'],default='QUICK');q.add_argument('--timeout',type=int,default=120);q.add_argument('--output');q.add_argument('--markdown');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_audit)
    q=sub.add_parser('pilot-bootstrap',help='Create the durable P.T. pilot workspace and run Research Intake without claiming Research Audit.');q.add_argument('--workspace',required=True);q.add_argument('--research-pack',required=True);q.add_argument('--language',default='th-TH');q.add_argument('--output');q.add_argument('--json',action='store_true');q.set_defaults(fn=cmd_pilot_bootstrap)
    return p


def main(argv=None):
    args=parser().parse_args(argv)
    try:return int(args.fn(args) or 0)
    except ColdStartError as exc:
        print(json.dumps({'error':exc.code,'message':str(exc),'details':exc.details},ensure_ascii=False),file=sys.stderr);return 2
    except Exception as exc:
        print(json.dumps({'error':type(exc).__name__,'message':str(exc)},ensure_ascii=False),file=sys.stderr);return 1
