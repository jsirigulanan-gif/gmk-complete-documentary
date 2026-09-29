from pathlib import Path
from tempfile import TemporaryDirectory
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))

from gmk_qa import FullFilmQAStageRuntime, SceneQAStageRuntime
from tests.build031.test_scene_qa_stage import _shot_qa_passed, _plan as _scene_plan
from tests.build032.test_full_film_qa_stage import _plan as _full_plan

with TemporaryDirectory(prefix='gmk_full_film_qa_') as d:
    ws=_shot_qa_passed(Path(d))
    SceneQAStageRuntime(ROOT,ws).run(_scene_plan(ws,batch='SMOKE_SCENE_QA'))
    out=FullFilmQAStageRuntime(ROOT,ws).run(_full_plan(batch='SMOKE_FULL_FILM'))
    assert out.project_state=='FULL_FILM_QA_PASSED'
    assert out.full_film_qa_gate=='PASS'
    assert out.transitioned is True
    print('PASS — explicit three-pass Full Film QA reached FULL_FILM_QA_PASSED with exact current Scene-QA/render/lock evidence.')
