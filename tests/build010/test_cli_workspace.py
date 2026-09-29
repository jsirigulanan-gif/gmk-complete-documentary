from pathlib import Path
import json, subprocess, sys, zipfile

ROOT=Path(__file__).resolve().parents[2]


def run(*args,check=True):
    return subprocess.run([sys.executable,'-m','gmk_cli',*map(str,args)],cwd=ROOT,text=True,capture_output=True,check=check)


def make_pack(path:Path):
    path.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(path,'w') as z:
        z.writestr('[Content_Types].xml','<Types/>')
        z.writestr('word/document.xml','<w:document/>')


def test_cli_init_status_doctor_and_next_action(tmp_path):
    ws=tmp_path/'workspace';pack=tmp_path/'The Ghost of P.T. Research Pack.docx';make_pack(pack)
    r=run('init','--workspace',ws,'--title','The Ghost of P.T.','--format','LONGFORM_DOCUMENTARY','--runtime-min','20','--runtime-max','40','--research-pack',pack,'--json')
    init=json.loads(r.stdout);assert init['project_state']=='BOOTSTRAPPED';assert init['research_pack_ref']['artifact_type']=='RESEARCH_PACK';assert (ws/'CURRENT_MANIFEST.json').is_file();assert (ws/'WORKSPACE.json').is_file();assert (ws/'inputs'/'research'/pack.name).is_file()
    status=json.loads(run('status','--workspace',ws,'--json').stdout);assert status['project_state']=='BOOTSTRAPPED';assert status['loaded_objects']==1;assert status['loaded_artifacts']==1
    nxt=json.loads(run('next-action','--workspace',ws,'--json').stdout);assert nxt['action']=='TRANSITION_PROJECT_STATE';assert nxt['target_state']=='RESEARCH_INTAKE'
    doc=json.loads(run('doctor','--workspace',ws,'--json').stdout);assert doc['ok'] is True


def test_cli_pilot_preflight_is_explicitly_not_research_audit(tmp_path):
    pack=tmp_path/'The Ghost of P.T. & The Erasure of Hideo Kojima Research Pack.docx';make_pack(pack)
    report_path=tmp_path/'preflight.json';r=run('pilot-preflight','--research-pack',pack,'--output',report_path,'--json');data=json.loads(r.stdout)
    assert data['ready_for_bootstrap'] is True;assert 'does not claim Research Audit' in data['scope_note'];assert report_path.is_file()


def test_cli_init_refuses_existing_workspace(tmp_path):
    ws=tmp_path/'workspace';run('init','--workspace',ws,'--title','A','--json')
    r=run('init','--workspace',ws,'--title','B','--json',check=False);assert r.returncode!=0;assert 'WORKSPACE_ALREADY_INITIALIZED' in r.stderr
