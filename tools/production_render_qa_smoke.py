from pathlib import Path
import sys, tempfile
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tests/build008'))
from gmk_state import StateEngine
from conftest import Clock, bootstrap
from gmk_production import ProductionLockRuntime
from gmk_render import RenderRuntime, RenderProduct
from gmk_qa import QARuntime
class A:
    def render(self,payload,snapshot,*,attempt):return RenderProduct('gmk://renders/smoke.mp4',b'smoke',technical={'width':1280,'height':720,'duration_seconds':5.0})
e=StateEngine(ROOT,clock=Clock());r=bootstrap(e);lock=ProductionLockRuntime(e).create_scene_lock(voice_lock_ref=r['voice_lock'],design_dna_ref=r['dna'],scene_plan_ref=r['plan'],scene_preview_ref=r['preview']);rr=RenderRuntime(e);job=rr.queue_final(production_lock_ref=lock,scope_target=r['scene']);out=rr.execute(job,A());qa=QARuntime(e).evaluate(report_type='SHOT_QA',scope=r['shot'],observed_artifact=out['output_ref'],findings=[]);assert qa['result']=='PASS';print('PASS: production lock + final render + QA execution loop')
