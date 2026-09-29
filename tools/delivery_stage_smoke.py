from pathlib import Path
from tempfile import TemporaryDirectory
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from gmk_release import DeliveryStageRuntime
from gmk_release.runtime import ReleaseRuntime
from gmk_qa import FullFilmQAStageRuntime
from tests.build032.test_full_film_qa_stage import _scene_qa_passed, _plan as _ff_plan

def fake_profile(self,config_id='GMK_TEST_320'):
    data={'config_id':'GMK_TEST_320','version':'1.0.0','schema_version':'1.0.0','video':{'width':320,'height':180,'allowed_codecs':['h264'],'min_duration_seconds':0.1},'audio':{'required':False},'metadata':{'required_fields':['title','description']},'release':{'required_destinations':['PRIMARY'],'optional_destinations':[]}}
    return data,{'config_id':'GMK_TEST_320','version':'1.0.0','sha256':'a'*64}
ReleaseRuntime.load_delivery_profile=fake_profile
with TemporaryDirectory(prefix='gmk_delivery_') as d:
    ws=_scene_qa_passed(Path(d));FullFilmQAStageRuntime(ROOT,ws).run(_ff_plan(batch='SMOKE_FF'))
    rt=DeliveryStageRuntime(ROOT,ws);p=rt.prepare({'batch_id':'SMOKE_DELIVERY','profile_id':'GMK_TEST_320','metadata':{'title':'P.T.','description':'Smoke'}})
    assert p.project_state=='FULL_FILM_QA_PASSED' and p.delivery_gate=='PASS'
    out=rt.decide({'actor_id':'delivery_owner','decision':'APPROVED','checks':{'package_integrity':'PASS','provenance_complete':'PASS','rights_ready':'PASS','metadata_ready':'PASS','destination_ready':'PASS'}})
    assert out.project_state=='DELIVERY_READY' and out.transitioned is True
    print('PASS — exact delivery candidate + human RELEASE approval reached DELIVERY_READY without publishing.')
